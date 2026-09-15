import json
from datetime import datetime, timezone

from config import Settings
from models import DigestResult, DigestStory

import showcase


def make_settings():
    settings = Settings()
    settings.timezone = "Asia/Kolkata"
    return settings


def make_digest(stories=None, ai_degraded=False):
    return DigestResult(
        stories=stories if stories is not None else [
            DigestStory(
                category="Major AI News",
                headline_gu="ગુજરાતી હેડલાઇન",
                what_happened_gu="શું થયું",
                why_it_matters_gu="કેમ મહત્વનું",
                source_name="Example Source",
                source_url="https://example.com/story",
            )
        ],
        ai_degraded=ai_degraded,
    )


class FakeProvider:
    def __init__(self, translations):
        self.translations = translations
        self.calls = []

    def translate_story(self, story, target_language):
        self.calls.append(target_language)
        return self.translations.get(target_language)


def test_skips_when_digest_is_degraded(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "SHOWCASE_PATH", tmp_path / "today.json")
    digest = make_digest(ai_degraded=True)
    provider = FakeProvider({})

    showcase.build_and_write_showcase(digest, provider, make_settings())

    assert not (tmp_path / "today.json").exists()
    assert provider.calls == []


def test_skips_when_no_stories(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "SHOWCASE_PATH", tmp_path / "today.json")
    digest = make_digest(stories=[])

    showcase.build_and_write_showcase(digest, FakeProvider({}), make_settings())

    assert not (tmp_path / "today.json").exists()


def test_writes_all_three_languages_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "SHOWCASE_PATH", tmp_path / "today.json")
    digest = make_digest()
    provider = FakeProvider({
        "Hindi": {"headline": "हिंदी शीर्षक", "what_happened": "क्या हुआ", "why_it_matters": "क्यों मायने रखता है"},
        "English": {"headline": "English headline", "what_happened": "What happened", "why_it_matters": "Why it matters"},
    })

    showcase.build_and_write_showcase(digest, provider, make_settings())

    data = json.loads((tmp_path / "today.json").read_text(encoding="utf-8"))
    assert set(data["stories"].keys()) == {"gu", "hi", "en"}
    assert data["stories"]["en"]["headline"] == "1. English headline"
    assert data["stories"]["gu"]["headline"] == "1. ગુજરાતી હેડલાઇન"
    assert data["story_count"] == 1


def test_skips_write_when_english_translation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "SHOWCASE_PATH", tmp_path / "today.json")
    digest = make_digest()
    # Hindi succeeds but English fails - English is required for the page's
    # default tab, so the whole update should be skipped rather than publish
    # a broken state.
    provider = FakeProvider({
        "Hindi": {"headline": "हिंदी शीर्षक", "what_happened": "क्या हुआ", "why_it_matters": "क्यों"},
    })

    showcase.build_and_write_showcase(digest, provider, make_settings())

    assert not (tmp_path / "today.json").exists()


def test_publishes_gujarati_even_if_hindi_translation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "SHOWCASE_PATH", tmp_path / "today.json")
    digest = make_digest()
    provider = FakeProvider({
        "English": {"headline": "English headline", "what_happened": "What happened", "why_it_matters": "Why it matters"},
    })

    showcase.build_and_write_showcase(digest, provider, make_settings())

    data = json.loads((tmp_path / "today.json").read_text(encoding="utf-8"))
    assert set(data["stories"].keys()) == {"gu", "en"}
