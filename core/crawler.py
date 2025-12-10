import time
from typing import List, Tuple, Any, Dict
import urllib.parse
import threading
import requests
from bs4 import BeautifulSoup
from cat.log import log
from cat.looking_glass.stray_cat import StrayCat
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from .context import ScrapyCatContext
from ..utils.url_utils import normalize_domain
from ..utils.robots import is_url_allowed_by_robots


# Thread-local storage for session objects
_thread_local = threading.local()


def get_thread_session() -> requests.Session:
    """Get or create a thread-local requests session for thread-safe parallel requests"""
    if not hasattr(_thread_local, 'session'):
        _thread_local.session = requests.Session()
        _thread_local.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0"
        })
    return _thread_local.session


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
        # Use thread-local session for true parallel requests
        session = get_thread_session()
        response: str = session.get(page).text
        soup: BeautifulSoup = BeautifulSoup(response, "html.parser")
        
        # Store scraped page for later sequential ingestion
        with ctx.scraped_pages_lock:
            ctx.scraped_pages.append(page)
            current_count: int = len(ctx.scraped_pages)
            
        # Send progress update for scraping (only if not scheduled)
        # Done outside the lock to prevent blocking other threads
        # Throttled to avoid flooding the websocket channel
        if not ctx.scheduled:
            should_send = False
            with ctx.update_lock:
                now = time.time()
                if now - ctx.last_update_time > 0.5:  # Update every 0.5 seconds max
                    ctx.last_update_time = now
                    should_send = True
            
            if should_send:
                # Get worker name for debugging
                worker_name = threading.current_thread().name
                # Simplify worker name if it's the standard ThreadPoolExecutor format
                if "ThreadPoolExecutor" in worker_name:
                    try:
                        # Extract just the number if possible, e.g. "ThreadPoolExecutor-0_1" -> "Worker 1"
                        parts = worker_name.split("_")
                        if len(parts) > 1:
                            worker_name = f"Worker {parts[-1]}"
                    except:
                        pass
                
                cat.send_ws_message(f"Scraped {current_count} pages - {worker_name} scraping: {page}")
        
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
            if ctx.follow_robots_txt and not is_url_allowed_by_robots(ctx, new_url):
                log.debug(f"URL blocked by robots.txt: {new_url}")
                continue

            # Skip URLs with GET parameters if the setting is enabled
            if ctx.skip_get_params and "?" in new_url:
                continue

            # Skip URLs with configured file extensions
            if ctx.skip_extensions and new_url.lower().endswith(tuple(ctx.skip_extensions)):
                continue

            # Handle PDFs based on settings
            if new_url.lower().endswith(".pdf"):
                if ctx.ingest_pdf:
                    # PDFs should be added to scraped pages but not processed for URL extraction
                    should_add_pdf = False
                    with ctx.visited_lock:
                        if new_url not in ctx.visited_pages:
                            ctx.visited_pages.add(new_url)
                            should_add_pdf = True
                    
                    if should_add_pdf:
                        with ctx.scraped_pages_lock:
                            ctx.scraped_pages.append(new_url)
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
                should_add = False
                with ctx.visited_lock:
                    if url not in ctx.visited_pages:
                        ctx.visited_pages.add(url)
                        should_add = True
                
                if should_add:
                    # Add to scraped pages for ingestion
                    with ctx.scraped_pages_lock:
                        ctx.scraped_pages.append(url)

        # Batch check for unvisited URLs to reduce lock overhead
        unvisited_urls: List[Tuple[str, int]] = []
        # We don't strictly need the lock here because crawl_page handles the authoritative check
        # This is just a pre-filter to avoid submitting too many duplicate tasks
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
            # Check max_pages limit before processing more futures
            with ctx.visited_lock:
                if ctx.max_pages != -1 and len(ctx.visited_pages) >= ctx.max_pages:
                    log.info(f"Max pages limit reached: {ctx.max_pages} pages")
                    # Cancel remaining futures
                    for remaining_future in future_to_url.keys():
                        remaining_future.cancel()
                    break
            
            # Collect all futures that complete within the timeout window
            # This allows true parallel processing instead of one-at-a-time
            completed_in_batch: List[Any] = []
            
            # Use wait() instead of as_completed() to efficiently wait for the first batch of results
            # This avoids creating a new iterator and checking .done() on all futures repeatedly
            done, not_done = wait(future_to_url.keys(), timeout=ctx.page_timeout, return_when=FIRST_COMPLETED)
            
            if done:
                completed_in_batch = list(done)
            else:
                # Timeout occurred - no futures completed
                # Cancel all remaining futures and exit gracefully
                log.warning(f"Timeout waiting for {len(future_to_url)} futures - cancelling remaining tasks")
                for future in list(future_to_url.keys()):
                    future.cancel()
                    url, depth = future_to_url.pop(future)
                    ctx.failed_pages.append(url)
                    log.warning(f"URL cancelled due to timeout: {url}")
                break
            
            # Process all completed futures in this batch
            for completed_future in completed_in_batch:
                if completed_future not in future_to_url:
                    continue  # Already processed
                    
                url, depth = future_to_url.pop(completed_future)
                
                try:
                    new_urls: List[Tuple[str, int]] = completed_future.result()
                    
                    # Submit new URLs for crawling (if under limits)
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
                    ctx.failed_pages.append(url)