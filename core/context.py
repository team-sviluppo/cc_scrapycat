from typing import Dict, Set, List, Optional
from threading import Lock
from urllib.robotparser import RobotFileParser
import uuid
import time


class ScrapyCatContext:
    def __init__(self) -> None:
        self.visited_pages: Set[str] = set()  # Set of visited pages during crawling
        self.root_domains: Set[str] = set()  # Set of normalized root domains (for recursive crawling)
        self.allowed_paths: Set[str] = set()  # Set of allowed base paths for URL filtering
        self.ingest_pdf: bool = False  # Whether to ingest PDFs
        self.skip_get_params: bool = False  # Skip URLs with GET parameters
        self.max_depth: int = -1  # Max recursion/crawling depth (-1 for unlimited)
        self.max_pages: int = -1  # Max pages to crawl (-1 for unlimited)
        self.allowed_domains: Set[str] = set()  # Set of allowed domains (single page scraping only)
        self.use_crawl4ai: bool = False  # Whether to use crawl4ai for content extraction
        self.use_crawl4ai_fallback: bool = False  # Whether to use crawl4ai as fallback for empty pages
        self.follow_robots_txt: bool = False  # Whether to follow robots.txt
        self.robots_cache: Dict[str, Optional[RobotFileParser]] = {}  # Cache robots.txt parsers by domain
        self.visited_lock: Lock = Lock()  # Thread-safe access to visited_pages
        self.max_workers: int = 1   # Configurable thread pool size
        self.skip_extensions: List[str] = []  # List of file extensions to skip during crawling
        self.chunk_size: int = 512  # Size of text chunks for ingestion
        self.chunk_overlap: int = 128  # Overlap between consecutive chunks
        self.page_timeout: int = 30  # Timeout for page loading operations
        # Store scraped pages for sequential ingestion
        self.scraped_pages: List[str] = []
        self.scraped_pages_lock: Lock = Lock()  # Thread-safe access to scraped_pages
        
        # UI update throttling
        self.last_update_time: float = 0.0
        self.update_lock: Lock = Lock()
        
        # Session tracking fields for coordination with other plugins
        self.session_id: str = str(uuid.uuid4())  # Unique identifier for this scraping session
        self.command: str = ""  # The command that triggered this scraping session
        self.scheduled: bool = False  # Whether this command is running from scheduler (True) or chat (False)
        self.failed_pages: List[str] = []  # URLs that failed during ingestion
    
    def to_hook_context(self) -> Dict[str, any]:
        """Create a serializable context data dictionary for hook execution"""
        return {
            "session_id": str(self.session_id),
            "command": str(self.command),
            "scheduled": bool(self.scheduled),
            "scraped_pages": [str(url) for url in self.scraped_pages],
            "failed_pages": [str(url) for url in self.failed_pages],
            "chunk_size": int(self.chunk_size),
            "chunk_overlap": int(self.chunk_overlap),
            "page_timeout": int(self.page_timeout),
            "skip_extensions": [str(ext) for ext in self.skip_extensions]
        }
    
    def update_from_hook_context(self, context_data: Dict[str, any]) -> None:
        """Update context with data returned from hook execution"""
        self.session_id = context_data.get("session_id", self.session_id)
        self.command = context_data.get("command", self.command)
        self.scheduled = context_data.get("scheduled", self.scheduled)
        self.scraped_pages = context_data.get("scraped_pages", self.scraped_pages)
        self.failed_pages = context_data.get("failed_pages", self.failed_pages)
        self.chunk_size = context_data.get("chunk_size", self.chunk_size)
        self.chunk_overlap = context_data.get("chunk_overlap", self.chunk_overlap)
        self.page_timeout = context_data.get("page_timeout", self.page_timeout)
        self.skip_extensions = context_data.get("skip_extensions", self.skip_extensions)