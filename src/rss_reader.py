"""Fetches configured RSS/Atom feeds and returns Article objects published
within the configured lookback window. A single feed failing (network error,
malformed XML, timeout) never stops the run — it is logged and skipped.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import requests

from config import Settings
from models import Article
from utils import canonicalize_url, extract_domain, normalize_title, within_lookback

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10
USER_AGENT = "ai-news-digest/1.0 (+https://github.com/)"


def _parse_published(entry) -> datetime | None:
    for field_name in ("published_parsed", "updated_parsed"):
        struct_time = getattr(entry, field_name, None)
        if struct_time:
            try:
                return datetime(*struct_time[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _fetch_one(name: str, url: str) -> feedparser.FeedParserDict | None:
    try:
        response = requests.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as exc:  # noqa: BLE001 - any feed failure must not crash the run
        logger.warning("Feed failed: %s (%s) - %s", name, url, exc)
        return None

    if parsed.bozo and not parsed.entries:
        logger.warning("Feed unparseable: %s (%s) - %s", name, url, parsed.get("bozo_exception"))
        return None
    return parsed


def fetch_articles(settings: Settings, now: datetime | None = None) -> list[Article]:
    """Fetch every configured feed and return articles within the lookback
    window. Returns a flat list of Article objects (not yet deduplicated).
    """
    articles: list[Article] = []
    feeds_ok = 0
    feeds_failed = 0
    dropped_no_date = 0
    dropped_stale = 0

    for feed_cfg in settings.feeds:
        name = feed_cfg.get("name", "Unnamed feed")
        url = feed_cfg.get("url", "")
        feed_type = feed_cfg.get("type", "other")
        category_hint = feed_cfg.get("category_hint", "")

        if not url:
            logger.warning("Feed missing url: %s", name)
            feeds_failed += 1
            continue

        parsed = _fetch_one(name, url)
        if parsed is None:
            feeds_failed += 1
            continue
        feeds_ok += 1

        for entry in parsed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue

            published = _parse_published(entry)
            if published is None:
                dropped_no_date += 1
                continue
            if not within_lookback(published, settings.lookback_hours, now=now):
                dropped_stale += 1
                continue

            summary = getattr(entry, "summary", "") or ""
            canonical = canonicalize_url(link)
            domain = extract_domain(canonical)

            articles.append(
                Article(
                    title=title,
                    url=link,
                    source_name=name,
                    domain=domain,
                    published=published,
                    summary=summary,
                    feed_type=feed_type,
                    category_hint=category_hint,
                    canonical_url=canonical,
                    normalized_title=normalize_title(title),
                    tier=settings.tier_for_domain(domain),
                )
            )

    logger.info(
        "Feeds configured: %d | Feeds successful: %d | Feeds failed: %d",
        len(settings.feeds), feeds_ok, feeds_failed,
    )
    logger.info(
        "Articles collected: %d | Dropped (no date): %d | Dropped (outside %dh window): %d",
        len(articles) + dropped_stale, dropped_no_date, settings.lookback_hours, dropped_stale,
    )
    logger.info("Articles within lookback window: %d", len(articles))

    return articles
