from cat.mad_hatter.decorators import hook
from typing import Dict
from cat.log import log
from bs4 import BeautifulSoup
import requests
import urllib.parse

class ScrapyCatContext:
    def __init__(self):
        self.internal_links = []  # List of internal URLs on the site
        self.visited_pages = []  # List of visited pages during crawling
        self.queue = []  # Queue of unexplored pages
        self.root_url = ""  # Root URL of the site
        self.ingest_pdf = False
        self.skip_get_params = False  # Skip URLs with GET parameters
        self.base_path = ""  # Base path for URL filtering
        self.max_depth = 0  # Max recursion depth


@hook(priority=10)
def agent_fast_reply(fast_reply, cat) -> Dict:
    settings = cat.mad_hatter.get_plugin().load_settings()

    ctx = ScrapyCatContext()
    ctx.ingest_pdf = settings["ingest_pdf"]
    ctx.skip_get_params = settings["skip_get_params"]
    ctx.max_depth = settings["max_depth"]

    return_direct = False
    # Get user message
    user_message = cat.working_memory["user_message_json"]["text"]

    if user_message.startswith("scrapycat"):
        # Reset context for each run
        full_url = user_message.split(" ")[1]
        if full_url.endswith("/"):
            full_url = full_url[:-1]

        # Extract base path from URL if present
        parsed_url = urllib.parse.urlparse(full_url)
        ctx.base_path = parsed_url.path

        # Set root_url to just the scheme and netloc (domain)
        ctx.root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        crawler(ctx, ctx.root_url)
        successful_imports = 0
        for link in ctx.internal_links:
            try:
                cat.rabbit_hole.ingest_file(cat, link, 400, 100)
                successful_imports += 1
            except Exception as e:
                log.error(f"Error ingesting {link}: {str(e)}")
        return_direct = True
        response = f"{successful_imports} of {len(ctx.internal_links)} URLs successfully imported in rabbit hole!"

    # Manage response
    if return_direct:
        return {"output": response}

    return fast_reply


def crawler(ctx: ScrapyCatContext, page):
    """Crawls a webpage to find its internal/external linked URLs."""
    try:
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
                    # anchor link
                    continue
                if url.startswith("/") or url.startswith(f"{ctx.root_url}"):
                    if url.startswith("/"):
                        new_url = f"{ctx.root_url}{url}"
                    else:
                        new_url = url
                    if new_url not in ctx.internal_links:
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
                        elif new_url.endswith(".pdf"):
                            if ctx.ingest_pdf:
                                ctx.internal_links.append(new_url)
                        else:
                            ctx.internal_links.append(new_url)
                else:
                    # external link
                    continue

            for i in range(len(ctx.internal_links)):
                if (
                    ctx.internal_links[i] not in ctx.visited_pages
                    and ctx.internal_links[i] not in ctx.queue
                ):
                    ctx.queue.append(ctx.internal_links[i])

            while len(ctx.queue) > 0:
                next_url = ctx.queue.pop()
                if next_url not in ctx.visited_pages:
                    ctx.visited_pages.append(next_url)
                    crawler(ctx, next_url)

    except Exception as e:
        pass
