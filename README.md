# Description

This plugin for the [Cheshire Cat Project](https://github.com/pieroit/cheshire-cat) allows you to scrape an entire website and ingest all pages and PDFs into Rabbithole. Image files are automatically skipped during the scraping process.

# Usage

After installation, send a message with `@scrapycat` followed by the website URL to scrape the website (recursively).

The ingest phase may be long, you need to wait for the cat's response with the number of URLs/PDFs successfully ingested. If some URLs fail to be ingested (due to server disconnections or other errors), the plugin will continue processing the remaining URLs and report how many were successful.

## Basic Usage

- `@scrapycat www.example.com - Scrape all pages`
- `@scrapycat www.example.com/docs`- Scrape only pages under /docs

## Advanced Usage

Multiple starting URLs with allowed external roots:

```bash
@scrapycat <url1> [url2 ...] [--allow <allowed_url1> [allowed_url2 ...]]
```

Example:

```bash
@scrapycat https://www.example.com www.example2.com/subpath --allow external.example.com https://external.com
```

- Starts crawling from both` example.com` and `example2.com/subpath`
- Also allows scraping pages from external.example.com (only specific pages, not the entire domain)
- The ingest phase may take time. The plugin reports the number of successfully ingested URLs/PDFs, continuing even if some fail

# Settings

On the plugin settings you can set:

## Basic

- Ingest PDF: Include PDFs in the ingestion
- Skip GET Parameters: Ignore URLs with ?param=value to prevent duplicates or infinite loops
- _Use Crawl4AI_: Enables Crawl4AI parsing and Markdown ingestion (requires setup)
- Follow Robots.txt: Only accept URLs allowed by robots.txt (default False)
- Max Depth: How many levels of links to follow:
  - `-1`: No limit
  - `0`: Only the starting page
  - `N > 0`: Up to N levels deep
- Max Pages: Maximum number of pages to crawl:
  - `-1`: No limit
  - `N > 0`: Up to N pages
- Allowed Extra Roots: Comma-separated list of additional root URLs

## Performance

- Maximum Concurrent Workers: Number of parallel workers (default 1)
- Text Chunk Size: Size of content chunks for ingestion (default 512)
- Text Chunk Overlap: Overlap between consecutive chunks (default 128)

## Scheduling

- Scheduled Command: Complete command to run daily, e.g., `@scrapycat https://www.example.com --allow external.it` -> leave empty to remove the job
- Schedule Hour: UTC hour to start (default 2)
- Schedule Minute: Minute to start (default 0)

> Saving settings automatically updates the WhiteRabbit scheduler

# Setup

First-time setup for Crawl4AI:

```bash
@scrapycat crawl4ai-setup
```

Installs required packages. Wait for the "Crawl4AI setup completed successfully." message.

# Hooks

The plugin provides three hooks that allow other plugins to interact with the scraping process:

## scrapycat_before_scrape
Executed before the scraping process begins.

**Parameters:**
- `context` (Dict[str, Any]): Contains session information including:
  - `session_id` (str): Unique identifier for the scraping session
  - `command` (str): The original command that triggered the scraping
  - `scheduled` (bool): Whether this is a scheduled run (prevents websocket messages)
  - `scraped_pages` (List[str]): List of successfully scraped page URLs (initially empty)
  - `failed_pages` (List[str]): List of URLs that failed to scrape (initially empty)
  - `chunk_size` (int): Size of content chunks for ingestion
  - `chunk_overlap` (int): Overlap between consecutive chunks
- `cat` (StrayCat): The cat instance

**Usage:** Allows preprocessing or validation before scraping starts.

## scrapycat_after_crawl
Executed after the crawling phase is complete but before ingestion begins.

**Parameters:**
- `context` (Dict[str, Any]): Contains updated session information including:
  - `session_id` (str): Unique identifier for the scraping session
  - `command` (str): The original command that triggered the scraping
  - `scheduled` (bool): Whether this is a scheduled run (prevents websocket messages)
  - `scraped_pages` (List[str]): List of successfully scraped page URLs (populated after crawling)
  - `failed_pages` (List[str]): List of URLs that failed to scrape (populated if any failures occurred)
  - `chunk_size` (int): Size of content chunks for ingestion
  - `chunk_overlap` (int): Overlap between consecutive chunks
- `cat` (StrayCat): The cat instance

**Usage:** Allows processing of the crawled URLs list or cleanup operations before ingestion.

## scrapycat_after_scrape
Executed after the entire scraping and ingestion process is complete.

**Parameters:**
- `context` (Dict[str, Any]): Contains final session information including:
  - `session_id` (str): Unique identifier for the scraping session
  - `command` (str): The original command that triggered the scraping
  - `scheduled` (bool): Whether this is a scheduled run (prevents websocket messages)
  - `scraped_pages` (List[str]): List of successfully scraped page URLs (final list)
  - `failed_pages` (List[str]): List of URLs that failed to scrape (final list)
  - `chunk_size` (int): Size of content chunks for ingestion
  - `chunk_overlap` (int): Overlap between consecutive chunks
- `cat` (StrayCat): The cat instance

**Usage:** Allows post-processing, cleanup, or notification operations after scraping completion.

## Scheduled Parameter

The plugin includes a `scheduled` parameter in the processing function that prevents websocket errors when running automated scheduled jobs. When `scheduled=True`, progress messages are not sent via websocket to avoid logging errors during unattended operations.
