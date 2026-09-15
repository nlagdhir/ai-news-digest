from datetime import datetime, timedelta, timezone

from utils import (
    canonicalize_url,
    extract_domain,
    hours_since,
    normalize_title,
    title_tokens,
    within_lookback,
)


def test_canonicalize_url_strips_tracking_params():
    url = "https://Example.com/article/?utm_source=x&utm_medium=y&id=42"
    assert canonicalize_url(url) == "https://example.com/article?id=42"


def test_canonicalize_url_strips_www_and_trailing_slash():
    assert canonicalize_url("https://www.example.com/path/") == "https://example.com/path"


def test_canonicalize_url_removes_known_tracking_keys():
    url = "https://example.com/a?fbclid=abc&ref=twitter&keep=1"
    assert canonicalize_url(url) == "https://example.com/a?keep=1"


def test_extract_domain_strips_www():
    assert extract_domain("https://www.openai.com/blog/foo") == "openai.com"
    assert extract_domain("https://techcrunch.com/x") == "techcrunch.com"


def test_normalize_title_lowercases_and_strips_stopwords_and_punctuation():
    title = "OpenAI Releases a New GPT Model!"
    normalized = normalize_title(title)
    assert normalized == "openai releases gpt model"


def test_normalize_title_handles_empty_string():
    assert normalize_title("") == ""
    assert normalize_title(None) == ""


def test_title_tokens_returns_a_set():
    tokens = title_tokens("openai releases gpt model")
    assert tokens == {"openai", "releases", "gpt", "model"}


def test_within_lookback_true_for_recent_article():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    published = now - timedelta(hours=5)
    assert within_lookback(published, lookback_hours=24, now=now) is True


def test_within_lookback_false_for_old_article():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    published = now - timedelta(hours=48)
    assert within_lookback(published, lookback_hours=24, now=now) is False


def test_within_lookback_false_for_missing_date():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    assert within_lookback(None, lookback_hours=24, now=now) is False


def test_within_lookback_tolerates_small_future_clock_skew():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    published = now + timedelta(minutes=10)
    assert within_lookback(published, lookback_hours=24, now=now) is True


def test_hours_since_naive_datetime_assumed_utc():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    published_naive = datetime(2026, 9, 11, 6, 0)  # no tzinfo
    assert hours_since(published_naive, now=now) == 6.0
