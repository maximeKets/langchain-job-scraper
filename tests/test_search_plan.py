from __future__ import annotations

from src.config import settings
from src.pipeline.config import JobSearchConfig
from src.pipeline.llm_agents import build_search_plan_with_agent, normalize_search_intents
from src.pipeline.models import CandidateProfile, SearchIntent


def build_profile() -> CandidateProfile:
    return CandidateProfile(
        profile_id="search-plan-test",
        candidate_summary="AI backend developer",
        experience_summary="Python FastAPI RAG LLM",
        target_titles=["AI Engineer", "Backend Python IA", "Automation Developer"],
        target_locations=["Montpellier", "Remote France"],
        remote_policy="flexible",
        contract_types=["full_time", "contract"],
        required_keywords=["python", "fastapi", "rag", "llm", "ai", "automation"],
        bonus_keywords=["langchain", "mcp", "docker"],
        excluded_keywords=["internship", "stage", "alternance"],
        core_skills=["python", "fastapi", "rag"],
        preferred_domains=["ai"],
        raw_markdown="Python FastAPI RAG LLM",
    )


def build_config() -> JobSearchConfig:
    return JobSearchConfig(
        profile_id="search-plan-test",
        profile_markdown_path="candidate.md",
        search={
            "target_locations": ["Montpellier", "Remote France"],
            "remote_policy": "flexible",
            "target_titles": ["AI Engineer", "Backend Python IA", "Automation Developer"],
            "contract_types": ["full_time", "contract"],
            "required_keywords": ["python", "fastapi", "rag", "llm", "ai", "automation"],
            "bonus_keywords": ["langchain", "mcp", "docker"],
            "excluded_keywords": ["internship", "stage", "alternance"],
        },
        sources={"enabled": ["wttj"]},
        digest={"recipient_email": "test@example.com"},
    )


def test_wttj_agent_queries_are_normalized_to_broad_algolia_queries() -> None:
    intents = normalize_search_intents(
        [
            SearchIntent(
                source="wttj",
                title="AI Engineer",
                query="AI Engineer Python FastAPI RAG LLM automation Montpellier full_time remote",
            ),
            SearchIntent(
                source="wttj",
                title="Automation Developer",
                query="Automation Developer Python FastAPI RAG LLM Remote Europe contract",
            ),
        ],
        build_profile(),
    )

    assert [intent.query for intent in intents] == ["AI Engineer", "Automation Developer"]
    assert intents[0].locations == ["Montpellier", "Remote France"]
    assert intents[0].contract_types == ["full_time", "contract"]
    assert intents[0].excluded_keywords == ["internship", "stage", "alternance"]


def test_wttj_fallback_search_plan_uses_broad_queries(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    intents = build_search_plan_with_agent(build_profile(), build_config())
    queries_by_title = {intent.title: intent.query for intent in intents}

    assert queries_by_title["AI Engineer"] == "AI Engineer"
    assert queries_by_title["Backend Python IA"] == "Backend Python IA"
    assert queries_by_title["Automation Developer"] == "Automation Developer"
