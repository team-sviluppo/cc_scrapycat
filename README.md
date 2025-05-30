# What is this?

This is a plugin for the [Cheshire Cat Project](https://github.com/pieroit/cheshire-cat), that allow to scrape an entire website and ingest in rabbithole all website pages and PDFs. Image files are automatically skipped during the scraping process

# Usage

After plugin installation you need to digit scrapycat url

The URL must be the website root url (homepage).
The ingest phase myq be long, you need to wait the cat response with number of urls/pdf ingested

# Settings

On the plugin settings you can set:

- **Ingest PDF**: If this setting is enabled, the plugin will also ingest PDFs found on the website.
- **Base Path**: If set, the plugin will only process URLs that start with this path. For example, if you set "/docs", only URLs like "/docs/page1" will be processed, while "/about" will be skipped. Leave empty to process all URLs.

# Example

"scrapycat https://cheshire-cat-ai.github.io/docs/"
