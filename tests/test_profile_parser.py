from __future__ import annotations

from pathlib import Path

from src.pipeline.config import JobSearchConfig
from src.pipeline.llm_agents import fallback_parse_candidate_profile


def test_fallback_profile_parser_handles_noisy_markdown() -> None:
    markdown = Path("tests/fixtures/noisy_candidate_profile.md").read_text(encoding="utf-8")
    job_config = JobSearchConfig(
        profile_id="candidate-noisy",
        profile_markdown_path="../tests/fixtures/noisy_candidate_profile.md",
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
        sources={"enabled": ["wttj", "greenhouse", "lever"]},
        digest={"recipient_email": "test@example.com", "min_relevance_score": 65},
    )

    profile = fallback_parse_candidate_profile(job_config, markdown)

    assert profile.profile_id == "candidate-noisy"
    assert "Python" in profile.candidate_summary or "python" in profile.candidate_summary
    assert profile.target_titles == ["Data Engineer", "AI Engineer"]
    assert "langchain" in [keyword.lower() for keyword in profile.required_keywords]
