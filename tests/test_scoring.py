from __future__ import annotations

from src.pipeline.config import JobSearchConfig
from src.pipeline.llm_agents import fallback_parse_candidate_profile
from src.pipeline.models import NormalizedJobOffer
from src.pipeline.scoring import build_fallback_relevance_reason, build_scored_offer, score_offer

RAW_MARKDOWN = "Senior data engineer focused on Python SQL LangChain and production AI systems."


def build_job_config() -> JobSearchConfig:
    return JobSearchConfig(
        profile_id="score-test",
        profile_markdown_path="../profiles/candidate_profile.md",
        search={
            "target_locations": ["Paris", "Remote France"],
            "remote_policy": "flexible",
            "target_titles": ["Data Engineer", "AI Engineer"],
            "contract_types": ["full_time"],
            "seniority": "senior",
            "required_keywords": ["python", "sql", "langchain"],
            "bonus_keywords": ["langgraph", "rag"],
            "excluded_keywords": ["internship", "stage"],
        },
        sources={"enabled": ["wttj"]},
        digest={"recipient_email": "test@example.com", "min_relevance_score": 65},
    )


def test_score_offer_high_match() -> None:
    job_config = build_job_config()
    profile = fallback_parse_candidate_profile(job_config, RAW_MARKDOWN)
    offer = NormalizedJobOffer(
        source="wttj",
        source_id="1",
        title="Senior Data Engineer",
        company="Acme",
        url="https://example.com/jobs/1",
        canonical_url="https://example.com/jobs/1",
        category="Data Engineer",
        location="Paris, France",
        remote_policy="hybrid",
        employment_type="full_time",
        description="Python SQL LangChain LangGraph platform role.",
        matched_queries=["Senior Data Engineer Paris"],
        source_payload={},
    )

    breakdown, strengths, gaps = score_offer(profile, job_config, offer)
    reason = build_fallback_relevance_reason(offer, breakdown, strengths, gaps)
    scored = build_scored_offer(offer, breakdown, strengths, gaps, reason)

    assert scored.relevance_score >= 70
    assert breakdown.blocked is False
    assert strengths


def test_score_offer_blocked_by_excluded_keyword() -> None:
    job_config = build_job_config()
    profile = fallback_parse_candidate_profile(job_config, RAW_MARKDOWN)
    offer = NormalizedJobOffer(
        source="wttj",
        source_id="2",
        title="Data Engineer Internship",
        company="Acme",
        url="https://example.com/jobs/2",
        canonical_url="https://example.com/jobs/2",
        category="Data Engineer",
        location="Paris, France",
        remote_policy="onsite",
        employment_type="internship",
        description="Python internship role for students.",
        matched_queries=["Data Engineer Paris"],
        source_payload={},
    )

    breakdown, strengths, gaps = score_offer(profile, job_config, offer)

    assert breakdown.blocked is True
    assert breakdown.total_score == 0
    assert any("Excluded keywords" in reason for reason in breakdown.blocked_reasons)


def test_score_offer_medium_match() -> None:
    job_config = build_job_config()
    profile = fallback_parse_candidate_profile(job_config, RAW_MARKDOWN)
    offer = NormalizedJobOffer(
        source="lever",
        source_id="3",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/jobs/3",
        canonical_url="https://example.com/jobs/3",
        category="Backend Engineer",
        location="Remote - France",
        remote_policy="remote",
        employment_type="full_time",
        description="Python services with some data pipelines.",
        matched_queries=["Backend Engineer Python"],
        source_payload={},
    )

    breakdown, _, _ = score_offer(profile, job_config, offer)

    assert 0 < breakdown.total_score < 80
