from cat.mad_hatter.decorators import hook
from typing import Dict, Set, Tuple
from cat.log import log
from bs4 import BeautifulSoup
import requests
import urllib.parse
from cat.looking_glass.stray_cat import StrayCat
from queue import Queue

class ScrapyCatContext:
    def __init__(self) -> None:
        self.internal_links: Set[str] = set()  # Set of internal URLs on the site (unique)
        self.visited_pages: Set[str] = set()   # Set of visited pages during crawling
        self.queue: Queue[Tuple[str, int]] = Queue()  # Queue of (url, depth) tuples for BFS
        self.root_url: str = ""           # Root URL of the site
        self.ingest_pdf: bool = False      # Whether to ingest PDFs
        self.skip_get_params: bool = False # Skip URLs with GET parameters
        self.base_path: str = ""          # Base path for URL filtering
        self.max_depth: int = 0           # Max recursion/crawling depth


@hook(priority=10)
def agent_fast_reply(fast_reply: Dict, cat: StrayCat) -> Dict:

    settings = cat.mad_hatter.get_plugin().load_settings()

    # Initialize context for this run
    ctx = ScrapyCatContext()
    ctx.ingest_pdf = settings["ingest_pdf"]
    ctx.skip_get_params = settings["skip_get_params"]
    ctx.max_depth = settings["max_depth"]

    return_direct = False
    # Get user message
    user_message: str = cat.working_memory["user_message_json"]["text"]

    if user_message.startswith("@scrapycat"):

        full_url = user_message.split(" ")[1]
        if full_url.endswith("/"):
            full_url = full_url[:-1]

        # Extract base path from URL if present
        parsed_url = urllib.parse.urlparse(full_url)
        ctx.base_path = parsed_url.path

        # Set root_url to just the scheme and netloc (domain)
        ctx.root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Start crawling from the root URL
        crawler(ctx, ctx.root_url)
        successful_imports = 0

        # Ingest all found internal links
        for link in ctx.internal_links:
            try:
                cat.rabbit_hole.ingest_file(cat, link, 400, 100)
                successful_imports += 1
            except Exception as e:
                log.error(f"Error ingesting {link}: {str(e)}")
        return_direct = True
        response: str = f"{successful_imports} of {len(ctx.internal_links)} URLs successfully imported in rabbit hole!"

    # Manage response
    if return_direct:
        return {"output": response}

    return fast_reply


def crawler(ctx: ScrapyCatContext, start_url: str) -> None:
    """
    Crawls a webpage to find its internal/external linked URLs using BFS.
    - Only internal links are followed.
    - Skips images, archives, and optionally GET params.
    - Handles PDFs based on settings.
    - Respects max_depth:
        - max_depth == -1: unlimited crawling (default behavior)
        - max_depth == 0: only analyze the starting link
        - max_depth > 0: crawl up to max_depth levels
    """
    

    ctx.queue = Queue()
    ctx.queue.put((start_url, 0))  # (url, depth)

    while not ctx.queue.empty():
        page, depth = ctx.queue.get()
        if page in ctx.visited_pages:
            continue
        ctx.visited_pages.add(page)

        # Handle max_depth logic
        # -1: unlimited, 0: only starting link, >0: up to max_depth
        if ctx.max_depth != -1 and depth > ctx.max_depth:
            continue

        try:
            # Only crawl internal pages (relative or under root_url)
            if page.startswith("/") or page.startswith(f"{ctx.root_url}"):
                log.warning("Crawling page: " + page)
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0",
                }
                response = requests.get(page, headers=headers).text
                soup = BeautifulSoup(response, "html.parser")
                urls = [link["href"] for link in soup.select("a[href]")]

                for url in urls:
                    if "#" in url:
                        # Skip anchor links
                        continue
                    # Normalize URL (handles relative and absolute)
                    new_url = urllib.parse.urljoin(ctx.root_url, url)
                    if not new_url.startswith(ctx.root_url):
                        # External link
                        # TODO ADD A SETTING TO DECIDE IF IGNORE OR NOT
                        continue

                    # Check if URL matches the base path filter (if set)
                    if ctx.base_path and not new_url.replace(ctx.root_url, "").startswith(ctx.base_path):
                        continue

                    # Skip URLs with GET parameters if the setting is enabled
                    if ctx.skip_get_params and "?" in new_url:
                        continue

                    # Skip image URLs and zip files
                    if new_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.zip')):
                        continue

                    # Handle PDFs based on settings
                    if new_url.endswith(".pdf"):
                        if ctx.ingest_pdf:
                            ctx.internal_links.add(new_url)
                        continue

                    # Add to internal links set
                    ctx.internal_links.add(new_url)
                    # Only queue for crawling if:
                    # - max_depth == -1 (unlimited)
                    # - or next depth <= max_depth
                    # - and not already visited
                    if (
                        (ctx.max_depth == -1 or depth + 1 <= ctx.max_depth)
                        and new_url not in ctx.visited_pages
                    ):
                        ctx.queue.put((new_url, depth + 1))
        except Exception as e:
            log.warning(f"Error crawling {page}: {e}")
