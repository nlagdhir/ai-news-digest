"""Shared data structures used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    """A single article as read from an RSS feed."""

    title: str
    url: str
    source_name: str
    domain: str
    published: datetime | None
    summary: str = ""
    feed_type: str = "other"
    category_hint: str = ""

    canonical_url: str = ""
    normalized_title: str = ""
    tier: int = 5


@dataclass
class StoryCluster:
    """A group of articles believed to be about the same event."""

    id: str
    representative: Article
    members: list[Article] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.representative.title

    @property
    def url(self) -> str:
        return self.representative.url

    @property
    def source_name(self) -> str:
        return self.representative.source_name

    @property
    def tier(self) -> int:
        return self.representative.tier

    @property
    def published(self) -> datetime | None:
        return self.representative.published

    @property
    def snippet(self) -> str:
        return self.representative.summary


@dataclass
class DigestStory:
    """A single AI-selected, AI-summarized story ready for the email."""

    category: str
    headline_gu: str
    what_happened_gu: str
    why_it_matters_gu: str
    source_name: str
    source_url: str


@dataclass
class DigestResult:
    """Final output of the AI selection/summarization step."""

    stories: list[DigestStory]
    takeaway_gu: str = ""
    summary_bullets_gu: list[str] = field(default_factory=list)
    ai_degraded: bool = False
    ai_requests_used: int = 0
