from datetime import datetime, timedelta, timezone

from deduplicator import deduplicate
from models import Article
from utils import canonicalize_url, extract_domain, normalize_title

BASE_TIME = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)


def make_article(title, url, source_name, minutes_offset=0, tier=5, summary=""):
    published = BASE_TIME + timedelta(minutes=minutes_offset)
    canonical = canonicalize_url(url)
    return Article(
        title=title,
        url=url,
        source_name=source_name,
        domain=extract_domain(canonical),
        published=published,
        summary=summary,
        canonical_url=canonical,
        normalized_title=normalize_title(title),
        tier=tier,
    )


def test_exact_url_duplicates_are_merged():
    a = make_article("OpenAI launches new model", "https://openai.com/blog/new-model?utm_source=x", "OpenAI", tier=1)
    b = make_article("OpenAI launches new model", "https://openai.com/blog/new-model", "OpenAI Mirror", minutes_offset=5, tier=5)

    clusters = deduplicate([a, b])

    assert len(clusters) == 1
    assert len(clusters[0].members) == 2


def test_similar_titles_from_different_sources_are_merged():
    a = make_article(
        "OpenAI releases GPT-5 with major upgrades",
        "https://openai.com/blog/gpt-5", "OpenAI", tier=1,
    )
    b = make_article(
        "OpenAI Releases GPT-5 With Major Upgrades",
        "https://techcrunch.com/2026/09/11/openai-gpt-5", "TechCrunch",
        minutes_offset=20, tier=3,
    )

    clusters = deduplicate([a, b])

    assert len(clusters) == 1


def test_distinct_stories_are_not_merged():
    a = make_article("OpenAI releases GPT-5", "https://openai.com/blog/gpt-5", "OpenAI", tier=1)
    b = make_article(
        "Anthropic announces new funding round",
        "https://anthropic.com/news/funding", "Anthropic",
        minutes_offset=30, tier=1,
    )

    clusters = deduplicate([a, b])

    assert len(clusters) == 2


def test_official_source_wins_as_representative_over_later_tier():
    official = make_article(
        "OpenAI releases GPT-5", "https://openai.com/blog/gpt-5", "OpenAI",
        minutes_offset=10, tier=1,
    )
    aggregator = make_article(
        "OpenAI Releases GPT-5", "https://random-blog.example.com/gpt-5-news", "Random Blog",
        minutes_offset=0, tier=5,
    )

    clusters = deduplicate([aggregator, official])

    assert len(clusters) == 1
    assert clusters[0].representative.source_name == "OpenAI"


def test_same_tier_ties_break_by_earliest_publish_time():
    first = make_article(
        "OpenAI releases GPT-5", "https://reuters.com/tech/openai-gpt5", "Reuters",
        minutes_offset=0, tier=2,
    )
    second = make_article(
        "OpenAI Releases GPT-5", "https://apnews.com/article/openai-gpt5", "AP News",
        minutes_offset=15, tier=2,
    )

    clusters = deduplicate([second, first])

    assert len(clusters) == 1
    assert clusters[0].representative.source_name == "Reuters"


def test_google_news_redirect_url_dedupes_via_title_similarity():
    original = make_article(
        "Google DeepMind unveils new reasoning model",
        "https://deepmind.google/blog/reasoning-model", "Google DeepMind Blog",
        tier=1,
    )
    google_news = make_article(
        "Google DeepMind Unveils New Reasoning Model",
        "https://news.google.com/rss/articles/CBMi123abcXYZ", "Google News - AI",
        minutes_offset=45, tier=5,
    )

    clusters = deduplicate([original, google_news])

    assert len(clusters) == 1
    assert clusters[0].representative.source_name == "Google DeepMind Blog"
