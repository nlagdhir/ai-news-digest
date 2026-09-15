"""Writes a small public JSON snapshot of today's top story, in Gujarati,
Hindi, and English, for the landing page's "Real story, today" showcase
card (docs/index.html + docs/data/today.json).

This is a decorative marketing add-on, not part of the core digest - it
must never be able to fail the main daily email run. Gujarati is reused
verbatim from the already-generated digest (zero extra cost); Hindi and
English each cost exactly one extra, no-retry Gemini call, sharing the same
run-wide request budget as the main digest (GeminiProvider.requests_used),
so a bad-503 day that already used up the budget simply skips this step
rather than spending more.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Settings
from gemini_provider import GeminiProvider
from models import DigestResult, DigestStory

logger = logging.getLogger(__name__)

SHOWCASE_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "today.json"

LANGUAGE_NAMES = {"hi": "Hindi", "en": "English"}


def _story_to_dict(headline: str, what_happened: str, why_it_matters: str, source_name: str, source_url: str) -> dict:
    return {
        "headline": headline,
        "what_happened": what_happened,
        "why_it_matters": why_it_matters,
        "source_name": source_name,
        "source_url": source_url,
    }


def build_and_write_showcase(digest: DigestResult, provider: GeminiProvider, settings: Settings) -> None:
    if digest.ai_degraded or not digest.stories:
        logger.info("Skipping showcase update (degraded/fallback digest or no stories today)")
        return

    top_story: DigestStory = digest.stories[0]
    stories = {
        "gu": _story_to_dict(
            "1. " + top_story.headline_gu,
            top_story.what_happened_gu,
            top_story.why_it_matters_gu,
            top_story.source_name,
            top_story.source_url,
        )
    }

    for lang_code, lang_name in LANGUAGE_NAMES.items():
        translated = provider.translate_story(top_story, lang_name)
        if not translated:
            logger.warning("Showcase translation to %s failed - skipping for today's update", lang_name)
            continue
        stories[lang_code] = _story_to_dict(
            "1. " + translated.get("headline", "").strip(),
            translated.get("what_happened", "").strip(),
            translated.get("why_it_matters", "").strip(),
            top_story.source_name,
            top_story.source_url,
        )

    if "en" not in stories:
        # The page defaults to the English tab on load - without it, the
        # frontend's fallback chain would show Gujarati script under an
        # "English" label, which is confusing. Skip the whole update rather
        # than publish that. Gujarati-only ("gu") is always safe to publish
        # since it costs nothing and never fails.
        logger.warning("Showcase missing English translation - not overwriting today.json")
        return

    now = datetime.now(ZoneInfo(settings.timezone))
    payload = {
        "generated_at": now.isoformat(),
        "weekday": now.strftime("%A"),
        "story_count": len(digest.stories),
        "stories": stories,
    }

    try:
        SHOWCASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHOWCASE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Showcase data written to %s (languages: %s)", SHOWCASE_PATH, ", ".join(stories.keys()))
    except OSError as exc:
        logger.warning("Could not write showcase data: %s", exc)
