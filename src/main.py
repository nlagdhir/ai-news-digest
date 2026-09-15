"""Orchestrates the full pipeline: fetch feeds -> filter -> deduplicate ->
pre-rank -> AI select & summarize -> render email -> send (or preview).

Usage:
    python src/main.py               # full run, sends the real daily email
    python src/main.py --test        # full run, writes preview.html instead of sending
    python src/main.py --send-test   # full run, sends one real email (manual verification)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import Settings
from deduplicator import deduplicate
from email_sender import build_subject, render_digest_html, send_email
from gemini_provider import GeminiProvider
from news_ranker import preselect
from rss_reader import fetch_articles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
PREVIEW_PATH = PROJECT_ROOT / "preview.html"

logger = logging.getLogger("ai_news_digest")


def _setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    # Log messages can contain emoji and Gujarati text (e.g. the email
    # subject/headlines) - on Windows, stdout otherwise defaults to a
    # legacy codepage (cp1252) that cannot encode them and crashes logging.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8"),
        ],
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Daily News Digest (Gujarati)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--test", action="store_true",
        help="Run the full pipeline but only write preview.html - never sends an email.",
    )
    mode.add_argument(
        "--send-test", action="store_true",
        help="Run the full pipeline and send one real email for manual verification.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    settings = Settings.load()

    articles = fetch_articles(settings)
    if not articles:
        logger.warning("No articles collected within the lookback window - nothing to send today")
        if not args.test:
            logger.info("Skipping email send: no news to report")
        return 0

    clusters = deduplicate(articles)
    candidates = preselect(clusters, settings)

    provider = GeminiProvider(settings)
    digest = provider.select_and_summarize(candidates, settings)
    logger.info(
        "AI requests made: %d | Stories selected: %d%s",
        digest.ai_requests_used, len(digest.stories),
        " (degraded/fallback mode)" if digest.ai_degraded else "",
    )

    if not digest.stories:
        logger.warning("No stories survived selection - nothing to send today")
        return 0

    html = render_digest_html(digest, settings)
    subject = build_subject(settings)
    logger.info("Email generated (subject: %s)", subject)

    if args.test:
        PREVIEW_PATH.write_text(html, encoding="utf-8")
        logger.info("Preview written to %s (email NOT sent)", PREVIEW_PATH)
        return 0

    send_email(html, subject, settings)
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = parse_args(argv)
    try:
        return run(args)
    except Exception:
        logger.exception("Run failed with an unhandled error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
