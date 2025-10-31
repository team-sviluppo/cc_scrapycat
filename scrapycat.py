from cat.mad_hatter.decorators import hook
from typing import Dict, Set, Tuple, List, Optional, Any
from cat.log import log
from bs4 import BeautifulSoup
import requests
import urllib.parse
from cat.looking_glass.stray_cat import StrayCat
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import os
import asyncio
import subprocess
from urllib.robotparser import RobotFileParser

# crawl4ai imports
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    log.warning("crawl4ai not available. Install it to use advanced crawling features.")


class ScrapyCatContext:
    def __init__(self) -> None:
        self.visited_pages: Set[str] = set()  # Set of visited pages during crawling
        self.root_domains: Set[str] = set()  # Set of normalized root domains (for recursive crawling)
        self.allowed_paths: Set[str] = set()  # Set of allowed base paths for URL filtering
        self.ingest_pdf: bool = False  # Whether to ingest PDFs
        self.skip_get_params: bool = False  # Skip URLs with GET parameters
        self.max_depth: int = -1  # Max recursion/crawling depth (-1 for unlimited)
        self.max_pages: int = -1  # Max pages to crawl (-1 for unlimited)
        self.allowed_domains: Set[str] = set()  # Set of allowed domains (single page scraping only)
        self.use_crawl4ai: bool = False  # Whether to use crawl4ai for content extraction
        self.follow_robots_txt: bool = False  # Whether to follow robots.txt
        self.robots_cache: Dict[str, Optional[RobotFileParser]] = {}  # Cache robots.txt parsers by domain
        self.visited_lock: Lock = Lock()  # Thread-safe access to visited_pages
        self.max_workers: int = 1   # Configurable thread pool size
        self.chunk_size: int = 512  # Size of text chunks for ingestion
        self.chunk_overlap: int = 128  # Overlap between consecutive chunks
        # Session reuse for better performance
        self.session: requests.Session = requests.Session()  # Reuse connections
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0"
        })
        # Store scraped pages for sequential ingestion
        self.scraped_pages: List[str] = []
        self.scraped_pages_lock: Lock = Lock()  # Thread-safe access to scraped_pages

def run_crawl4ai_setup() -> str:
    """Setup crawl4ai dependencies and configuration"""
    try:
        # Runs the setup command just like in the shell
        subprocess.run(["crawl4ai-setup"], check=True)
        log.info("Crawl4AI setup completed successfully.")
        return "Crawl4AI setup completed successfully."
    except subprocess.CalledProcessError as e:
        log.error(f"Error during Crawl4AI setup: {e}")
        return "Error during Crawl4AI setup."
    except FileNotFoundError:
        log.error("crawl4ai-setup command not found. Make sure crawl4ai is installed.")
        return "crawl4ai-setup command not found. Make sure crawl4ai is installed."


async def crawl4i(url: str) -> str:
    """Use crawl4ai to extract content from a URL"""
    if not CRAWL4AI_AVAILABLE:
        raise ImportError("crawl4ai is not available. Please install it first.")
    
    if not url.endswith(".pdf"):
        async with AsyncWebCrawler() as mdcrawler:
            config = CrawlerRunConfig(
                excluded_tags=["form", "header", "footer", "nav"],
                exclude_social_media_links=True,
                exclude_external_images=True,
                remove_overlay_elements=True,
            )
            md_generator = DefaultMarkdownGenerator(
                options={"ignore_links": True, "ignore_images": True}
            )
            config.markdown_generator = md_generator
            result = await mdcrawler.arun(url, config=config)
            return result.markdown
    else:
        pdf_crawler_strategy = PDFCrawlerStrategy()
        async with AsyncWebCrawler(crawler_strategy=pdf_crawler_strategy) as pdfcrawler:
            pdf_scraping_strategy = PDFContentScrapingStrategy()
            run_config = CrawlerRunConfig(scraping_strategy=pdf_scraping_strategy)
            result = await pdfcrawler.arun(url=url, config=run_config)
            if result.markdown and hasattr(result.markdown, "raw_markdown"):
                return result.markdown.raw_markdown
            return ""


def clean_url(url: str) -> str:
    # Remove trailing slashes and normalize the URL
    return url.strip().rstrip("/")


def normalize_url_with_protocol(url: str) -> str:
    """
    Ensure URL has a protocol. If no protocol is specified, prepend https://
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
    return url


def normalize_domain(domain_or_url: str) -> str:
    """
    Normalize a domain or URL to a consistent format for comparison.
    Returns the domain without protocol, and handles www subdomain normalization.
    
    Examples:
    - "https://example.com" -> "example.com"
    - "www.example.com" -> "example.com" 
    - "https://www.example.com" -> "example.com"
    - "example.com" -> "example.com"
    """
    domain = domain_or_url.strip().lower()
    
    # Remove protocol if present
    if domain.startswith(('http://', 'https://')):
        domain = urllib.parse.urlparse(domain).netloc
    
    # Remove www. prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return domain


def load_robots_txt(ctx: ScrapyCatContext, domain: str) -> Optional[RobotFileParser]:
    """
    Load and parse robots.txt for a given domain.
    Returns None if robots.txt is not accessible or parsing fails.
    Results are cached in ctx.robots_cache.
    """
    if domain in ctx.robots_cache:
        return ctx.robots_cache[domain]
    
    try:
        # Try both http and https
        for protocol in ['https', 'http']:
            robots_url = f"{protocol}://{domain}/robots.txt"
            try:
                response = ctx.session.get(robots_url, timeout=10)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.set_url(robots_url)
                    rp.read()
                    ctx.robots_cache[domain] = rp
                    log.info(f"Loaded robots.txt for {domain} from {robots_url}")
                    return rp
            except Exception as e:
                log.warning(f"Failed to load robots.txt from {robots_url}: {e}")
                continue
        
        # If we get here, robots.txt is not accessible
        log.info(f"No accessible robots.txt found for {domain}, allowing all URLs")
        ctx.robots_cache[domain] = None
        return None
        
    except Exception as e:
        log.warning(f"Error loading robots.txt for {domain}: {e}")
        ctx.robots_cache[domain] = None
        return None


def is_url_allowed_by_robots(ctx: ScrapyCatContext, url: str) -> bool:
    """
    Check if a URL is allowed by robots.txt.
    Returns True if robots.txt allows the URL or if robots.txt is not available.
    """
    if not ctx.follow_robots_txt:
        return True
    
    parsed_url = urllib.parse.urlparse(url)
    domain = normalize_domain(parsed_url.netloc)
    
    # Get robots.txt parser for this domain
    robots_parser = load_robots_txt(ctx, domain)
    
    # If no robots.txt available, allow the URL
    if robots_parser is None:
        return True
    
    # Check if the URL is allowed for our user agent
    user_agent = ctx.session.headers.get('User-Agent', '*')
    return robots_parser.can_fetch(user_agent, url)


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

    # Start crawling from all starting URLs
    try:
        crawler(ctx, cat, starting_urls)
        log.info(f"Crawling completed: {len(ctx.scraped_pages)} pages scraped")
        
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
                        metadata: Dict[str, str] = {"url": scraped_url, "source": scraped_url}
                        cat.rabbit_hole.ingest_file(cat, output_file, ctx.chunk_size, ctx.chunk_overlap, metadata)
                        os.remove(output_file)
                        ingested_count += 1
                    except Exception as crawl4ai_error:
                        log.warning(f"crawl4ai failed for {scraped_url}, falling back to default method: {str(crawl4ai_error)}")
                        # Fallback to default method
                        cat.rabbit_hole.ingest_file(cat, scraped_url, ctx.chunk_size, ctx.chunk_overlap)
                        ingested_count += 1
                else:
                    # Use default ingestion method
                    cat.rabbit_hole.ingest_file(cat, scraped_url, ctx.chunk_size, ctx.chunk_overlap)
                    ingested_count += 1
                
                # Send progress update
                cat.send_ws_message(f"Ingested {ingested_count}/{len(ctx.scraped_pages)} pages - Currently processing: {scraped_url}")
                
            except Exception as e:
                failed_count += 1
                log.error(f"Page ingestion failed: {scraped_url} - {str(e)}")
                # Continue with next page even if one fails
        
        log.info(f"Ingestion completed: {ingested_count} successful, {failed_count} failed")
        response: str = f"{ingested_count} URLs successfully imported, {failed_count} failed"

    except Exception as e:
        log.error(f"ScrapyCat operation failed: {str(e)}")
        response = f"ScrapyCat failed: {str(e)}"
    finally:
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


def validate_url(url: str) -> bool:
    # Check if the URL is valid, allowing for subdomains and handling domains without protocols
    url = url.strip()
    
    # If it doesn't have a protocol, it might be a domain with or without a path
    if not url.startswith(('http://', 'https://')):
        # Check if it's a valid domain format (with optional path)
        domain_regex: re.Pattern = re.compile(
            r"^([a-z0-9-]+\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
        )
        return re.match(domain_regex, url) is not None
    
    # If it has a protocol, validate as full URL
    regex: re.Pattern = re.compile(
        r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
    )
    return re.match(regex, url) is not None


def crawl_page(ctx: ScrapyCatContext, cat: StrayCat, page: str, depth: int) -> List[Tuple[str, int]]:
    """Thread-safe page crawling function - now stores content for later sequential ingestion"""
    with ctx.visited_lock:
        if page in ctx.visited_pages:
            return []
        ctx.visited_pages.add(page)
    
    # Check robots.txt compliance for this page
    if not is_url_allowed_by_robots(ctx, page):
        log.info(f"Page blocked by robots.txt, skipping: {page}")
        return []
    
    new_urls: List[Tuple[str, int]] = []
    try:
        response: str = ctx.session.get(page).text
        soup: BeautifulSoup = BeautifulSoup(response, "html.parser")
        
        # Store scraped page for later sequential ingestion
        with ctx.scraped_pages_lock:
            ctx.scraped_pages.append(page)
            # Send progress update for scraping
            current_count: int = len(ctx.scraped_pages)
            cat.send_ws_message(f"Scraped {current_count} pages - Currently scraping: {page}")
        
        urls: List[str] = [link["href"] for link in soup.select("a[href]")]

        valid_urls: List[str] = []
        for url in urls:
            if "#" in url:
                # Skip anchor links
                continue

            # Handle absolute vs relative URLs correctly
            if url.startswith(("http://", "https://")):
                # URL is already absolute, use it as-is
                new_url: str = url
            else:
                # URL is relative, join with current page
                new_url = urllib.parse.urljoin(page, url)

            parsed_new_url: urllib.parse.ParseResult = urllib.parse.urlparse(new_url)
            new_url_domain: str = normalize_domain(parsed_new_url.netloc)

            # Check if URL is allowed
            is_root_domain: bool = new_url_domain in ctx.root_domains  # Can crawl recursively
            is_allowed_domain: bool = new_url_domain in ctx.allowed_domains  # Single page only
            
            if not (is_root_domain or is_allowed_domain):
                continue

            # Check if URL matches any of the allowed paths (only for root domains)
            if is_root_domain and ctx.allowed_paths:
                path_allowed: bool = any(
                    parsed_new_url.path.startswith(allowed_path)
                    for allowed_path in ctx.allowed_paths
                )
                if not path_allowed:
                    continue

            # Check robots.txt compliance
            if not is_url_allowed_by_robots(ctx, new_url):
                log.debug(f"URL blocked by robots.txt: {new_url}")
                continue

            # Skip URLs with GET parameters if the setting is enabled
            if ctx.skip_get_params and "?" in new_url:
                continue
            skip_endswith: Tuple[str, ...] = (
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".svg",
                ".webp",
                ".ico",
                ".zip",
                ".ods",
                ".xls",
                ".p7m",
                ".rar",
                ".mp3",
                ".xml",
                ".7z",
                ".exe",
            )

            # Skip image URLs and zip files
            if new_url.lower().endswith(
                skip_endswith
            ):
                continue

            # Handle PDFs based on settings
            if new_url.lower().endswith(".pdf"):
                if ctx.ingest_pdf:
                    valid_urls.append(new_url)
                continue

            valid_urls.append(new_url)

        # Process found URLs: scrape allowed domains immediately, queue root domains for recursion
        recursive_urls: List[str] = []
        for url in valid_urls:
            parsed_url: urllib.parse.ParseResult = urllib.parse.urlparse(url)
            url_domain: str = normalize_domain(parsed_url.netloc)
            
            if url_domain in ctx.root_domains:
                # Root domain URL - add for recursive crawling
                recursive_urls.append(url)
            elif url_domain in ctx.allowed_domains:
                # Allowed domain URL - scrape immediately but don't recurse
                with ctx.visited_lock:
                    if url not in ctx.visited_pages:
                        ctx.visited_pages.add(url)
                        # Add to scraped pages for ingestion
                        with ctx.scraped_pages_lock:
                            ctx.scraped_pages.append(url)

        # Batch check for unvisited URLs to reduce lock overhead
        unvisited_urls: List[Tuple[str, int]] = []
        with ctx.visited_lock:
            for url in recursive_urls:
                if url not in ctx.visited_pages:
                    unvisited_urls.append((url, depth + 1))
        
        # Add unvisited URLs to new_urls
        new_urls.extend(unvisited_urls)
                            
    except Exception as e:
        log.error(f"Page crawl failed: {page} - {str(e)}")
    
    return new_urls


def crawler(ctx: ScrapyCatContext, cat: StrayCat, start_urls: List[str]) -> None:
    """Multi-threaded crawler using ThreadPoolExecutor - supporting multiple starting URLs"""

    with ThreadPoolExecutor(max_workers=ctx.max_workers) as executor:
        # Track submitted futures and their depths
        future_to_url: Dict[Any, Tuple[str, int]] = {}
        
        # Submit all initial URLs
        for start_url in start_urls:
            future = executor.submit(crawl_page, ctx, cat, start_url, 0)
            future_to_url[future] = (start_url, 0)
        
        while future_to_url:
            # Check max_pages limit
            with ctx.visited_lock:
                if ctx.max_pages != -1 and len(ctx.visited_pages) >= ctx.max_pages:
                    log.info(f"Max pages limit reached: {ctx.max_pages} pages")
                    break
            
            # Process completed futures with timeout
            completed_futures: List[Any] = []
            try:
                for future in as_completed(future_to_url, timeout=10):
                    completed_futures.append(future)
                    break  # Process one at a time to check limits frequently
            except TimeoutError:
                # If timeout occurs, continue to check for any completed futures
                for future in list(future_to_url.keys()):
                    if future.done():
                        completed_futures.append(future)
                
                # If no futures completed, continue waiting
                if not completed_futures:
                    continue
                    
            for future in completed_futures:
                url, depth = future_to_url.pop(future)
                
                try:
                    new_urls: List[Tuple[str, int]] = future.result()
                    
                    # Submit new URLs for crawling
                    for new_url, new_depth in new_urls:
                        # Check limits before submitting new tasks
                        with ctx.visited_lock:
                            if ctx.max_pages != -1 and len(ctx.visited_pages) >= ctx.max_pages:
                                break
                                
                        if (ctx.max_depth == -1 or new_depth <= ctx.max_depth):
                            future = executor.submit(crawl_page, ctx, cat, new_url, new_depth)
                            future_to_url[future] = (new_url, new_depth)
                            
                except Exception as e:
                    log.error(f"URL processing failed: {url} (depth {depth}) - {str(e)}")