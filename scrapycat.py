from cat.mad_hatter.decorators import hook
from typing import Dict, Set, Tuple
from cat.log import log
from bs4 import BeautifulSoup
import requests
import urllib.parse
from cat.looking_glass.stray_cat import StrayCat
from queue import Queue
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

import re
import os
import asyncio

import subprocess


def run_crawl4ai_setup():
    try:
        # Runs the setup command just like in the shell
        subprocess.run(["crawl4ai-setup"], check=True)
        log.info("Crawl4AI setup completed successfully.")
        return "Crawl4AI setup completed successfully."
    except subprocess.CalledProcessError as e:
        log.error("Error during Crawl4AI setup:", e)
        return "Error during Crawl4AI setup."


class ScrapyCatContext:
    def __init__(self) -> None:
        self.internal_links: Set[str] = (
            set()
        )  # Set of internal URLs on the site (unique)
        self.visited_pages: Set[str] = set()  # Set of visited pages during crawling
        self.queue: Queue[Tuple[str, int]] = (
            Queue()
        )  # Queue of (url, depth) tuples for BFS
        self.root_url: str = ""  # Root URL of the site
        self.ingest_pdf: bool = False  # Whether to ingest PDFs
        self.skip_get_params: bool = False  # Skip URLs with GET parameters
        self.base_path: str = ""  # Base path for URL filtering
        self.max_depth: int = -1  # Max recursion/crawling depth (-1 for unlimited)
        self.max_pages: int = -1  # Max pages to crawl (-1 for unlimited)
        self.allowed_extra_roots: Set[str]  # Set of allowed root URLs for filtering
        self.use_crawl4ai: bool = False  # Whether to use crawl4ai for crawling


def clean_url(url: str) -> str:
    # Remove trailing slashes and normalize the URL
    return url.strip().rstrip("/")


@hook(priority=10)
def agent_fast_reply(fast_reply: Dict, cat: StrayCat) -> Dict:
    # Fixed Deprecation Warning: To get `text` use dot notation instead of dictionary keys, example:`obj.text` instead of `obj["text"]`
    user_message: str = cat.working_memory.user_message_json.text

    if not user_message.startswith("@scrapycat"):
        return fast_reply

    if user_message == "@scrapycat crawl4ai-setup":
        result = run_crawl4ai_setup()
        fast_reply["output"] = result
        return fast_reply

    settings = cat.mad_hatter.get_plugin().load_settings()

    # Initialize context for this run
    ctx = ScrapyCatContext()
    ctx.ingest_pdf = settings["ingest_pdf"]
    ctx.skip_get_params = settings["skip_get_params"]
    ctx.max_depth = settings["max_depth"]
    ctx.use_crawl4ai = settings["use_crawl4ai"]
    ctx.allowed_extra_roots = {
        clean_url(url)
        for url in settings["allowed_extra_roots"].split(",")
        if validate_url(url.strip())
    }
    ctx.max_pages = settings["max_pages"]

    full_url = clean_url(user_message.split(" ")[1])

    # Extract base path from URL if present
    parsed_url = urllib.parse.urlparse(full_url)
    ctx.base_path = parsed_url.path

    # Set root_url to just the scheme and netloc (domain)
    ctx.root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Start crawling from the root URL
    crawler(ctx, full_url)
    successful_imports = 0

    log.info("Totale links interni trovati: " + str(len(ctx.internal_links)))
    # Ingest all found internal links
    for link in ctx.internal_links:
        try:
            if ctx.use_crawl4ai:
                # Use crawl4ai for fetching and processing the page
                markdown_content = asyncio.run(crawl4i(link))
                output_file = "ocrcontent.md"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                metadata = {"url": link, "source": link}
                cat.rabbit_hole.ingest_file(cat, output_file, 1024, 256, metadata)
                os.remove(output_file)
            else:
                # Use default ingestion method
                cat.rabbit_hole.ingest_file(cat, link, 400, 100)
            successful_imports += 1
        except Exception as e:
            log.error(f"Error ingesting {link}: {str(e)}")
    response: str = (
        f"{successful_imports} of {len(ctx.internal_links)} URLs successfully imported in rabbit hole!"
    )

    return {"output": response}


def validate_url(url: str) -> bool:
    # Check if the URL is valid, allowing for subdomains (e.g., https://sub.domain.com)
    regex = re.compile(
        r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
    )
    return re.match(regex, url) is not None


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
        # Check max_pages limit before processing next page
        if ctx.max_pages != -1 and len(ctx.visited_pages) >= ctx.max_pages:
            log.warning(f"Reached max_pages limit of {ctx.max_pages}. Stopping crawl.")
            break

        # Handle max_depth logic
        # -1: unlimited, 0: only starting link, >0: up to max_depth
        if ctx.max_depth != -1 and depth > ctx.max_depth:
            continue

        if page in ctx.visited_pages:
            continue

        ctx.visited_pages.add(page)

        try:
            # Only crawl internal pages (relative or under root_url)
            if page.startswith("/") or page.startswith(f"{ctx.root_url}"):
                log.warning("Crawling page: " + page)
                # The current page is included in internal_links
                ctx.internal_links.add(page)
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

                    # Handle absolute vs relative URLs correctly
                    if url.startswith(("http://", "https://")):
                        # URL is already absolute, use it as-is
                        new_url = url
                    else:
                        # URL is relative, join with current page
                        new_url = urllib.parse.urljoin(page, url)

                    # Extract root URL from new_url for O(1) check
                    parsed_new_url = urllib.parse.urlparse(new_url)
                    new_url_root = f"{parsed_new_url.scheme}://{parsed_new_url.netloc}"

                    # Check if URL is internal (starts with root_url) or allowed (root is in allowed_extra_roots)
                    if (
                        new_url_root != ctx.root_url
                        and new_url_root not in ctx.allowed_extra_roots
                    ):
                        log.warning(
                            f"Skipping external link: {new_url} because root {new_url_root} is not in allowed roots"
                        )
                        continue

                    # Check if URL matches the base path filter (if set)
                    if ctx.base_path and not new_url.replace(
                        ctx.root_url, ""
                    ).startswith(ctx.base_path):
                        continue

                    # Skip URLs with GET parameters if the setting is enabled
                    if ctx.skip_get_params and "?" in new_url:
                        continue

                    # Skip image URLs and zip files
                    if new_url.lower().endswith(
                        (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".gif",
                            ".bmp",
                            ".svg",
                            ".webp",
                            ".ico",
                            ".zip",
                        )
                    ):
                        continue

                    # Handle PDFs based on settings
                    if new_url.endswith(".pdf"):
                        if ctx.ingest_pdf:
                            ctx.internal_links.add(new_url)
                        continue

                    # Decides whether to include this URL in internal_links / queue
                    next_depth = depth + 1
                    # If max_depth is set and the next depth would exceed it, we don't add it
                    # We directly compare next_depth > max_depth (without +1)
                    if ctx.max_depth != -1 and next_depth > ctx.max_depth:
                        # We don't add it to internal_links or the queue
                        continue

                    # Add to internal links set
                    ctx.internal_links.add(new_url)
                    # Add to queue for crawling if not yet visited
                    if new_url not in ctx.visited_pages:
                        ctx.queue.put((new_url, next_depth))
        except Exception as e:
            log.warning(f"Error crawling {page}: {e}")


async def crawl4i(url: str) -> str:
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
