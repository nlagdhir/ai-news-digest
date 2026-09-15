"""Cheap, local (non-AI) pre-ranking. Trims the deduplicated story clusters
down to at most MAX_ARTICLES_TO_PROCESS before anything is sent to the AI
provider, using only source tier and recency. This bounds token/cost usage
regardless of how many stories were published that day.
"""

from __future__ import annotations

import logging

from config import Settings
from models import StoryCluster
from utils import hours_since

logger = logging.getLogger(__name__)


def _score(cluster: StoryCluster) -> tuple:
    recency_hours = hours_since(cluster.published) or 999.0
    # More sources reporting the same story is itself a weak signal of
    # importance; lower tier number and lower recency are both better.
    return (cluster.tier, recency_hours, -len(cluster.members))


def preselect(clusters: list[StoryCluster], settings: Settings) -> list[StoryCluster]:
    ranked = sorted(clusters, key=_score)
    trimmed = ranked[: settings.max_articles_to_process]
    logger.info(
        "Pre-AI ranking: %d candidate stories -> %d after applying MAX_ARTICLES_TO_PROCESS=%d",
        len(clusters), len(trimmed), settings.max_articles_to_process,
    )
    return trimmed
