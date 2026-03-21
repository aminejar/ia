"""Simple RSS collector - uses feedparser if available."""
from typing import List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _fetch_article_content(url: str, timeout: int = 3) -> str:
    """Fetch full article content from URL using web scraping.
    
    Args:
        url: Article URL to scrape
        timeout: Request timeout in seconds
        
    Returns:
        Extracted article text or empty string if failed
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Remove script, style, nav, footer elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            element.decompose()
        
        # Try common article selectors
        article = None
        selectors = [
            'article',
            '[class*="article-content"]',
            '[class*="post-content"]',
            '[class*="entry-content"]',
            'main',
            '.content'
        ]
        
        for selector in selectors:
            article = soup.select_one(selector)
            if article:
                break
        
        if article:
            # Get all paragraphs
            paragraphs = article.find_all('p')
            text = '\n\n'.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
            return text[:5000]  # Limit to 5000 chars
        
        # Fallback: get all paragraphs
        paragraphs = soup.find_all('p')
        text = '\n\n'.join(p.get_text().strip() for p in paragraphs[:10] if p.get_text().strip())
        return text[:5000]
        
    except Exception as e:
        logger.debug(f"Failed to fetch article content from {url}: {e}")
        return ""


import socket

def fetch_feed_with_timeout(url, timeout=10):
    try:
        socket.setdefaulttimeout(timeout)
        import feedparser
        feed = feedparser.parse(url)
        return feed
    except Exception as e:
        print(f"SKIPPED feed {url}: {e}")
        return None
    finally:
        socket.setdefaulttimeout(None)

def _fetch_summary_from_url(url: str, timeout: int = 5) -> str:
    """Fetch real article URL and extract first 500 chars if summary is empty."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script, style, nav, footer, ads, etc.
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
            element.decompose()
            
        # Extract text and clean up whitespaces
        text = soup.get_text(separator=' ', strip=True)
        return text[:500]
        
    except Exception as e:
        logger.debug(f"Failed to fetch summary from webpage {url}: {e}")
        return ""

def fetch_rss(feed_url: str, max_items: int = 10) -> list[dict]:
    try:
        import feedparser
    except Exception as e:
        raise ImportError(
            "feedparser is required for RSS collection. Install with: pip install feedparser"
        ) from e

    parsed = fetch_feed_with_timeout(feed_url, timeout=10)
    if not parsed:
        return []

    items = []
    source = parsed.feed.get("title") if getattr(parsed, "feed", None) else feed_url
    import re
    for entry in parsed.entries[:max_items]:
        summary = entry.get("summary", "")
        content = _extract_content(entry)
        link = entry.get("link", "")
        
        # If summary is too short, try fetching from the real page
        clean_summary = re.sub(r'<[^>]+>', '', summary).strip()
        if len(clean_summary) < 50 and link:
            logger.debug(f"Summary too short, fetching real page: {link}")
            new_summary = _fetch_summary_from_url(link, timeout=5)
            if new_summary:
                summary = new_summary
                
        # If content is too short, try fetching full article
        if len(content) < 200 and link:
            logger.debug(f"Fetching full content for: {entry.get('title', 'Unknown')}")
            full_content = _fetch_article_content(link)
            if len(full_content) > len(content):
                content = full_content
        
        items.append(
            {
                "title": entry.get("title", ""),
                "link": link,
                "published": entry.get("published", entry.get("updated", None)),
                "summary": summary,
                "content": content,
                "source": source,
                "feed_url": feed_url,
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }
        )
    return items


def _extract_content(entry) -> str:
    # feedparser may expose content[] for full text
    if "content" in entry and entry.content:
        try:
            return entry.content[0].value
        except Exception:
            return str(entry.get("summary", ""))
    return str(entry.get("summary", ""))
