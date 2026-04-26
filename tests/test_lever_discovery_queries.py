from __future__ import annotations

from src.pipeline.config import JobSearchConfig
from src.pipeline.llm_agents import (
    MAX_LEVER_DISCOVERY_QUERIES,
    fallback_build_lever_discovery_queries,
    _dedupe_queries,
)
from src.pipeline.models import CandidateProfile


def build_profile() -> CandidateProfile:
    return CandidateProfile(
        profile_id="query-test",
        candidate_summary="AI backend developer",
        experience_summary="Python FastAPI RAG LLM",
        target_titles=["AI Engineer", "Backend Python IA"],
        target_locations=["Montpellier", "Remote France"],
        remote_policy="flexible",
        contract_types=["full_time"],
        required_keywords=["python", "fastapi", "rag", "llm", "ai", "automation"],
        bonus_keywords=["langchain", "mcp", "docker"],
        excluded_keywords=["internship", "stage"],
        core_skills=["python", "fastapi", "rag"],
        preferred_domains=["ai"],
        raw_markdown="Python FastAPI RAG LLM",
    )


def build_config() -> JobSearchConfig:
    return JobSearchConfig(
        profile_id="query-test",
        profile_markdown_path="candidate.md",
        search={
            "target_titles": ["AI Engineer", "Backend Python IA"],
            "required_keywords": ["python", "fastapi", "rag", "llm", "ai", "automation"],
            "bonus_keywords": ["langchain", "mcp", "docker"],
        },
        sources={"enabled": ["lever"]},
        digest={"recipient_email": "test@example.com"},
    )


def test_dedupe_queries_simplifies_overcomplete_agent_queries() -> None:
    queries = _dedupe_queries(
        [
            'site:jobs.lever.co "AI Engineer" Python FastAPI RAG LLM Remote Europe '
            "-internship -stage -wordpress -mobile"
        ]
    )

    assert queries == ['site:jobs.lever.co "AI Engineer" Python FastAPI RAG']
    assert "-internship" not in queries[0]
    assert "Remote" not in queries[0]


def test_fallback_lever_discovery_queries_are_short_and_broad() -> None:
    queries = fallback_build_lever_discovery_queries(build_profile(), build_config())

    assert queries
    assert len(queries) <= MAX_LEVER_DISCOVERY_QUERIES
    assert all(query.startswith("site:jobs.lever.co") for query in queries)
    assert all("-" not in query.split("site:jobs.lever.co", maxsplit=1)[1] for query in queries)
    assert 'site:jobs.lever.co "AI Engineer"' in queries
