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


@hook(priority=10)
def agent_fast_reply(fast_reply, cat) -> Dict:
    global root_url
    global ingest_pdf
    settings = cat.mad_hatter.get_plugin().load_settings()
    if settings["ingest_pdf"]:
        ingest_pdf = True
    return_direct = False
    # Get user message
    user_message = cat.working_memory["user_message_json"]["text"]

    if user_message.startswith("scrapycat"):
        root_url = user_message.split(" ")[1]
        if root_url.endswith("/"):
            root_url = root_url[:-1]
        crawler(root_url)
        for link in internal_links:
            cat.rabbit_hole.ingest_file(cat, link, 400, 100)
        return_direct = True
        response = str(len(internal_links)) + " URLs imported in rabbit hole!"

    # Manage response
    if return_direct:
        print(internal_links)
        return {"output": response}

    return fast_reply


def crawler(page):
    """Crawls a webpage to find its internal/external linked URLs."""
    global internal_links, visited_pages, queue, root_url, ingest_pdf
    try:
        if page.startswith("/") or page.startswith(f"{root_url}"):

            log.warning("Crawling page: " + page)
            response = requests.get(page).text
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
                        if new_url.endswith(".pdf"):
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
