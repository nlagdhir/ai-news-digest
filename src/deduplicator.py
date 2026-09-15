"""Local (non-AI) deduplication: groups articles that are almost certainly
about the same event into StoryCluster objects using canonical URL matching,
title similarity, and token overlap. Runs entirely in Python — no API calls.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from models import Article, StoryCluster
from utils import hours_since, title_tokens

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_THRESHOLD = 0.82
TOKEN_JACCARD_THRESHOLD = 0.6
TIME_WINDOW_HOURS = 6.0


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _same_story(a: Article, b: Article) -> bool:
    if a.canonical_url and a.canonical_url == b.canonical_url:
        return True

    if not a.normalized_title or not b.normalized_title:
        return False

    ratio = SequenceMatcher(None, a.normalized_title, b.normalized_title).ratio()
    if ratio > TITLE_SIMILARITY_THRESHOLD:
        return True

    jaccard = _jaccard(title_tokens(a.normalized_title), title_tokens(b.normalized_title))
    return jaccard > TOKEN_JACCARD_THRESHOLD


def _pick_representative(members: list[Article]) -> Article:
    def sort_key(article: Article):
        published_ts = article.published.timestamp() if article.published else float("inf")
        return (article.tier, published_ts)

    return sorted(members, key=sort_key)[0]


def deduplicate(articles: list[Article]) -> list[StoryCluster]:
    """Cluster articles into StoryCluster objects. Comparisons are limited to
    articles published within TIME_WINDOW_HOURS of each other to keep this
    close to O(n) on realistic daily volumes instead of full O(n^2).
    """
    n = len(articles)
    uf = _UnionFind(n)

    ordered = sorted(
        range(n),
        key=lambda i: articles[i].published.timestamp() if articles[i].published else 0,
    )

    for pos, i in enumerate(ordered):
        for j in ordered[pos + 1:]:
            gap = None
            if articles[i].published and articles[j].published:
                gap = abs(hours_since(articles[i].published, now=articles[j].published))
            if gap is not None and gap > TIME_WINDOW_HOURS:
                break
            if _same_story(articles[i], articles[j]):
                uf.union(i, j)

    groups: dict[int, list[Article]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(articles[i])

    clusters: list[StoryCluster] = []
    for idx, (root, members) in enumerate(groups.items()):
        representative = _pick_representative(members)
        clusters.append(
            StoryCluster(id=f"c{idx}", representative=representative, members=members)
        )

    logger.info("After deduplication: %d stories (from %d articles)", len(clusters), n)
    return clusters
