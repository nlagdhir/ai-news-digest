from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import rss_reader
from config import Settings


def make_entry(title, link, hours_ago=1, summary="", with_date=True):
    published_parsed = None
    if with_date:
        dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        published_parsed = dt.timetuple()
    return SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        published_parsed=published_parsed,
    )


def make_settings(feeds):
    settings = Settings()
    settings.feeds = feeds
    settings.source_priority = {}
    settings.lookback_hours = 24
    return settings


def test_parse_published_reads_published_parsed():
    entry = make_entry("Title", "https://example.com/a", hours_ago=2)
    result = rss_reader._parse_published(entry)
    assert result is not None
    assert result.tzinfo is not None


def test_parse_published_returns_none_when_missing():
    entry = make_entry("Title", "https://example.com/a", with_date=False)
    assert rss_reader._parse_published(entry) is None


def test_fetch_articles_continues_when_one_feed_fails(monkeypatch):
    feeds = [
        {"name": "Good Feed", "url": "https://good.example.com/rss", "type": "official", "category_hint": ""},
        {"name": "Bad Feed", "url": "https://bad.example.com/rss", "type": "official", "category_hint": ""},
    ]
    settings = make_settings(feeds)

    def fake_fetch_one(name, url):
        if "bad" in url:
            return None  # simulates a network/parse failure that is logged and skipped
        return SimpleNamespace(entries=[make_entry("Good article", "https://good.example.com/a", hours_ago=1)])

    monkeypatch.setattr(rss_reader, "_fetch_one", fake_fetch_one)

    articles = rss_reader.fetch_articles(settings)

    assert len(articles) == 1
    assert articles[0].title == "Good article"


def test_fetch_articles_drops_articles_without_a_date(monkeypatch):
    feeds = [{"name": "Feed", "url": "https://example.com/rss", "type": "official", "category_hint": ""}]
    settings = make_settings(feeds)

    def fake_fetch_one(name, url):
        return SimpleNamespace(
            entries=[
                make_entry("Has date", "https://example.com/a", hours_ago=1),
                make_entry("No date", "https://example.com/b", with_date=False),
            ]
        )

    monkeypatch.setattr(rss_reader, "_fetch_one", fake_fetch_one)

    articles = rss_reader.fetch_articles(settings)

    assert len(articles) == 1
    assert articles[0].title == "Has date"


def test_fetch_articles_filters_outside_lookback_window(monkeypatch):
    feeds = [{"name": "Feed", "url": "https://example.com/rss", "type": "official", "category_hint": ""}]
    settings = make_settings(feeds)
    settings.lookback_hours = 24

    def fake_fetch_one(name, url):
        return SimpleNamespace(
            entries=[
                make_entry("Recent", "https://example.com/a", hours_ago=5),
                make_entry("Too old", "https://example.com/b", hours_ago=48),
            ]
        )

    monkeypatch.setattr(rss_reader, "_fetch_one", fake_fetch_one)

    articles = rss_reader.fetch_articles(settings)

    assert len(articles) == 1
    assert articles[0].title == "Recent"


def test_fetch_articles_returns_empty_list_when_all_feeds_fail(monkeypatch):
    feeds = [{"name": "Feed", "url": "https://example.com/rss", "type": "official", "category_hint": ""}]
    settings = make_settings(feeds)

    monkeypatch.setattr(rss_reader, "_fetch_one", lambda name, url: None)

    articles = rss_reader.fetch_articles(settings)

    assert articles == []
