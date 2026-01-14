# Description

This plugin for the [Cheshire Cat Project](https://github.com/pieroit/cheshire-cat) allows you to scrape an entire website and ingest all pages and PDFs into Rabbithole. Image files are automatically skipped during the scraping process.

# Usage

After installation, send a message with `@scrapycat` followed by the website URL to scrape the website (recursively).

The ingest phase may be long, you need to wait for the cat's response with the number of URLs/PDFs successfully ingested. If some URLs fail to be ingested (due to server disconnections or other errors), the plugin will continue processing the remaining URLs and report how many were successful.

## Basic Usage

- `@scrapycat www.example.com` - Scrape all pages
- `@scrapycat www.example.com/docs` - Scrape only pages under /docs

## Advanced Usage

Multiple starting URLs with allowed external roots:

```bash
@scrapycat <url1> [url2 ...] [--allow <allowed_url1> [allowed_url2 ...]]
```

Example:

```bash
@scrapycat https://www.example.com www.example2.com/subpath --allow external.example.com https://external.com
```

- Starts crawling from both `example.com` and `example2.com/subpath`
- Also allows scraping pages from `external.example.com` and `external.com` (only specific pages linked from the main sites, not recursively crawled)
- The ingest phase may take time. The plugin reports the number of successfully ingested URLs/PDFs, continuing even if some fail

# Settings

On the plugin settings you can set:

## Basic Settings

- **Ingest PDF**: Include PDFs in the ingestion
- **Skip GET Parameters**: Ignore URLs with ?param=value to prevent duplicates or infinite loops
- **Use Crawl4AI for Content Extraction**: Enables Crawl4AI for better content extraction and JavaScript rendering during ingestion (requires setup via `@scrapycat crawl4ai-setup`)
- **Follow Robots.txt**: Respect robots.txt files when crawling (default: False)
- **Max Depth**: How many levels of links to follow:
  - `-1`: No limit (default)
  - `0`: Only the starting page
  - `N > 0`: Up to N levels deep
- **Max Pages**: Maximum number of pages to crawl:
  - `-1`: No limit (default)
  - `N > 0`: Up to N pages
- **Allowed Extra Roots**: Comma-separated list of additional root URLs for single-page scraping from external domains
- **Skip Extensions**: File extensions to skip during crawling (default: `.jpg,.jpeg,.png,.gif,.bmp,.svg,.webp,.ico,.zip,.ods,.odt,.xls,.p7m,.rar,.mp3,.xml,.7z,.exe,.doc,.m4a,.crdownload,.odp,.ppt,.pptx`)
- **Page Timeout**: Maximum time in seconds to wait for pages to load (default: 30, range: 5-300)
- **User Agent**: User agent string for HTTP requests (default: Firefox 55.0)
- **Only Scheduled**: If enabled, `@scrapycat` commands in chat are ignored; only scheduled scraping runs (default: False)

## Performance Settings

- **Maximum Concurrent Workers**: Number of parallel workers for crawling (default: 1)
- **Text Chunk Size**: Size of content chunks for ingestion in characters (default: 512)
- **Text Chunk Overlap**: Overlap between consecutive chunks in characters (default: 128)

## Scheduling Settings

- **Scheduled Command**: Complete command to run daily, e.g., `@scrapycat https://www.example.com --allow external.it` (leave empty to disable scheduling)
- **Schedule Hour**: UTC hour to start scheduled job (0-23, default: 2)
- **Schedule Minute**: Minute to start scheduled job (0-59, default: 0)

> **Note:** Saving settings automatically updates the WhiteRabbit scheduler. The scheduled job will run at the specified UTC time each day.

# Crawl4AI Setup

For enhanced content extraction and JavaScript rendering support, set up Crawl4AI:

```bash
@scrapycat crawl4ai-setup
```

This command installs the required packages and dependencies. Wait for the "Crawl4AI setup completed successfully." message before enabling the feature in settings.

# Hooks

The plugin provides three hooks that allow other plugins to interact with the scraping process, with the `context` (Dict[str, Any]) parameter containing:

- `session_id` (str): Unique identifier for the scraping session
- `command` (str): The original command that triggered the scraping
- `scheduled` (bool): Whether this is a scheduled run (True) or chat command (False)
- `scraped_pages` (List[str]): List of successfully scraped page URLs (initially empty)
- `failed_pages` (List[str]): List of URLs that failed to scrape (initially empty)
- `ignored_pages` (List[str]): List of URLs that were scraped but ignored (initially empty)
- `chunk_size` (int): Size of content chunks for ingestion
- `chunk_overlap` (int): Overlap between consecutive chunks
- `page_timeout` (int): Timeout in seconds for page loading
- `skip_extensions` (List[str]): File extensions to skip
- `user_agent` (str): User agent string used for requests

> **Note:** Other plugins may attach additional temporary fields to the context by returning them in the hook. These fields will persist only for the current scraping session and will be available to subsequent hooks.

## scrapycat_before_scraping

Executed before the scraping process begins.

It allows preprocessing or validation before scraping starts.

## scrapycat_after_scraping

Executed after the scraping phase is complete but before ingestion begins.

It allows processing of the crawled URLs list or cleanup operations before ingestion.

## scrapycat_after_ingestion

Executed after the entire scraping and ingestion process is complete.

It allows post-processing, cleanup, or notification operations after scraping completion.


# Scheduled Operations

The plugin includes a `scheduled` parameter that controls websocket message behavior:
- When `scheduled=True` (automated scheduled jobs): Progress messages are not sent via websocket to avoid errors during unattended operations
- When `scheduled=False` (chat commands): Progress messages are sent to provide real-time feedback to the user

This ensures reliable operation for both interactive and automated scraping scenarios.
