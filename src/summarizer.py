"""Builds the prompt(s) sent to the AI provider and parses/validates the
JSON response into DigestStory/DigestResult objects. Contains no network
code itself - gemini_provider.py owns the actual API calls.
"""

from __future__ import annotations

import logging

from config import CATEGORIES, Settings
from models import DigestResult, DigestStory, StoryCluster

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 220

SYSTEM_INSTRUCTION = """You are an experienced Gujarati technology journalist who writes a daily \
AI news briefing for an educated general audience in Gujarat, India.

You will be given a list of candidate news stories (title, source, source \
tier, a short snippet, URL, and publish time). Your job:

1. Identify which candidates are clearly reporting the SAME real-world event \
   (e.g. the same product launch covered by multiple outlets) and merge them \
   - keep only the most useful representative id, and list the others under \
   "merged_ids".
2. From the remaining distinct stories, select only the genuinely important \
   ones for an AI-focused audience: major model releases/updates, new AI \
   capabilities, AI agents, notable AI tools/products, major company \
   announcements, funding/acquisitions, important research, AI safety, AI \
   regulation/policy, major infrastructure/chip news, developer/coding AI, \
   India AI developments, and practical impact on businesses/users/developers.
3. Ignore clickbait, SEO filler, promotional content, rumors without \
   reliable sourcing, and very minor/repetitive updates.
4. Select at most {max_stories} stories. If fewer than {max_stories} are \
   genuinely important, select fewer - never pad the list with low-quality \
   stories just to reach the maximum.
5. Assign each selected story to exactly one of these categories: {categories}.
6. Write in natural, simple Gujarati - the way a Gujarati tech journalist \
   would explain this to a general reader, not a literal word-for-word \
   translation. Technical terms (AI, model names, company names, "AI agents", \
   etc.) may remain in English when that reads more naturally. Do not \
   invent facts, statistics, quotes, dates, or capabilities that are not \
   supported by the given title/snippet - if something is uncertain, say so \
   (e.g. "અહેવાલો અનુસાર...").
7. For "source_url", always reuse the exact URL given for the id you selected \
   as the representative - never invent or alter a URL.
8. Also write one short overall "takeaway_gu" paragraph (2-4 sentences) about \
   the most important AI trend visible across today's selected stories, and \
   3-5 very short "summary_bullets_gu" bullets in the style \
   "OpenAI — ટૂંકમાં શું થયું", one bullet per major company/theme present \
   today.

Respond only with JSON matching the provided schema."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "headline_gu": {"type": "string"},
                    "what_happened_gu": {"type": "string"},
                    "why_it_matters_gu": {"type": "string"},
                    "source_url": {"type": "string"},
                    "merged_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "id", "category", "headline_gu",
                    "what_happened_gu", "why_it_matters_gu", "source_url",
                ],
            },
        },
        "takeaway_gu": {"type": "string"},
        "summary_bullets_gu": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["selected", "takeaway_gu", "summary_bullets_gu"],
}

TITLE_ONLY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "top_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["top_ids"],
}


def build_system_instruction(settings: Settings) -> str:
    return SYSTEM_INSTRUCTION.format(
        max_stories=settings.max_stories,
        categories=", ".join(CATEGORIES),
    )


def _clip(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def candidates_to_payload(candidates: list[StoryCluster], full: bool = True) -> list[dict]:
    payload = []
    for cluster in candidates:
        item = {
            "id": cluster.id,
            "title": cluster.title,
            "source": cluster.source_name,
            "tier": cluster.tier,
        }
        if full:
            item["snippet"] = _clip(cluster.snippet)
            item["url"] = cluster.url
            item["published"] = cluster.published.isoformat() if cluster.published else ""
        payload.append(item)
    return payload


def parse_digest_response(data: dict, candidates_by_id: dict[str, StoryCluster], settings: Settings) -> DigestResult:
    """Validate the model's JSON response against the known candidate ids and
    build a DigestResult. Any malformed/unknown entries are skipped rather
    than crashing the run.
    """
    stories: list[DigestStory] = []
    for item in data.get("selected", []):
        cluster_id = item.get("id")
        cluster = candidates_by_id.get(cluster_id)
        if cluster is None:
            logger.warning("AI returned unknown story id %r, skipping", cluster_id)
            continue

        category = item.get("category")
        if category not in CATEGORIES:
            category = cluster.representative.category_hint or CATEGORIES[0]

        source_url = item.get("source_url") or cluster.url
        # Never trust a URL the model didn't give us verbatim from a known
        # candidate - fall back to the original cluster URL if it doesn't
        # match anything we sent.
        known_urls = {c.url for c in candidates_by_id.values()}
        if source_url not in known_urls:
            source_url = cluster.url

        headline = (item.get("headline_gu") or "").strip()
        what_happened = (item.get("what_happened_gu") or "").strip()
        why_it_matters = (item.get("why_it_matters_gu") or "").strip()
        if not headline or not what_happened:
            logger.warning("AI returned incomplete story for id %r, skipping", cluster_id)
            continue

        stories.append(
            DigestStory(
                category=category,
                headline_gu=headline,
                what_happened_gu=what_happened,
                why_it_matters_gu=why_it_matters,
                source_name=cluster.source_name,
                source_url=source_url,
            )
        )
        if len(stories) >= settings.max_stories:
            break

    return DigestResult(
        stories=stories,
        takeaway_gu=(data.get("takeaway_gu") or "").strip(),
        summary_bullets_gu=[b.strip() for b in data.get("summary_bullets_gu", []) if b and b.strip()],
    )
