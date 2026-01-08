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
## Log Schema

This plugin uses structured JSON logging to facilitate monitoring and debugging. All logs follow this base structure:

```json
{
  "component": "cc_scrapycat",
  "event": "<event_name>",
  "data": {
    ... <event_specific_data>
  }
}
```

### Event Types

| Event Name | Description | Data Fields |
|------------|-------------|-------------|
| `validation_warning` | Logged when an allowed URL is invalid | `url` |
| `command_error` | Logged when command validation fails | `error` |
| `crawl4ai_warning` | Logged when crawl4ai is requested but unavailable | `message` |
| `robots_loaded` | Logged when robots.txt is preloaded | `count` |
| `start` | Logged when scraping starts | `urls_count`, `max_pages`, `max_depth`, `workers`, `robots_txt`, `single_page_domains`, `recursive_domains` |
| `hook_error` | Logged when a hook execution fails | `hook`, `error` |
| `crawl_complete` | Logged when crawling is finished | `scraped_count`, `failed_count` |
| `crawl4ai_fallback` | Logged when crawl4ai fails and falls back to default | `url`, `error` |
| `ingestion_progress` | Logged during ingestion (websocket message) | `current`, `total`, `url` |
| `ingestion_error` | Logged when page ingestion fails | `url`, `error` |
| `ingestion_complete` | Logged when ingestion is finished | `success_count`, `failed_count` |
| `operation_error` | Logged when the entire operation fails | `error` |
| `page_blocked` | Logged when a page is blocked by robots.txt | `url` |
| `crawl4ai_page_fallback` | Logged when crawl4ai fails for a page | `url`, `error` |
| `dynamic_retry` | Logged when retrying for dynamic content | `url` |
| `robots_load_success` | Logged when robots.txt is loaded successfully | `domain`, `url` |
| `robots_load_failed` | Logged when robots.txt load fails | `url`, `error` |
| `robots_not_found` | Logged when robots.txt is not found | `domain` |
| `robots_error` | Logged when robots.txt processing errors | `domain`, `error` |
| `crawl4ai_setup_success` | Logged when crawl4ai setup completes successfully | `message` |
| `crawl4ai_setup_error` | Logged when crawl4ai setup fails | `error` |
| `crawl4ai_setup_not_found` | Logged when crawl4ai setup command is missing | `error` |
| `crawl4ai_failure` | Logged when crawl4ai fails to process a URL | `url`, `error` |
| `crawl4ai_navigation_error` | Logged when crawl4ai encounters navigation error | `url`, `error` |
| `crawl4ai_error` | Logged when crawl4ai encounters generic error | `url`, `error` |
| `schedule_removed` | Logged when a scheduled job is removed | `job_id` |
| `schedule_disabled` | Logged when scheduling is disabled | - |
| `schedule_updated` | Logged when schedule is updated | `command`, `hour`, `minute`, `current_utc` |
| `scheduler_status` | Logged to report scheduler running status | `running` |
| `scheduler_not_running` | Logged when scheduler is not running | - |
| `scheduler_jobs_count` | Logged to report total scheduled jobs | `count` |
| `job_scheduled` | Logged when a job is successfully scheduled | `job` |
| `job_next_run` | Logged to report next run time of a job | `next_run`, `time_until` |
| `job_scheduled_in_past` | Logged when job is scheduled in the past | - |
| `job_missing_next_run` | Logged when job has no next run time | - |
| `job_creation_failed` | Logged when job creation fails | `job_id` |
| `scheduler_debug_error` | Logged when scheduler debug check fails | `error` |
| `schedule_setup_error` | Logged when schedule setup fails | `error` |
| `settings_load_error` | Logged when settings load fails | `error` |
| `settings_save_error` | Logged when settings save fails | `error` |
| `bootstrap_schedule_setup` | Logged when setting up schedule at bootstrap | - |
| `settings_saved` | Logged when settings are saved | - |
| `schedule_updated_success` | Logged when schedule update succeeds | - |
| `schedule_update_error` | Logged when schedule update fails | `error` |
