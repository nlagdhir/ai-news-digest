from datetime import datetime, timezone

from config import Settings
from models import Article, StoryCluster
from summarizer import build_system_instruction, parse_digest_response


def make_cluster(cluster_id, title, url, source_name="Some Source"):
    article = Article(
        title=title,
        url=url,
        source_name=source_name,
        domain="example.com",
        published=datetime(2026, 9, 15, tzinfo=timezone.utc),
        canonical_url=url,
        normalized_title=title.lower(),
        tier=1,
    )
    return StoryCluster(id=cluster_id, representative=article, members=[article])


def make_settings(max_stories=10, company_context="Acme Corp, a widget maker."):
    settings = Settings()
    settings.max_stories = max_stories
    settings.company_context = company_context
    return settings


def test_build_system_instruction_includes_company_context():
    settings = make_settings(company_context="Acme Corp, a widget maker.")
    instruction = build_system_instruction(settings)
    assert "Acme Corp, a widget maker." in instruction
    assert "business_angle_gu" in instruction


def test_parse_digest_response_extracts_business_angle():
    candidates = {"c1": make_cluster("c1", "New AI Agent Framework", "https://example.com/a")}
    data = {
        "selected": [{
            "id": "c1",
            "category": "AI Tools & Products",
            "headline_gu": "હેડલાઇન",
            "what_happened_gu": "શું થયું",
            "why_it_matters_gu": "કેમ મહત્વનું",
            "source_url": "https://example.com/a",
            "business_angle_gu": "ક્લાયન્ટ માટે નવી તક",
        }],
        "takeaway_gu": "ટેકઅવે",
        "summary_bullets_gu": ["બુલેટ ૧"],
    }

    result = parse_digest_response(data, candidates, make_settings())

    assert len(result.stories) == 1
    assert result.stories[0].business_angle_gu == "ક્લાયન્ટ માટે નવી તક"


def test_parse_digest_response_defaults_business_angle_to_empty_string():
    candidates = {"c1": make_cluster("c1", "Policy Debate", "https://example.com/b")}
    data = {
        "selected": [{
            "id": "c1",
            "category": "AI Regulation & Safety",
            "headline_gu": "હેડલાઇન",
            "what_happened_gu": "શું થયું",
            "why_it_matters_gu": "કેમ મહત્વનું",
            "source_url": "https://example.com/b",
            # business_angle_gu intentionally omitted, as a real response might do
        }],
        "takeaway_gu": "",
        "summary_bullets_gu": [],
    }

    result = parse_digest_response(data, candidates, make_settings())

    assert result.stories[0].business_angle_gu == ""


def test_parse_digest_response_never_invents_a_url_outside_known_candidates():
    candidates = {"c1": make_cluster("c1", "Some Story", "https://example.com/real")}
    data = {
        "selected": [{
            "id": "c1",
            "category": "Major AI News",
            "headline_gu": "હેડલાઇન",
            "what_happened_gu": "શું થયું",
            "why_it_matters_gu": "",
            "source_url": "https://not-a-real-candidate.example.com/made-up",
            "business_angle_gu": "",
        }],
        "takeaway_gu": "",
        "summary_bullets_gu": [],
    }

    result = parse_digest_response(data, candidates, make_settings())

    assert result.stories[0].source_url == "https://example.com/real"
