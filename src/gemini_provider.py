"""Gemini implementation of AIProvider. Owns all batching/chunking, retry,
and rate-limit logic so the rest of the pipeline never has to think about
API mechanics - it just calls select_and_summarize() once.

Cost-safety guarantees enforced here:
  - Never more than settings.max_ai_requests actual network calls in a run
    (this counts every retry attempt too, not just distinct "logical" calls).
  - Never one request per article - candidates are always sent as one
    batch, chunked into at most two calls even for a large candidate set.
  - On repeated failure, falls back to a local, headline-only digest instead
    of retrying indefinitely.
"""

from __future__ import annotations

import json
import logging
import time

from ai_provider import AIProvider
from config import Settings
from models import DigestResult, DigestStory, StoryCluster
from summarizer import (
    RESPONSE_SCHEMA,
    TITLE_ONLY_RESPONSE_SCHEMA,
    build_system_instruction,
    candidates_to_payload,
    parse_digest_response,
)

logger = logging.getLogger(__name__)

# If there are more candidates than this after local pre-ranking, do a cheap
# titles-only pre-filter call first to cut the list down before the full
# (snippet + Gujarati writing) call. Keeps token usage bounded even if
# MAX_ARTICLES_TO_PROCESS is configured high.
CHUNK_THRESHOLD = 25
PREFILTER_TARGET_COUNT = 20

MAX_ATTEMPTS_PER_CALL = 3  # 1 initial attempt + 2 retries

# The pre-filter call has a solid, near-free local fallback (pre-ranking
# order) if it fails, so it doesn't need retries. The final summarization/
# translation call has no such cheap fallback (only the full headline-only
# digest), so it must always get its full retry budget - capping the
# pre-filter to a single attempt guarantees that, since
# PREFILTER_MAX_ATTEMPTS + MAX_ATTEMPTS_PER_CALL never exceeds the default
# MAX_AI_REQUESTS even in the worst case.
PREFILTER_MAX_ATTEMPTS = 1
RETRY_BACKOFF_SECONDS = (2, 8)

FALLBACK_WHAT_HAPPENED_GU = "આજે AI સારાંશ સેવા ઉપલબ્ધ નથી. મૂળ સમાચાર વાંચવા માટે નીચે લિંક પર ક્લિક કરો."
FALLBACK_TAKEAWAY_GU = "આજે ટેકનિકલ કારણોસર AI સારાંશ જનરેટ થઈ શક્યો નથી, તેથી ફક્ત મુખ્ય મથાળાં દર્શાવવામાં આવ્યા છે."


class GeminiProvider(AIProvider):
    def __init__(self, settings: Settings):
        self._client = None
        self._settings = settings
        self.requests_used = 0

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    def _budget_available(self) -> bool:
        return self.requests_used < self._settings.max_ai_requests

    def _call(
        self,
        system_instruction: str,
        contents: str,
        response_schema: dict,
        max_attempts: int = MAX_ATTEMPTS_PER_CALL,
    ) -> dict | None:
        """Make one logical Gemini call, retrying a limited number of times
        on transient failures. Every individual attempt counts against the
        run's total request budget.
        """
        from google.genai import types

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            if not self._budget_available():
                logger.warning(
                    "MAX_AI_REQUESTS=%d reached, aborting further Gemini calls",
                    self._settings.max_ai_requests,
                )
                return None

            self.requests_used += 1
            try:
                client = self._get_client()
                response = client.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        temperature=0.4,
                    ),
                )
                return json.loads(response.text)
            except Exception as exc:  # noqa: BLE001 - network/SDK/parse errors all handled the same
                last_error = exc
                if attempt < max_attempts - 1:
                    backoff = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Gemini call failed (attempt %d/%d): %s - retrying in %ds",
                        attempt + 1, max_attempts, exc, backoff,
                    )
                    time.sleep(backoff)

        logger.error("Gemini call failed after %d attempts: %s", max_attempts, last_error)
        return None

    def _prefilter(self, candidates: list[StoryCluster], settings: Settings) -> list[StoryCluster]:
        payload = candidates_to_payload(candidates, full=False)
        prompt = (
            "Here are today's candidate AI news story titles. Return the ids of "
            f"the top {PREFILTER_TARGET_COUNT} most important, non-duplicate stories "
            "for an AI-focused audience, most important first.\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        data = self._call(
            "You are filtering AI news candidates down to the most important, "
            "distinct stories before detailed summarization. Respond only with JSON.",
            prompt,
            TITLE_ONLY_RESPONSE_SCHEMA,
            max_attempts=PREFILTER_MAX_ATTEMPTS,
        )
        if not data:
            logger.warning("Pre-filter call failed - falling back to local pre-ranking order")
            return candidates[:CHUNK_THRESHOLD]

        by_id = {c.id: c for c in candidates}
        picked = [by_id[i] for i in data.get("top_ids", []) if i in by_id]
        return picked or candidates[:CHUNK_THRESHOLD]

    def _fallback_digest(self, candidates: list[StoryCluster], settings: Settings) -> DigestResult:
        logger.warning("Using fallback headline-only digest (AI unavailable)")
        stories = [
            DigestStory(
                category=c.representative.category_hint or "Major AI News",
                headline_gu=c.title,
                what_happened_gu=FALLBACK_WHAT_HAPPENED_GU,
                why_it_matters_gu="",
                source_name=c.source_name,
                source_url=c.url,
            )
            for c in candidates[: settings.max_stories]
        ]
        return DigestResult(
            stories=stories,
            takeaway_gu=FALLBACK_TAKEAWAY_GU,
            summary_bullets_gu=[],
            ai_degraded=True,
            ai_requests_used=self.requests_used,
        )

    def select_and_summarize(self, candidates: list[StoryCluster], settings: Settings) -> DigestResult:
        if not candidates:
            return DigestResult(stories=[], ai_requests_used=0)

        if not settings.gemini_api_key:
            logger.error("GEMINI_API_KEY not set - cannot call Gemini")
            return self._fallback_digest(candidates, settings)

        working_set = candidates
        if len(candidates) > CHUNK_THRESHOLD:
            working_set = self._prefilter(candidates, settings)

        if not self._budget_available():
            return self._fallback_digest(candidates, settings)

        payload = candidates_to_payload(working_set, full=True)
        prompt = f"Candidate stories (JSON array):\n{json.dumps(payload, ensure_ascii=False)}"

        data = self._call(build_system_instruction(settings), prompt, RESPONSE_SCHEMA)
        if not data:
            return self._fallback_digest(candidates, settings)

        candidates_by_id = {c.id: c for c in working_set}
        result = parse_digest_response(data, candidates_by_id, settings)
        result.ai_requests_used = self.requests_used

        if not result.stories:
            logger.warning("AI returned zero usable stories - using fallback digest")
            return self._fallback_digest(candidates, settings)

        return result
