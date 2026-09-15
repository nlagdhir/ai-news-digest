"""Small, dependency-light helper functions: URL canonicalization, title
normalization, and date/timezone handling. Kept free of network/AI calls so
it is trivially unit-testable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that are purely for tracking/attribution and never change what
# page a URL points to. Stripping them lets two links to the same article
# canonicalize to the same string.
TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAMS = {
    "ref",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "share",
    "source",
    "cmpid",
}

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "is",
    "are", "with", "at", "by", "from", "as", "its", "it", "this", "that",
    "will", "has", "have", "new", "says",
}

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def canonicalize_url(url: str) -> str:
    """Strip tracking query params and normalize scheme/host/trailing slash
    so equivalent links to the same article compare equal.
    """
    if not url:
        return url
    parts = urlsplit(url.strip())
    scheme = "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"

    kept_params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PARAM_PREFIXES):
            continue
        kept_params.append((key, value))
    query = urlencode(kept_params)

    return urlunsplit((scheme, netloc, path, query, ""))


def extract_domain(url: str) -> str:
    """Return the registrable-ish host (without leading www.) for a URL."""
    if not url:
        return ""
    netloc = urlsplit(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/stopwords, collapse whitespace."""
    if not title:
        return ""
    lowered = title.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    tokens = [t for t in no_punct.split() if t not in _STOPWORDS]
    return _WS_RE.sub(" ", " ".join(tokens)).strip()


def title_tokens(normalized_title: str) -> set[str]:
    return set(normalized_title.split())


def to_utc(dt: datetime | None) -> datetime | None:
    """Attach/convert a datetime to UTC. Naive datetimes are assumed UTC
    (which is what feedparser's struct_time-derived datetimes normally are).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hours_since(dt: datetime | None, now: datetime | None = None) -> float | None:
    """Hours elapsed between dt and now (both normalized to UTC)."""
    dt_utc = to_utc(dt)
    if dt_utc is None:
        return None
    now_utc = to_utc(now) if now else datetime.now(timezone.utc)
    delta = now_utc - dt_utc
    return delta.total_seconds() / 3600.0


def within_lookback(dt: datetime | None, lookback_hours: float, now: datetime | None = None) -> bool:
    """True if dt is within the last `lookback_hours` (and not in the future
    by more than a small grace window, to tolerate clock skew).
    """
    hrs = hours_since(dt, now)
    if hrs is None:
        return False
    return -0.5 <= hrs <= lookback_hours
