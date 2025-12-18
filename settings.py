from pydantic import BaseModel, Field, validator
from cat.mad_hatter.decorators import plugin


# Plugin settings
class PluginSettings(BaseModel):
    ingest_pdf: bool = Field(
        default=False,
        title="Ingest PDF files",
        description="Whether to ingest PDF files found during crawling"
    )
    skip_get_params: bool = Field(
        default=False,
        title="Skip URLs with GET parameters",
        description="Skip crawling URLs that contain GET parameters (?param=value)"
    )
    use_crawl4ai: bool = Field(
        default=False,
        title="Use crawl4ai for advanced crawling",
        description="Enable crawl4ai for better content extraction and JavaScript rendering"
    )
    use_crawl4ai_fallback: bool = Field(
        default=False,
        title="Use crawl4ai as fallback",
        description="If enabled, retries fetching pages with crawl4ai (and a wait time) if no links are found with standard scraping. Useful for dynamic pages."
    )
    follow_robots_txt: bool = Field(
        default=False,
        title="Follow robots.txt",
        description="Respect robots.txt files when crawling. If enabled, only crawl URLs allowed by robots.txt"
    )
    max_depth: int = Field(
        default=-1,
        title="Maximum crawling depth",
        description="Maximum recursion depth for crawling (-1 for unlimited)"
    )
    max_pages: int = Field(
        default=-1,
        title="Maximum pages to crawl",
        description="Maximum number of pages to crawl (-1 for unlimited)"
    )
    allowed_extra_roots: str = Field(
        default="",
        title="Allowed extra root URLs",
        description="Comma-separated list of additional allowed root URLs for external crawling"
    )
    max_workers: int = Field(
        default=1,
        title="Maximum concurrent workers",
        description="Number of concurrent threads for parallel crawling"
    )
    chunk_size: int = Field(
        default=512,
        title="Text chunk size",
        description="Size of text chunks for document ingestion (in characters)"
    )
    chunk_overlap: int = Field(
        default=128,
        title="Chunk overlap",
        description="Overlap between consecutive text chunks (in characters)"
    )
    scheduled_command: str = Field(
        default="",
        title="Scheduled ScrapyCat command",
        description="Full @scrapycat command to run on schedule (e.g., '@scrapycat https://example.com'). Leave empty to disable scheduling."
    )
    schedule_hour: int = Field(
        default=2,
        title="Schedule hour (24h format) UTC+0",
        description="Hour of the day to run the scheduled command (0-23)",
    )
    schedule_minute: int = Field(
        default=0,
        title="Schedule minute",
        description="Minute of the hour to run the scheduled command (0-59)",
    )
    skip_extensions: str = Field(
        default=".jpg,.jpeg,.png,.gif,.bmp,.svg,.webp,.ico,.zip,.ods,.odt,.xls,.p7m,.rar,.mp3,.xml,.7z,.exe,.doc,.m4a, .crdownload, .odp, ,ppt, .pptx",
        title="File extensions to skip",
        description="Comma-separated list of file extensions to skip during crawling (e.g., '.jpg,.png,.zip')"
    )
    page_timeout: int = Field(
        default=30,
        title="Page load timeout (seconds)",
        description="Maximum time to wait for a page to load before checking for other completed pages (in seconds)"
    )
    json_logs: bool = Field(
        default=False,
        title="Enable JSON logs",
        description="If enabled, logs will be formatted as JSON objects following a specific schema."
    )

    @validator('page_timeout')
    def validate_page_timeout(cls, v):
        """Validate that page timeout is reasonable (5-300 seconds)"""
        if not 5 <= v <= 300:
            raise ValueError('Page timeout must be between 5 and 300 seconds')
        return v

    @validator('schedule_hour')
    def validate_schedule_hour(cls, v):
        """Validate that schedule hour is between 0 and 23"""
        if not 0 <= v <= 23:
            raise ValueError('Schedule hour must be between 0 and 23')
        return v

    @validator('schedule_minute')
    def validate_schedule_minute(cls, v):
        """Validate that schedule minute is between 0 and 59"""
        if not 0 <= v <= 59:
            raise ValueError('Schedule minute must be between 0 and 59')
        return v

    @validator('scheduled_command')
    def validate_scheduled_command(cls, v):
        """Validate that scheduled command starts with @scrapycat if not empty"""
        if v.strip() and not v.strip().startswith('@scrapycat'):
            raise ValueError('Scheduled command must start with @scrapycat or be empty')
        return v



# hook to give the cat settings
@plugin
def settings_model():
    return PluginSettings
