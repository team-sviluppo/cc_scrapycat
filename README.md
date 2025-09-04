# What is this?

This is a plugin for the [Cheshire Cat Project](https://github.com/pieroit/cheshire-cat), that allow to scrape an entire website and ingest in rabbithole all website pages and PDFs. Image files are automatically skipped during the scraping process

# Usage

After plugin installation you need to type `@scrapycat` followed by the website URL.

You can specify a base path in the URL to only process pages under that path:

- `@scrapycat www.dominio.it` - processes all pages on the site
- `@scrapycat www.dominio.it/pippo` - only processes pages under the /pippo path

The ingest phase may be long, you need to wait for the cat's response with the number of URLs/PDFs successfully ingested. If some URLs fail to be ingested (due to server disconnections or other errors), the plugin will continue processing the remaining URLs and report how many were successful.

# Settings

On the plugin settings you can set:

- **Ingest PDF**: If this setting is enabled, the plugin will also ingest PDFs found on the website.
- **Skip GET Parameters**: If this setting is enabled, the plugin will skip URLs that contain GET parameters (URLs with a question mark, like "example.com/page?param=value"). This is useful to avoid duplicate content and prevent crawling dynamic pages that might generate infinite loops.
- **Max Depth**: Controls how many levels of links the scraper will follow from the starting page.
  - `-1`: No limit (standard behavior). The scraper will follow all nested links and crawl the entire site.
  - `0`: Only the starting page is processed; no links are followed.
  - `N > 0`: The scraper will follow links up to N levels deep from the starting page.
- **Max Pages**: Controls the maximum number of pages to crawl.
  - `-1`: No limit (standard behavior). The scraper will follow all links until there are no more to follow.
  - `N > 0`: The scraper will stop after crawling N pages.
- **Allowed Extra Roots**: A comma-separated list of additional root URLs that the scraper is allowed to follow if found while crawling from the starting url. This is useful for sites with multiple subdomains or (un)related domains.
- **_Use Crawl4AI_**: if enabled the default url and pdf parsing are substituted with crawl4ai (need setup to work) and data are sent in rabbithole in markdown

# Examples

Process all pages on a site:

```
@scrapycat https://cheshire-cat-ai.github.io
```

Process only pages under a specific path:

```
@scrapycat https://cheshire-cat-ai.github.io/docs
```

This will only process URLs that start with "/docs", such as "/docs/installation", "/docs/usage", etc.

Setup crawl4ai (only first time):

```
@scrapycat crawl4ai-setup
```

This command install all packages needs for crawl4ai, wait some minutes to receive the "Crawl4AI setup completed successfully." message
