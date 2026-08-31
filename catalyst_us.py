"""
US news catalyst lookup -- uses yfinance's free news feed (no API key
needed). Same purpose as catalyst_nse.py on the India side: turns a raw
institutional-flow volume signal into "RVOL 40x AND there's a recent
headline" rather than just "RVOL 40x" alone.

NOTE: yfinance's news feed is aggregated headlines (Reuters, PR Newswire,
etc via Yahoo), not a direct SEC/exchange filing feed like the NSE side's
announcements/bulk-deals lookup -- treat "no recent headline found" as
"nothing surfaced in this window", not as proof nothing happened.
"""

from datetime import datetime, timezone
import yfinance as yf


def _publish_time(item: dict):
    """
    yfinance has shipped a couple of different news item shapes over time:
      - older: {"title": ..., "providerPublishTime": <unix_ts>}
      - newer: {"content": {"title": ..., "pubDate": "<iso8601>"}}
    Handles both; returns a timezone-aware UTC datetime, or None if it
    can't be parsed (a parse failure just drops that one item rather than
    blocking the whole lookup).
    """
    if "providerPublishTime" in item:
        try:
            return datetime.fromtimestamp(item["providerPublishTime"], tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

    content = item.get("content", {}) or {}
    pub_date = content.get("pubDate") or content.get("displayTime")
    if pub_date:
        try:
            return datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def _title(item: dict) -> str:
    if "title" in item:
        return item["title"]
    return (item.get("content", {}) or {}).get("title", "Untitled")


def get_recent_news(symbol: str, lookback_mins: int = 30) -> list:
    """
    Returns yfinance news items for `symbol` published within the last
    `lookback_mins` minutes, each as {"title": ..., "published": datetime}.
    Returns [] on any fetch failure -- a failed news lookup shouldn't block
    the volume alert itself.
    """
    try:
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []

    now = datetime.now(timezone.utc)
    recent = []
    for item in items:
        published = _publish_time(item)
        if published is None:
            continue
        age_mins = (now - published).total_seconds() / 60
        if 0 <= age_mins <= lookback_mins:
            recent.append({"title": _title(item), "published": published})

    return recent


def format_catalyst_summary(news_items: list) -> str:
    """Short human-readable line for a Telegram message."""
    if not news_items:
        return "No recent headline found -- treat with extra caution"

    titles = [n["title"] for n in news_items[:2]]
    return "Headline: " + "; ".join(titles)
