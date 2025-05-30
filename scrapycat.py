from cat.mad_hatter.decorators import tool, hook
from typing import Dict
from cat.log import log
from bs4 import BeautifulSoup
import requests
import re

internal_links = []  # List of internal URLs on the site
visited_pages = []  # List of visited pages during crawling
queue = []  # Queue of unexplored pages
root_url = ""  # Root URL of the site
ingest_pdf = False
base_path = ""  # Base path for URL filtering


@hook(priority=10)
def agent_fast_reply(fast_reply, cat) -> Dict:
    global root_url, ingest_pdf, base_path, internal_links, visited_pages, queue
    settings = cat.mad_hatter.get_plugin().load_settings()
    if settings["ingest_pdf"]:
        ingest_pdf = True
    else:
        ingest_pdf = False
    return_direct = False
    # Get user message
    user_message = cat.working_memory["user_message_json"]["text"]

    if user_message.startswith("scrapycat"):
        # Reset all global variables to ensure a clean state for each run
        internal_links = []
        visited_pages = []
        queue = []
        base_path = ""
        root_url = ""
        full_url = user_message.split(" ")[1]
        if full_url.endswith("/"):
            full_url = full_url[:-1]

        # Extract base path from URL if present
        import urllib.parse
        parsed_url = urllib.parse.urlparse(full_url)
        base_path = parsed_url.path

        # Set root_url to just the scheme and netloc (domain)
        root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        crawler(root_url)
        successful_imports = 0
        for link in internal_links:
            try:
                cat.rabbit_hole.ingest_file(cat, link, 400, 100)
                successful_imports += 1
            except Exception as e:
                log.error(f"Error ingesting {link}: {str(e)}")
        return_direct = True
        response = f"{successful_imports} of {len(internal_links)} URLs successfully imported in rabbit hole!"

    # Manage response
    if return_direct:
        return {"output": response}

    return fast_reply


def crawler(page):
    """Crawls a webpage to find its internal/external linked URLs."""
    global internal_links, visited_pages, queue, root_url, ingest_pdf, base_path
    try:
        if page.startswith("/") or page.startswith(f"{root_url}"):

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
                if url.startswith("/") or url.startswith(f"{root_url}"):
                    if url.startswith("/"):
                        new_url = f"{root_url}{url}"
                    else:
                        new_url = url
                    if new_url not in internal_links:
                        # Check if URL matches the base path filter (if set)
                        if base_path and not new_url.replace(root_url, "").startswith(base_path):
                            continue

                        # Skip image URLs and zip files
                        if new_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.zip')):
                            continue
                        # Handle PDFs based on settings
                        elif new_url.endswith(".pdf"):
                            if ingest_pdf:
                                internal_links.append(new_url)
                        else:
                            internal_links.append(new_url)
                else:
                    # external link
                    continue

            for i in range(len(internal_links)):
                if (
                    internal_links[i] not in visited_pages
                    and internal_links[i] not in queue
                ):
                    queue.append(internal_links[i])

            while len(queue) > 0:
                next_url = queue.pop()
                if next_url not in visited_pages:
                    visited_pages.append(next_url)
                    crawler(next_url)

    except Exception as e:
        pass
