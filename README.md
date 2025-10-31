# Description

This plugin for the [Cheshire Cat Project](https://github.com/pieroit/cheshire-cat) allows you to scrape an entire website and ingest all pages and PDFs into Rabbithole. Image files are automatically skipped during the scraping process.

# Usage

After installation, type `@scrapycat` followed by the website URL to scrape the website.

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
@scrapycat https://www.example.com https://www.example2.com/subpath --allow https://www.external.example.com
```

- Starts crawling from both` example.com` and `example2.com/subpath`
- Also allows scraping pages from external.example.com (only specific pages, not the entire domain)
- The ingest phase may take time. The plugin reports the number of successfully ingested URLs/PDFs, continuing even if some fail

# Settings



## Basic

- Ingest PDF: Include PDFs in the ingestion
- Skip GET Parameters: Ignore URLs with ?param=value to prevent duplicates or infinite loops
- _Use Crawl4AI_: Enables Crawl4AI parsing and Markdown ingestion (requires setup)
- Follow Robots.txt: Only accept URLs allowed by robots.txt (default False)
- Max Depth: How many levels of links to follow
  - `-1`: No limit
  - `0`: Only the starting page
  - `N > 0`: Up to N levels deep
- Max Pages: Maximum number of pages to crawl (-1 = no limit)
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

# Examples

## Basic

Scrape all pages:
```bash
@scrapycat https://cheshire-cat-ai.github.io
```

Scrape pages under a path:
```bash
@scrapycat https://cheshire-cat-ai.github.io/docs
```

## Advanced

Multiple starting URLs with allowed external roots:
@scrapycat https://www.example.com https://www.example2.com/subpath --allow https://www.external.example.com

# Setup

First-time setup for Crawl4AI:
@scrapycat crawl4ai-setup

Installs required packages. Wait for the "Crawl4AI setup completed successfully." message.
