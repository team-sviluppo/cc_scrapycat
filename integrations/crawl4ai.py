import subprocess
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