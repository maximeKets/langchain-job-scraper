from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.pipeline.config import load_job_search_config


def test_load_job_search_config_reads_markdown() -> None:
    loaded = load_job_search_config("config/job_search.yaml")

    assert loaded.settings.profile_id == "maxime-data-ai"
    assert loaded.profile_markdown_path.name == "candidate_profile.md"
    assert "LangChain" in loaded.profile_markdown
    assert loaded.settings.target_sources == ["wttj", "greenhouse", "lever"]


def test_load_job_search_config_is_independent_from_current_directory(monkeypatch) -> None:
    monkeypatch.chdir("src/scripts")

    loaded = load_job_search_config("config/job_search.yaml")

    assert loaded.profile_markdown_path.name == "candidate_profile.md"
    assert loaded.settings.profile_id == "maxime-data-ai"


def test_settings_job_search_config_path_is_absolute() -> None:
    assert Path(settings.JOB_SEARCH_CONFIG_PATH).is_absolute()
    assert settings.JOB_SEARCH_CONFIG_PATH.endswith("config/job_search.yaml")
