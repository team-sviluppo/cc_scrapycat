import urllib.parse
import re


def clean_url(url: str) -> str:
    # Remove trailing slashes and normalize the URL
    return url.strip().rstrip("/")


def normalize_url_with_protocol(url: str) -> str:
    """
    Ensure URL has a protocol. If no protocol is specified, prepend https://
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
    return url


def normalize_domain(domain_or_url: str) -> str:
    """
    Normalize a domain or URL to a consistent format for comparison.
    Returns the domain without protocol, and handles www subdomain normalization.
    
    Examples:
    - "https://example.com" -> "example.com"
    - "www.example.com" -> "example.com" 
    - "https://www.example.com" -> "example.com"
    - "example.com" -> "example.com"
    """
    domain = domain_or_url.strip().lower()
    
    # Remove protocol if present
    if domain.startswith(('http://', 'https://')):
        domain = urllib.parse.urlparse(domain).netloc
    
    # Remove www. prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return domain


def validate_url(url: str) -> bool:
    # Check if the URL is valid, allowing for subdomains and handling domains without protocols
    url = url.strip()
    
    # If it doesn't have a protocol, it might be a domain with or without a path
    if not url.startswith(('http://', 'https://')):
        # Check if it's a valid domain format (with optional path)
        domain_regex: re.Pattern = re.compile(
            r"^([a-z0-9-]+\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
        )
        return re.match(domain_regex, url) is not None
    
    # If it has a protocol, validate as full URL
    regex: re.Pattern = re.compile(
        r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
    )
    return re.match(regex, url) is not None