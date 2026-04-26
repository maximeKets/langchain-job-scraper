from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.pipeline.config import JobSearchConfig, load_job_search_config


def test_load_job_search_config_reads_markdown() -> None:
    loaded = load_job_search_config("config/job_search.yaml")

    assert loaded.settings.profile_id == "maxime-data-ai"
    assert loaded.profile_markdown_path.name == "candidate_profile.md"
    assert "LangChain" in loaded.profile_markdown
    assert loaded.settings.sources.enabled == ["wttj", "greenhouse", "lever"]
    assert loaded.settings.search.target_titles
    assert loaded.settings.digest.min_relevance_score == 60


def test_load_job_search_config_is_independent_from_current_directory(monkeypatch) -> None:
    monkeypatch.chdir("src/scripts")

    loaded = load_job_search_config("config/job_search.yaml")

    assert loaded.profile_markdown_path.name == "candidate_profile.md"
    assert loaded.settings.profile_id == "maxime-data-ai"


def test_settings_job_search_config_path_is_absolute() -> None:
    assert Path(settings.JOB_SEARCH_CONFIG_PATH).is_absolute()
    assert settings.JOB_SEARCH_CONFIG_PATH.endswith("config/job_search.yaml")


def test_job_search_config_uses_structured_shape() -> None:
    config = JobSearchConfig(
        profile_id="legacy",
        profile_markdown_path="candidate.md",
        search={
            "target_titles": ["AI Engineer"],
            "required_keywords": ["python"],
        },
        sources={
            "enabled": ["wttj"],
            "wttj": {"hits_per_page": 12, "locale": "en"},
        },
        digest={
            "recipient_email": "legacy@example.com",
            "min_relevance_score": 70,
        },
    )

    assert config.digest.recipient_email == "legacy@example.com"
    assert config.search.target_titles == ["AI Engineer"]
    assert config.sources.enabled == ["wttj"]
    assert config.sources.wttj.hits_per_page == 12
    assert config.digest.min_relevance_score == 70
