"""
fetch_news.py — Ingests RIA industry news from NewsData.io API and RSS feeds.

Sources:
  - NewsData.io (3 API calls covering acquisitions/M&A, breakaway/funding, and AI in wealthtech)
  - RSS feeds: AdvisorHub, RIABiz, WealthManagement.com, Financial Planning

Output: Deduplicated list of article dicts in normalized schema.
"""

import os
import logging
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS feeds to poll
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    ("AdvisorHub", "https://advisorhub.com/feed/"),
    ("RIABiz", "https://riabiz.com/rss"),
    ("WealthManagement.com", "https://www.wealthmanagement.com/rss.xml"),
    ("Financial Planning", "https://www.financial-planning.com/feed/"),
]

# NewsData.io search queries — list of param dicts passed directly to the API.
# Simple phrases work best; complex OR syntax not supported on the free tier.
# country=us applied only to the AI query (M&A/breakaway queries need global coverage
# since niche RIA stories appear on US sites that don't register as country=us).
NEWSDATA_QUERIES = [
    {"q": '"wealth management" acquisition', "language": "en"},
    {"q": "wealth management funding advisor", "language": "en"},
    {"q": "AI wealthtech wealth management", "language": "en", "country": "us"},
]

NEWSDATA_ENDPOINT = "https://newsdata.io/api/1/latest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_utm(url: str) -> str:
    """Remove UTM query parameters so we can deduplicate URLs correctly."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if not k.startswith("utm_")}
    clean_url = parsed._replace(query=urlencode(clean_qs, doseq=True))
    return urlunparse(clean_url).rstrip("?")


def _truncate(text: str, max_chars: int = 300) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[:max_chars] + "…" if len(text) > max_chars else text


def _html_to_text(html: str) -> str:
    """Strip HTML tags to get plain text."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()


def _parse_rss_date(entry) -> str:
    """Parse feedparser entry date to ISO 8601 string. Falls back to now."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()


def _is_within_window(iso_date: str, hours: int = 72) -> bool:
    """Return True if the date string is within the rolling window.

    Default 72h covers the Friday→Monday weekend gap so Monday's digest
    always includes Friday's news. GPT de-duplicates any cross-day overlap.
    """
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt <= timedelta(hours=hours)
    except Exception:
        return False  # If we can't parse, skip it


def _make_article(title, url, source, published, description, content="") -> dict:
    return {
        "title": title.strip() if title else "",
        "url": url.strip() if url else "",
        "source": source,
        "published": published,
        "description": _truncate(_html_to_text(description)),
        "content": _html_to_text(content)[:1000] if content else "",
    }


# ---------------------------------------------------------------------------
# NewsData.io
# ---------------------------------------------------------------------------

def fetch_newsdata(api_key: str) -> list[dict]:
    """Fetch articles from NewsData.io using targeted queries."""
    articles = []

    for query_params in NEWSDATA_QUERIES:
        params = {"apikey": api_key, **query_params}
        query_label = query_params.get("q", "")[:60]
        try:
            resp = requests.get(NEWSDATA_ENDPOINT, params=params, timeout=15)

            if resp.status_code == 429:
                logger.warning("NewsData.io rate limit hit — continuing with RSS only.")
                break
            if resp.status_code == 401:
                raise ValueError(
                    "NewsData.io API key is invalid (HTTP 401). "
                    "Check NEWSDATA_API_KEY in your .env file."
                )

            resp.raise_for_status()
            data = resp.json()

            logger.debug(f"NewsData.io status: {data.get('status')}, totalResults: {data.get('totalResults', 0)}")

            results = data.get("results", [])
            if not results:
                logger.info(f"NewsData.io: 0 results for query '{query_label}'")

            for item in results:
                article = _make_article(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    source=item.get("source_id", "NewsData.io"),
                    published=item.get("pubDate", datetime.now(timezone.utc).isoformat()),
                    description=item.get("description", ""),
                    content=item.get("content", ""),
                )
                if article["title"] and article["url"]:
                    articles.append(article)
                else:
                    logger.debug(f"Skipped item with missing title/url: {item.get('title', '(no title)')[:60]}")

        except ValueError:
            raise  # Re-raise auth errors
        except Exception as e:
            logger.warning(f"NewsData.io query failed for '{query_label}...': {e}")

    logger.info(f"NewsData.io: fetched {len(articles)} articles")
    return articles


# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------

def fetch_rss_feeds() -> list[dict]:
    """Fetch articles from all configured RSS feeds, filtered to last 24h."""
    articles = []

    for source_name, feed_url in RSS_FEEDS:
        try:
            # Use requests to fetch (handles SSL certs correctly on macOS)
            # then pass raw bytes to feedparser to avoid SSL certificate errors
            resp = requests.get(feed_url, timeout=15, headers={"User-Agent": "FastTrackr-RIA-Digest/1.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            if feed.bozo and not feed.entries:
                logger.warning(f"RSS parse issue for {source_name}: {feed.bozo_exception}")
                continue

            count = 0
            for entry in feed.entries:
                published = _parse_rss_date(entry)
                if not _is_within_window(published):
                    continue

                description = ""
                if hasattr(entry, "summary"):
                    description = entry.summary
                elif hasattr(entry, "description"):
                    description = entry.description

                content = ""
                if hasattr(entry, "content") and entry.content:
                    content = entry.content[0].get("value", "")

                article = _make_article(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_name,
                    published=published,
                    description=description,
                    content=content,
                )
                if article["title"] and article["url"]:
                    articles.append(article)
                    count += 1

            logger.info(f"RSS {source_name}: {count} articles in last 24h")

        except Exception as e:
            logger.warning(f"RSS feed failed for {source_name}: {e}")

    return articles


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by cleaned URL."""
    seen = set()
    unique = []
    for article in articles:
        clean_url = _strip_utm(article["url"])
        if clean_url and clean_url not in seen:
            seen.add(clean_url)
            unique.append(article)
    return unique


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_all_news(newsdata_api_key: str) -> list[dict]:
    """
    Fetch from all sources, normalize, deduplicate, and return article list.

    Args:
        newsdata_api_key: NewsData.io API key (may be empty string for RSS-only mode)

    Returns:
        List of normalized article dicts, deduplicated by URL.
    """
    all_articles = []

    # NewsData.io (primary)
    if newsdata_api_key:
        try:
            nd_articles = fetch_newsdata(newsdata_api_key)
            all_articles.extend(nd_articles)
        except ValueError as e:
            raise  # Auth errors should fail fast
        except Exception as e:
            logger.warning(f"NewsData.io ingestion failed entirely: {e}")

    # RSS feeds (secondary / always run)
    rss_articles = fetch_rss_feeds()
    all_articles.extend(rss_articles)

    # Deduplicate
    unique_articles = deduplicate(all_articles)
    logger.info(f"Total unique articles after deduplication: {len(unique_articles)}")

    return unique_articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("NEWSDATA_API_KEY", "")
    articles = fetch_all_news(key)
    print(f"\nFetched {len(articles)} unique articles:")
    for a in articles[:5]:
        print(f"  [{a['source']}] {a['title'][:80]}")
