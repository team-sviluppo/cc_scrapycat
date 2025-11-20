from typing import List, Tuple, Any, Dict
import urllib.parse
from bs4 import BeautifulSoup
from cat.log import log
from cat.looking_glass.stray_cat import StrayCat
from concurrent.futures import ThreadPoolExecutor, as_completed
from .context import ScrapyCatContext
from ..utils.url_utils import normalize_domain
from ..utils.robots import is_url_allowed_by_robots


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
                ".odt",
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