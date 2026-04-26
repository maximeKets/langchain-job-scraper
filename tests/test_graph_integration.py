from __future__ import annotations

from pathlib import Path

import pytest

from src.db.operations import get_pending_digest_offers
from src.pipeline.config import JobSearchConfig
from src.pipeline.graph import get_job_search_graph
from src.pipeline.llm_agents import DigestSummaryOutput
from src.pipeline.models import CandidateProfile, DigestEntry, NormalizedJobOffer, SearchIntent


@pytest.fixture(autouse=True)
def disable_lever_discovery(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.pipeline.graph.build_lever_discovery_queries_with_agent",
        lambda candidate_profile, job_config: [],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.discover_lever_companies",
        lambda queries: [],
    )


def test_graph_integration_with_mocked_agents_and_scrapers(
    monkeypatch, tmp_path: Path, temp_db: str
) -> None:
    profile_path = tmp_path / "candidate.md"
    profile_path.write_text("Python SQL LangChain profile", encoding="utf-8")

    config_path = tmp_path / "job_search.yaml"
    config_path.write_text(
        "\n".join(
            [
                "profile_id: integration-user",
                "profile_markdown_path: candidate.md",
                "recipient_email: integration@example.com",
                "target_locations:",
                "  - Paris",
                "remote_policy: flexible",
                "target_titles:",
                "  - Data Engineer",
                "contract_types:",
                "  - full_time",
                "seniority: senior",
                "required_keywords:",
                "  - python",
                "  - sql",
                "bonus_keywords:",
                "  - langchain",
                "excluded_keywords:",
                "  - internship",
                "target_sources:",
                "  - wttj",
                "  - greenhouse",
                "  - lever",
                "min_relevance_score: 60",
            ]
        ),
        encoding="utf-8",
    )

    fake_profile = CandidateProfile(
        profile_id="integration-user",
        candidate_summary="Senior data engineer",
        experience_summary="Python SQL LangChain experience",
        target_titles=["Data Engineer"],
        target_locations=["Paris"],
        remote_policy="flexible",
        contract_types=["full_time"],
        seniority="senior",
        required_keywords=["python", "sql"],
        bonus_keywords=["langchain"],
        excluded_keywords=["internship"],
        core_skills=["python", "sql", "langchain"],
        preferred_domains=["data", "ai"],
        raw_markdown="Python SQL LangChain profile",
    )
    fake_intent = SearchIntent(
        source="wttj",
        title="Data Engineer",
        query="Data Engineer Python SQL",
        locations=["Paris"],
        remote_policy="flexible",
        contract_types=["full_time"],
        required_keywords=["python", "sql"],
        bonus_keywords=["langchain"],
        excluded_keywords=["internship"],
    )
    fake_offer = NormalizedJobOffer(
        source="wttj",
        source_id="integration-offer",
        title="Senior Data Engineer",
        company="Integration Co",
        url="https://example.com/jobs/integration-offer",
        canonical_url="https://example.com/jobs/integration-offer",
        category="Data Engineer",
        location="Paris, France",
        remote_policy="hybrid",
        employment_type="full_time",
        description="Python SQL LangChain data platform role",
        matched_queries=["Data Engineer Python SQL"],
        source_payload={"fixture": True},
    )

    sent_payload: dict[str, str] = {}

    monkeypatch.setattr(
        "src.pipeline.graph.parse_candidate_profile_with_agent",
        lambda job_config, raw_markdown: fake_profile,
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_search_plan_with_agent",
        lambda candidate_profile, job_config: [
            fake_intent,
            fake_intent.model_copy(update={"source": "greenhouse"}),
            fake_intent.model_copy(update={"source": "lever"}),
        ],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_wttj_jobs",
        lambda job_config, search_intents: [fake_offer],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_greenhouse_jobs",
        lambda job_config, search_intents: [],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_lever_jobs",
        lambda job_config, search_intents: [],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_digest_summary_with_agent",
        lambda candidate_profile, digest_entries: DigestSummaryOutput(
            subject="Integration digest",
            intro="Here are the best matching roles.",
            highlights=["Integration Co - Senior Data Engineer"],
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.graph.send_digest_email",
        lambda recipient_email, subject, html_body: (
            sent_payload.update(
                {
                    "recipient_email": recipient_email,
                    "subject": subject,
                    "html_body": html_body,
                }
            )
            or True
        ),
    )

    graph = get_job_search_graph()
    result = graph.invoke({"config_path": str(config_path)})

    assert result["sent_offer_ids"]
    assert sent_payload["recipient_email"] == "integration@example.com"
    assert result["digest_subject"] == "Integration digest"
    assert get_pending_digest_offers(60, 5) == []


def test_graph_does_not_mark_sent_when_email_fails(
    monkeypatch, tmp_path: Path, temp_db: str
) -> None:
    profile_path = tmp_path / "candidate.md"
    profile_path.write_text("Python SQL LangChain profile", encoding="utf-8")

    config_path = tmp_path / "job_search.yaml"
    config_path.write_text(
        "\n".join(
            [
                "profile_id: integration-user",
                "profile_markdown_path: candidate.md",
                "recipient_email: integration@example.com",
                "target_locations:",
                "  - Paris",
                "remote_policy: flexible",
                "target_titles:",
                "  - Data Engineer",
                "contract_types:",
                "  - full_time",
                "seniority: senior",
                "required_keywords:",
                "  - python",
                "  - sql",
                "bonus_keywords:",
                "  - langchain",
                "excluded_keywords:",
                "  - internship",
                "target_sources:",
                "  - wttj",
                "min_relevance_score: 60",
            ]
        ),
        encoding="utf-8",
    )

    fake_profile = CandidateProfile(
        profile_id="integration-user",
        candidate_summary="Senior data engineer",
        experience_summary="Python SQL LangChain experience",
        target_titles=["Data Engineer"],
        target_locations=["Paris"],
        remote_policy="flexible",
        contract_types=["full_time"],
        seniority="senior",
        required_keywords=["python", "sql"],
        bonus_keywords=["langchain"],
        excluded_keywords=["internship"],
        core_skills=["python", "sql", "langchain"],
        preferred_domains=["data", "ai"],
        raw_markdown="Python SQL LangChain profile",
    )
    fake_offer = NormalizedJobOffer(
        source="wttj",
        source_id="integration-offer",
        title="Senior Data Engineer",
        company="Integration Co",
        url="https://example.com/jobs/integration-offer",
        canonical_url="https://example.com/jobs/integration-offer",
        category="Data Engineer",
        location="Paris, France",
        remote_policy="hybrid",
        employment_type="full_time",
        description="Python SQL LangChain data platform role",
        matched_queries=["Data Engineer Python SQL"],
        source_payload={"fixture": True},
    )

    monkeypatch.setattr(
        "src.pipeline.graph.parse_candidate_profile_with_agent",
        lambda job_config, raw_markdown: fake_profile,
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_search_plan_with_agent",
        lambda candidate_profile, job_config: [
            SearchIntent(
                source="wttj",
                title="Data Engineer",
                query="Data Engineer Python SQL",
                locations=["Paris"],
                remote_policy="flexible",
                contract_types=["full_time"],
                required_keywords=["python", "sql"],
                bonus_keywords=["langchain"],
                excluded_keywords=["internship"],
            )
        ],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_wttj_jobs",
        lambda job_config, search_intents: [fake_offer],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_digest_summary_with_agent",
        lambda candidate_profile, digest_entries: DigestSummaryOutput(
            subject="Integration digest",
            intro="Here are the best matching roles.",
            highlights=["Integration Co - Senior Data Engineer"],
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.graph.send_digest_email",
        lambda recipient_email, subject, html_body: (_ for _ in ()).throw(
            RuntimeError("smtp unavailable")
        ),
    )

    graph = get_job_search_graph()
    with pytest.raises(RuntimeError):
        graph.invoke({"config_path": str(config_path)})

    pending = get_pending_digest_offers(60, 5)
    assert pending
    assert pending[0].status == "new"


def test_graph_digest_includes_all_offers_above_min_score(
    monkeypatch, tmp_path: Path, temp_db: str
) -> None:
    profile_path = tmp_path / "candidate.md"
    profile_path.write_text("Python FastAPI RAG profile", encoding="utf-8")

    config_path = tmp_path / "job_search.yaml"
    config_path.write_text(
        "\n".join(
            [
                "profile_id: integration-user",
                "profile_markdown_path: candidate.md",
                "recipient_email: integration@example.com",
                "target_locations:",
                "  - Remote France",
                "remote_policy: flexible",
                "target_titles:",
                "  - AI Engineer",
                "contract_types:",
                "  - full_time",
                "seniority: mid",
                "required_keywords:",
                "  - python",
                "  - fastapi",
                "bonus_keywords:",
                "  - rag",
                "excluded_keywords:",
                "  - internship",
                "target_sources:",
                "  - wttj",
                "  - lever",
                "min_relevance_score: 60",
            ]
        ),
        encoding="utf-8",
    )

    fake_profile = CandidateProfile(
        profile_id="integration-user",
        candidate_summary="AI developer",
        experience_summary="Python FastAPI RAG experience",
        target_titles=["AI Engineer"],
        target_locations=["Remote France"],
        remote_policy="flexible",
        contract_types=["full_time"],
        seniority="mid",
        required_keywords=["python", "fastapi"],
        bonus_keywords=["rag"],
        excluded_keywords=["internship"],
        core_skills=["python", "fastapi", "rag"],
        preferred_domains=["ai", "automation"],
        raw_markdown="Python FastAPI RAG profile",
    )
    fake_intent = SearchIntent(
        source="wttj",
        title="AI Engineer",
        query="AI Engineer Python FastAPI",
        locations=["Remote France"],
        remote_policy="flexible",
        contract_types=["full_time"],
        required_keywords=["python", "fastapi"],
        bonus_keywords=["rag"],
        excluded_keywords=["internship"],
    )
    wttj_offer = NormalizedJobOffer(
        source="wttj",
        source_id="wttj-offer",
        title="AI Engineer",
        company="WTTJ Co",
        url="https://example.com/jobs/wttj-offer",
        canonical_url="https://example.com/jobs/wttj-offer",
        category="AI Engineer",
        location="Remote France",
        remote_policy="remote",
        employment_type="full_time",
        description="Python FastAPI RAG automation role",
        matched_queries=["AI Engineer Python FastAPI"],
        source_payload={"fixture": True},
    )
    lever_offer = wttj_offer.model_copy(
        update={
            "source": "lever",
            "source_id": "lever-offer",
            "company": "Lever Co",
            "url": "https://example.com/jobs/lever-offer",
            "canonical_url": "https://example.com/jobs/lever-offer",
        }
    )

    digest_counts: dict[str, int] = {}

    monkeypatch.setattr(
        "src.pipeline.graph.parse_candidate_profile_with_agent",
        lambda job_config, raw_markdown: fake_profile,
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_search_plan_with_agent",
        lambda candidate_profile, job_config: [
            fake_intent,
            fake_intent.model_copy(update={"source": "lever"}),
        ],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_wttj_jobs",
        lambda job_config, search_intents: [wttj_offer],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_lever_jobs",
        lambda job_config, search_intents: [lever_offer],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_digest_summary_with_agent",
        lambda candidate_profile, digest_entries: digest_counts.update(
            {"entries": len(digest_entries)}
        )
        or DigestSummaryOutput(
            subject="Integration digest",
            intro="Here are all matching roles.",
            highlights=[],
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.graph.send_digest_email",
        lambda recipient_email, subject, html_body: True,
    )

    graph = get_job_search_graph()
    result = graph.invoke({"config_path": str(config_path)})

    assert digest_counts["entries"] == 2
    assert len(result["sent_offer_ids"]) == 2


def test_graph_keeps_offers_new_when_email_is_not_delivered_live(
    monkeypatch, tmp_path: Path, temp_db: str
) -> None:
    profile_path = tmp_path / "candidate.md"
    profile_path.write_text("Python SQL LangChain profile", encoding="utf-8")

    config_path = tmp_path / "job_search.yaml"
    config_path.write_text(
        "\n".join(
            [
                "profile_id: integration-user",
                "profile_markdown_path: candidate.md",
                "recipient_email: integration@example.com",
                "target_locations:",
                "  - Paris",
                "remote_policy: flexible",
                "target_titles:",
                "  - Data Engineer",
                "contract_types:",
                "  - full_time",
                "seniority: senior",
                "required_keywords:",
                "  - python",
                "  - sql",
                "bonus_keywords:",
                "  - langchain",
                "excluded_keywords:",
                "  - internship",
                "target_sources:",
                "  - wttj",
                "min_relevance_score: 60",
            ]
        ),
        encoding="utf-8",
    )

    fake_profile = CandidateProfile(
        profile_id="integration-user",
        candidate_summary="Senior data engineer",
        experience_summary="Python SQL LangChain experience",
        target_titles=["Data Engineer"],
        target_locations=["Paris"],
        remote_policy="flexible",
        contract_types=["full_time"],
        seniority="senior",
        required_keywords=["python", "sql"],
        bonus_keywords=["langchain"],
        excluded_keywords=["internship"],
        core_skills=["python", "sql", "langchain"],
        preferred_domains=["data", "ai"],
        raw_markdown="Python SQL LangChain profile",
    )
    fake_offer = NormalizedJobOffer(
        source="wttj",
        source_id="integration-offer-not-live",
        title="Senior Data Engineer",
        company="Integration Co",
        url="https://example.com/jobs/integration-offer-not-live",
        canonical_url="https://example.com/jobs/integration-offer-not-live",
        category="Data Engineer",
        location="Paris, France",
        remote_policy="hybrid",
        employment_type="full_time",
        description="Python SQL LangChain data platform role",
        matched_queries=["Data Engineer Python SQL"],
        source_payload={"fixture": True},
    )

    monkeypatch.setattr(
        "src.pipeline.graph.parse_candidate_profile_with_agent",
        lambda job_config, raw_markdown: fake_profile,
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_search_plan_with_agent",
        lambda candidate_profile, job_config: [
            SearchIntent(
                source="wttj",
                title="Data Engineer",
                query="Data Engineer Python SQL",
                locations=["Paris"],
                remote_policy="flexible",
                contract_types=["full_time"],
                required_keywords=["python", "sql"],
                bonus_keywords=["langchain"],
                excluded_keywords=["internship"],
            )
        ],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.fetch_wttj_jobs",
        lambda job_config, search_intents: [fake_offer],
    )
    monkeypatch.setattr(
        "src.pipeline.graph.build_digest_summary_with_agent",
        lambda candidate_profile, digest_entries: DigestSummaryOutput(
            subject="Integration digest",
            intro="Here are the best matching roles.",
            highlights=["Integration Co - Senior Data Engineer"],
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.graph.send_digest_email",
        lambda recipient_email, subject, html_body: False,
    )

    graph = get_job_search_graph()
    result = graph.invoke({"config_path": str(config_path)})

    pending = get_pending_digest_offers(60)
    assert result["sent_offer_ids"] == []
    assert result["run_summary"] == "Email not delivered live; offers kept as new."
    assert [offer.status for offer in pending] == ["new"]
