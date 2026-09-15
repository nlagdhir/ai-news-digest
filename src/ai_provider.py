"""Abstract interface for AI providers. Keeping this thin means a future
provider (a different model, a different vendor) is a new file implementing
this one method - nothing else in the pipeline needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from config import Settings
from models import DigestResult, StoryCluster


class AIProvider(ABC):
    @abstractmethod
    def select_and_summarize(
        self, candidates: list[StoryCluster], settings: Settings
    ) -> DigestResult:
        """Given pre-filtered, pre-deduplicated story candidates, return the
        final selected/ranked/categorized/summarized digest. Implementations
        own their own batching, retry, and rate-limit logic, and must never
        exceed settings.max_ai_requests actual API calls in a single run.
        """
        raise NotImplementedError
