from typing import Optional
import urllib.parse
from urllib.robotparser import RobotFileParser
from cat.log import log
from ..core.context import ScrapyCatContext
from .url_utils import normalize_domain


def load_robots_txt(ctx: ScrapyCatContext, domain: str) -> Optional[RobotFileParser]:
    """
    Load and parse robots.txt for a given domain.
    Returns None if robots.txt is not accessible or parsing fails.
    Results are cached in ctx.robots_cache.
    """
    if domain in ctx.robots_cache:
        return ctx.robots_cache[domain]
    
    try:
        # Try both http and https
        for protocol in ['https', 'http']:
            robots_url = f"{protocol}://{domain}/robots.txt"
            try:
                response = ctx.session.get(robots_url, timeout=10)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.set_url(robots_url)
                    rp.read()
                    ctx.robots_cache[domain] = rp
                    log.info(f"Loaded robots.txt for {domain} from {robots_url}")
                    return rp
            except Exception as e:
                log.warning(f"Failed to load robots.txt from {robots_url}: {e}")
                continue
        
        # If we get here, robots.txt is not accessible
        log.info(f"No accessible robots.txt found for {domain}, allowing all URLs")
        ctx.robots_cache[domain] = None
        return None
        
    except Exception as e:
        log.warning(f"Error loading robots.txt for {domain}: {e}")
        ctx.robots_cache[domain] = None
        return None


def is_url_allowed_by_robots(ctx: ScrapyCatContext, url: str) -> bool:
    """
    Check if a URL is allowed by robots.txt.
    Returns True if robots.txt allows the URL or if robots.txt is not available.
    """
    if not ctx.follow_robots_txt:
        return True
    
    parsed_url = urllib.parse.urlparse(url)
    domain = normalize_domain(parsed_url.netloc)
    
    # Get robots.txt parser for this domain
    robots_parser = load_robots_txt(ctx, domain)
    
    # If no robots.txt available, allow the URL
    if robots_parser is None:
        return True
    
    # Check if the URL is allowed for our user agent
    user_agent = ctx.session.headers.get('User-Agent', '*')
    return robots_parser.can_fetch(user_agent, url)