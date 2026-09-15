"""Renders the HTML email from templates/email.html and sends it via Gmail
SMTP. In --test mode, main.py calls render_digest_html() directly and skips
send_email() entirely.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from config import CATEGORIES, CATEGORY_EMOJI, Settings
from models import DigestResult

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_NAME = "email.html"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
MAX_OPPORTUNITIES = 3


def _client_opportunities(result: DigestResult) -> list:
    """Stories the AI flagged with a concrete business/service angle,
    surfaced as a standalone highlight section near the top of the email.
    """
    return [s for s in result.stories if s.business_angle_gu][:MAX_OPPORTUNITIES]


def _group_by_category(result: DigestResult) -> list[dict]:
    grouped: dict[str, list] = {name: [] for name in CATEGORIES}
    for story in result.stories:
        grouped.setdefault(story.category, []).append(story)

    return [
        {"name": name, "emoji": CATEGORY_EMOJI.get(name, ""), "stories": stories}
        for name, stories in grouped.items()
        if stories
    ]


def render_digest_html(result: DigestResult, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo(settings.timezone))
    date_display = now.strftime("%d %B %Y")

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template(TEMPLATE_NAME)

    return template.render(
        date_display=date_display,
        categories=_group_by_category(result),
        opportunities=_client_opportunities(result),
        takeaway=result.takeaway_gu,
        summary_bullets=result.summary_bullets_gu,
        ai_degraded=result.ai_degraded,
    )


def build_subject(settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo(settings.timezone))
    date_display = now.strftime("%d %B %Y")
    return f"🤖 AI Daily — {date_display} | આજના મહત્વના AI સમાચાર"


def send_email(html: str, subject: str, settings: Settings) -> None:
    if not (settings.email_address and settings.email_password and settings.recipient_email):
        raise RuntimeError(
            "EMAIL_ADDRESS, EMAIL_PASSWORD, and RECIPIENT_EMAIL must all be set to send an email"
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.email_address
    message["To"] = settings.recipient_email
    message.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(settings.email_address, settings.email_password)
        server.sendmail(settings.email_address, [settings.recipient_email], message.as_string())

    logger.info("Email sent successfully to %s", settings.recipient_email)
