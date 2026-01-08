import subprocess
import json
from typing import Any
from cat.log import log

# crawl4ai imports
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    log.warning("crawl4ai not available. Install it to use advanced crawling features.")


def run_crawl4ai_setup(cat: Any) -> str:
    """Setup crawl4ai dependencies and configuration"""
    try:
        # Runs the setup command just like in the shell
        subprocess.run(["crawl4ai-setup"], check=True)
        subprocess.run(["playwright", "install"], check=True)
        subprocess.run(["playwright", "install-deps"], check=True)
        
        log.info("Crawl4AI setup completed successfully.")
        return "Crawl4AI setup completed successfully."
    except subprocess.CalledProcessError as e:
        log.error(f"Error during Crawl4AI setup: {e}")
        return "Error during Crawl4AI setup."
    except FileNotFoundError:
        msg = "crawl4ai-setup or playwright command not found. Make sure crawl4ai is installed."
        log.error(msg)
        return msg


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


async def crawl4ai_get_html(url: str, cat: Any, wait_time: int = 0) -> str:
    """Use crawl4ai to get the rendered HTML of a page"""
    if not CRAWL4AI_AVAILABLE:
        raise ImportError("crawl4ai is not available. Please install it first.")
    
    try:
        async with AsyncWebCrawler() as crawler:
            run_config = CrawlerRunConfig()
            if wait_time > 0:
                 # Wait for network to be idle (all requests finished)
                 run_config.wait_until = "networkidle"
                 # Also add a delay to ensure content is rendered
                 run_config.delay_before_return_html = wait_time
            
            result = await crawler.arun(url, config=run_config)
            
            if not result.success:
                error_msg = result.error_message if hasattr(result, "error_message") else "Unknown error"
                
                # Check for download error in the result message
                if "Download is starting" in error_msg:
                     # log.info(f"Crawl4AI detected download link, skipping HTML extraction: {url}")
                     return ""
                
                log.warning(f"Crawl4AI reported failure for {url}: {error_msg}")
                # If it failed, we might still have HTML, but usually not.
                # Raise exception to trigger fallback
                raise Exception(f"Crawl4AI failed: {error_msg}")
                
            return result.html
            
    except Exception as e:
        # Catch specific navigation errors or others
        error_str = str(e)
        
        # Handle file downloads gracefully
        if "Download is starting" in error_str:
            # log.info(f"Crawl4AI detected download link, skipping HTML extraction: {url}")
            return ""
            
        if "ACS-GOTO" in error_str:
            log.warning(f"Crawl4AI navigation error for {url}: {error_str}")
        else:
            log.warning(f"Crawl4AI error for {url}: {error_str}")
        raise e