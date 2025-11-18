from cat.mad_hatter.decorators import hook
from typing import Dict, List, Any
from cat.log import log
from cat.looking_glass.stray_cat import StrayCat
import os
import asyncio
import urllib.parse
import time

from .core.context import ScrapyCatContext
from .utils.url_utils import clean_url, normalize_url_with_protocol, normalize_domain, validate_url
from .utils.robots import load_robots_txt
from .integrations.crawl4ai import run_crawl4ai_setup, crawl4i, CRAWL4AI_AVAILABLE
from .core.crawler import crawler


def process_scrapycat_command(user_message: str, cat: StrayCat) -> str:
    """Process a scrapycat command and return the result message"""
    
    settings: Dict[str, Any] = cat.mad_hatter.get_plugin().load_settings()

    # Parse command arguments
    parts: List[str] = user_message.split()
    if len(parts) < 2:
        return "Usage: @scrapycat <url1> [url2 ...] [--allow <allowed_url1> [allowed_url2 ...]]"
    
    # Find --allow flag position
    allow_index: int = -1
    for i, part in enumerate(parts):
        if part == "--allow":
            allow_index = i
            break
    
    # Extract starting URLs and allowed URLs
    if allow_index == -1:
        # No --allow flag, all URLs after @scrapycat are starting URLs
        starting_urls: List[str] = [normalize_url_with_protocol(clean_url(url)) for url in parts[1:] if validate_url(url)]
        command_allowed_urls: List[str] = []
    else:
        # Split at --allow flag
        starting_urls = [normalize_url_with_protocol(clean_url(url)) for url in parts[1:allow_index] if validate_url(url)]
        # Allow more flexible validation for allowed URLs (domains without protocols are OK)
        command_allowed_urls = []
        for url in parts[allow_index + 1:]:
            cleaned_url: str = clean_url(url)
            if validate_url(cleaned_url):
                command_allowed_urls.append(cleaned_url)
            else:
                # Log validation issues for debugging
                log.warning(f"Invalid allowed URL ignored: {cleaned_url}")
    
    if not starting_urls:
        log.error("No valid starting URLs provided")
        return "Error: No valid starting URLs provided"

    # Initialize context for this run
    ctx: ScrapyCatContext = ScrapyCatContext()
    ctx.command = user_message  # Store the command that triggered this session
    ctx.ingest_pdf = settings.get("ingest_pdf", False)
    ctx.skip_get_params = settings.get("skip_get_params", False)
    ctx.max_depth = settings.get("max_depth", -1)
    ctx.use_crawl4ai = settings.get("use_crawl4ai", False)
    ctx.follow_robots_txt = settings.get("follow_robots_txt", False)

    # Build allowed domains set (for single-page scraping only, no recursion)
    # 1. Add domains from settings (normalize them for consistency)
    settings_allowed_urls: List[str] = [
        normalize_url_with_protocol(url.strip()) for url in settings.get("allowed_extra_roots", "").split(",")
        if url.strip() and validate_url(url.strip())
    ]
    for url in settings_allowed_urls:
        ctx.allowed_domains.add(normalize_domain(url))
    
    # 2. Add domains from command --allow argument
    for url in command_allowed_urls:
        normalized_url = normalize_url_with_protocol(url)
        ctx.allowed_domains.add(normalize_domain(normalized_url))

    ctx.max_pages = settings.get("max_pages", -1)
    ctx.max_workers = settings.get("max_workers", 1)  # Default to 1 if not set
    ctx.chunk_size = settings.get("chunk_size", 512)  # Default to 512 if not set
    ctx.chunk_overlap = settings.get("chunk_overlap", 128)  # Default to 128 if not set

    # Check if crawl4ai is requested but not available
    if ctx.use_crawl4ai and not CRAWL4AI_AVAILABLE:
        log.warning("crawl4ai requested but not available. Run '@scrapycat crawl4ai-setup' first. Falling back to default crawling.")
        ctx.use_crawl4ai = False

    # Extract root domains and paths from starting URLs
    ctx.root_domains = set()
    ctx.allowed_paths = set()
    for url in starting_urls:
        parsed_url: urllib.parse.ParseResult = urllib.parse.urlparse(url)
        ctx.root_domains.add(normalize_domain(parsed_url.netloc))
        # Add the path (or "/" if empty) to allowed paths
        path: str = parsed_url.path or "/"
        ctx.allowed_paths.add(path)
    
    # Preload robots.txt for all starting domains if robots.txt following is enabled
    if ctx.follow_robots_txt:
        all_domains = ctx.root_domains.union(ctx.allowed_domains)
        for domain in all_domains:
            load_robots_txt(ctx, domain)
        log.info(f"Robots.txt preloaded for {len(all_domains)} domains")

    log.info(f"ScrapyCat started: {len(starting_urls)} URLs, max_pages={ctx.max_pages}, max_depth={ctx.max_depth}, workers={ctx.max_workers}, robots.txt={ctx.follow_robots_txt}")
    if ctx.allowed_domains:
        log.info(f"Single-page domains configured: {len(ctx.allowed_domains)} domains")
    if ctx.root_domains:
        log.info(f"Recursive domains configured: {len(ctx.root_domains)} domains")

    # Fire before_scrape hook with serializable context data
    try:
        # Create completely independent data structure to avoid any lock references
        context_data = {
            "session_id": str(ctx.session_id),  # Ensure it's a string
            "command": str(ctx.command),        # Ensure it's a string
            "scraped_pages": [],  # Empty at start
            "failed_pages": [],   # Empty at start
            "chunk_size": int(ctx.chunk_size),
            "chunk_overlap": int(ctx.chunk_overlap)
        }
        cat.mad_hatter.execute_hook("scrapycat_before_scrape", context_data, cat=cat)
    except Exception as hook_error:
        log.warning(f"Error executing before_scrape hook: {hook_error}")

    # Start crawling from all starting URLs
    try:
        # Record start time for the whole crawling+ingestion operation
        start_time = time.time()
        crawler(ctx, cat, starting_urls)
        log.info(f"Crawling completed: {len(ctx.scraped_pages)} pages scraped")
        
        # Fire after_crawl hook with serializable context data
        try:
            # Create completely independent data structure to avoid any lock references
            context_data = {
                "session_id": str(ctx.session_id),  # Ensure it's a string
                "command": str(ctx.command),        # Ensure it's a string
                "scraped_pages": [str(url) for url in ctx.scraped_pages],  # Create new list with string copies
                "failed_pages": [],  # No failures yet during crawling
                "chunk_size": int(ctx.chunk_size),
                "chunk_overlap": int(ctx.chunk_overlap)
            }
            log.debug(f"Firing after_crawl hook with context data: session_id={context_data['session_id']}, command={context_data['command']}")
            cat.mad_hatter.execute_hook("scrapycat_after_crawl", context_data, cat=cat)
        except Exception as hook_error:
            log.warning(f"Error executing after_crawl hook: {hook_error}")
        
        # Sequential ingestion after parallel scraping is complete
        if not ctx.scraped_pages:
            return "No pages were successfully scraped"
        
        ingested_count: int = 0
        failed_count: int = 0
        for i, scraped_url in enumerate(ctx.scraped_pages):
            try:
                if ctx.use_crawl4ai and CRAWL4AI_AVAILABLE:
                    # Use crawl4ai for content extraction
                    try:
                        markdown_content: str = asyncio.run(crawl4i(scraped_url))
                        output_file: str = "temp_crawl4ai_content.md"
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(markdown_content)
                        metadata: Dict[str, str] = {
                            "url": scraped_url, 
                            "source": scraped_url,
                            "session_id": ctx.session_id,
                            "command": ctx.command
                        }
                        cat.rabbit_hole.ingest_file(cat, output_file, ctx.chunk_size, ctx.chunk_overlap, metadata)
                        os.remove(output_file)
                        ingested_count += 1
                    except Exception as crawl4ai_error:
                        log.warning(f"crawl4ai failed for {scraped_url}, falling back to default method: {str(crawl4ai_error)}")
                        # Fallback to default method
                        metadata: Dict[str, str] = {
                            "url": scraped_url,
                            "source": scraped_url, 
                            "session_id": ctx.session_id,
                            "command": ctx.command
                        }
                        cat.rabbit_hole.ingest_file(cat, scraped_url, ctx.chunk_size, ctx.chunk_overlap, metadata)
                        ingested_count += 1
                else:
                    # Use default ingestion method
                    metadata: Dict[str, str] = {
                        "url": scraped_url,
                        "source": scraped_url,
                        "session_id": ctx.session_id,
                        "command": ctx.command
                    }
                    cat.rabbit_hole.ingest_file(cat, scraped_url, ctx.chunk_size, ctx.chunk_overlap, metadata)
                    ingested_count += 1
                
                # Send progress update
                cat.send_ws_message(f"Ingested {ingested_count}/{len(ctx.scraped_pages)} pages - Currently processing: {scraped_url}")
                
            except Exception as e:
                failed_count += 1
                ctx.failed_pages.append(scraped_url)  # Track failed pages in context
                log.error(f"Page ingestion failed: {scraped_url} - {str(e)}")
                # Continue with next page even if one fails
        
        log.info(f"Ingestion completed: {ingested_count} successful, {failed_count} failed")
        # Compute elapsed time in minutes (rounded to 2 decimal places)
        elapsed_seconds = time.time() - start_time
        minutes = round(elapsed_seconds / 60.0, 2)
        response: str = f"{ingested_count} URLs successfully imported, {failed_count} failed in {minutes} minutes"

    except Exception as e:
        log.error(f"ScrapyCat operation failed: {str(e)}")
        response = f"ScrapyCat failed: {str(e)}"
    finally:
        # Fire after_scrape hook with serializable context data
        try:
            # Create completely independent data structure to avoid any lock references
            context_data = {
                "session_id": str(ctx.session_id),  # Ensure it's a string
                "command": str(ctx.command),        # Ensure it's a string
                "scraped_pages": [str(url) for url in ctx.scraped_pages],  # Create new list with string copies
                "failed_pages": [str(url) for url in ctx.failed_pages],    # Create new list with string copies
                "chunk_size": int(ctx.chunk_size),
                "chunk_overlap": int(ctx.chunk_overlap)
            }
            log.debug(f"Firing after_scrape hook with context data: session_id={context_data['session_id']}, command={context_data['command']}")
            cat.mad_hatter.execute_hook("scrapycat_after_scrape", context_data, cat=cat)
        except Exception as hook_error:
            log.warning(f"Error executing after_scrape hook: {hook_error}")
        
        # Always close the session
        ctx.session.close()

    return response


@hook(priority=9)
def agent_fast_reply(fast_reply: Dict, cat: StrayCat) -> Dict:

    user_message: str = cat.working_memory.user_message_json.text

    if not user_message.startswith("@scrapycat"):
        return fast_reply

    # Handle crawl4ai setup command
    if user_message.strip() == "@scrapycat crawl4ai-setup":
        result: str = run_crawl4ai_setup()
        return {"output": result}

    # Process the scrapycat command using the extracted function
    result = process_scrapycat_command(user_message, cat)
    return {"output": result}