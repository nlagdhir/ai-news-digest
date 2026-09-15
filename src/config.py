"""Loads configuration from environment variables (.env for local dev, GitHub
Secrets/Actions env in CI) and from config/feeds.yaml. All tunable numeric
limits live here so behavior can be changed without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a listed dependency
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS_PATH = PROJECT_ROOT / "config" / "feeds.yaml"

CATEGORIES = [
    "Major AI News",
    "New AI Models",
    "AI Tools & Products",
    "AI Coding & Agents",
    "AI Business & Funding",
    "AI Research",
    "India AI",
    "AI Regulation & Safety",
]

CATEGORY_EMOJI = {
    "Major AI News": "🔥",
    "New AI Models": "🤖",
    "AI Tools & Products": "🛠️",
    "AI Coding & Agents": "👨‍💻",
    "AI Business & Funding": "💼",
    "AI Research": "🔬",
    "India AI": "🇮🇳",
    "AI Regulation & Safety": "⚖️",
}

DEFAULT_COMPANY_CONTEXT = (
    "Ninja Technolabs, an IT/software services company (founded 2011, 250+ "
    "engineers, 1500+ projects delivered across 30+ countries) that builds for "
    "clients across many industries: web & mobile app development, AI/ML "
    "integration, e-commerce solutions, cloud development, business process "
    "automation, and CRM integration."
)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    # Secrets (may be None outside of --test mode)
    gemini_api_key: str | None = None
    email_address: str | None = None
    email_password: str | None = None
    recipient_email: str | None = None

    # Behavior
    timezone: str = "Asia/Kolkata"
    language: str = "gu"
    gemini_model: str = "gemini-2.5-flash"
    company_context: str = DEFAULT_COMPANY_CONTEXT

    # Cost / safety limits
    lookback_hours: int = 24
    max_articles_to_process: int = 40
    max_stories: int = 10
    max_ai_requests: int = 5

    feeds_path: Path = DEFAULT_FEEDS_PATH
    feeds: list[dict] = field(default_factory=list)
    source_priority: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, feeds_path: Path | None = None) -> "Settings":
        settings = cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            email_address=os.environ.get("EMAIL_ADDRESS") or None,
            email_password=os.environ.get("EMAIL_PASSWORD") or None,
            recipient_email=os.environ.get("RECIPIENT_EMAIL") or None,
            timezone=os.environ.get("TIMEZONE", "Asia/Kolkata"),
            language=os.environ.get("LANGUAGE", "gu"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            company_context=os.environ.get("COMPANY_CONTEXT", DEFAULT_COMPANY_CONTEXT),
            lookback_hours=_int_env("LOOKBACK_HOURS", 24),
            max_articles_to_process=_int_env("MAX_ARTICLES_TO_PROCESS", 40),
            max_stories=_int_env("MAX_STORIES", 10),
            max_ai_requests=_int_env("MAX_AI_REQUESTS", 5),
            feeds_path=feeds_path or DEFAULT_FEEDS_PATH,
        )
        settings._load_feeds()
        return settings

    def _load_feeds(self) -> None:
        with open(self.feeds_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.feeds = data.get("feeds", [])
        self.source_priority = {
            str(domain).lower(): int(tier)
            for domain, tier in (data.get("source_priority") or {}).items()
        }

    def tier_for_domain(self, domain: str) -> int:
        return self.source_priority.get((domain or "").lower(), 5)
