from datetime import datetime, timezone

import pytest

from config import Settings
from gemini_provider import CHUNK_THRESHOLD, PREFILTER_MAX_ATTEMPTS, GeminiProvider
from models import Article, StoryCluster


def make_cluster(cluster_id, title="Some Story", tier=1):
    article = Article(
        title=title,
        url=f"https://example.com/{cluster_id}",
        source_name="Some Source",
        domain="example.com",
        published=datetime(2026, 9, 15, tzinfo=timezone.utc),
        canonical_url=f"https://example.com/{cluster_id}",
        normalized_title=title.lower(),
        tier=tier,
    )
    return StoryCluster(id=cluster_id, representative=article, members=[article])


def make_settings(max_ai_requests=5):
    settings = Settings()
    settings.gemini_api_key = "fake-key-for-tests"
    settings.max_ai_requests = max_ai_requests
    settings.max_stories = 10
    return settings


def test_call_respects_max_attempts_and_does_not_retry_beyond_it(monkeypatch):
    settings = make_settings()
    provider = GeminiProvider(settings)

    call_count = {"n": 0}

    class FakeModels:
        def generate_content(self, **kwargs):
            call_count["n"] += 1
            raise RuntimeError("simulated 503 UNAVAILABLE")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(provider, "_get_client", lambda: FakeClient())
    monkeypatch.setattr("gemini_provider.time.sleep", lambda seconds: None)

    result = provider._call("system", "prompt", {"type": "object"}, max_attempts=1)

    assert result is None
    assert call_count["n"] == 1
    assert provider.requests_used == 1


def test_prefilter_failure_only_consumes_one_request_and_falls_back_to_local_order(monkeypatch):
    settings = make_settings()
    provider = GeminiProvider(settings)
    candidates = [make_cluster(f"c{i}") for i in range(CHUNK_THRESHOLD + 5)]

    class FakeModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("simulated 503 UNAVAILABLE")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(provider, "_get_client", lambda: FakeClient())
    monkeypatch.setattr("gemini_provider.time.sleep", lambda seconds: None)

    picked = provider._prefilter(candidates, settings)

    assert provider.requests_used == PREFILTER_MAX_ATTEMPTS == 1
    assert picked == candidates[:CHUNK_THRESHOLD]


def test_final_call_still_gets_full_retry_budget_after_prefilter_used_one(monkeypatch):
    """Regression test: a shaky Gemini day (503s) must not let the cheap
    pre-filter call eat the retry budget the final, more important
    summarization call needs.
    """
    settings = make_settings(max_ai_requests=5)
    provider = GeminiProvider(settings)
    candidates = [make_cluster(f"c{i}") for i in range(CHUNK_THRESHOLD + 5)]

    attempts = {"n": 0}

    class FakeModels:
        def generate_content(self, **kwargs):
            attempts["n"] += 1
            raise RuntimeError("simulated 503 UNAVAILABLE")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(provider, "_get_client", lambda: FakeClient())
    monkeypatch.setattr("gemini_provider.time.sleep", lambda seconds: None)

    result = provider.select_and_summarize(candidates, settings)

    # 1 pre-filter attempt + 3 full-call attempts = 4, well within the
    # default budget of 5 - the final call must not be starved.
    assert attempts["n"] == 4
    assert provider.requests_used == 4
    assert result.ai_degraded is True
