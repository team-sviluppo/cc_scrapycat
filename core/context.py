from typing import Dict, Set, List, Optional
from threading import Lock
import requests
from urllib.robotparser import RobotFileParser


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
        self.follow_robots_txt: bool = False  # Whether to follow robots.txt
        self.robots_cache: Dict[str, Optional[RobotFileParser]] = {}  # Cache robots.txt parsers by domain
        self.visited_lock: Lock = Lock()  # Thread-safe access to visited_pages
        self.max_workers: int = 1   # Configurable thread pool size
        self.chunk_size: int = 512  # Size of text chunks for ingestion
        self.chunk_overlap: int = 128  # Overlap between consecutive chunks
        # Session reuse for better performance
        self.session: requests.Session = requests.Session()  # Reuse connections
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0"
        })
        # Store scraped pages for sequential ingestion
        self.scraped_pages: List[str] = []
        self.scraped_pages_lock: Lock = Lock()  # Thread-safe access to scraped_pages