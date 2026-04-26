from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PIPELINE_CONFIG_PATH = PROJECT_ROOT / "config/job_search.yaml"


class JobSearchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile_id: str
    profile_markdown_path: str
    recipient_email: str
    target_locations: list[str] = Field(default_factory=list)
    remote_policy: str = "flexible"
    target_titles: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    required_keywords: list[str] = Field(default_factory=list)
    bonus_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    target_sources: list[str] = Field(
        default_factory=lambda: ["wttj", "greenhouse", "lever"]
    )
    min_relevance_score: int = 65
    daily_digest_top_n: int = 10
    greenhouse_board_tokens: list[str] = Field(default_factory=list)
    lever_company_tokens: list[str] = Field(default_factory=list)
    wttj_hits_per_page: int = 20
    wttj_locale: str = "fr"


class LoadedJobSearchConfig(BaseModel):
    config_path: Path
    profile_markdown_path: Path
    settings: JobSearchConfig
    profile_markdown: str


def load_job_search_config(config_path: str | Path) -> LoadedJobSearchConfig:
    config_path = Path(config_path).expanduser()
    resolved_config_path = (
        config_path if config_path.is_absolute() else PROJECT_ROOT / config_path
    ).resolve()
    raw_config = yaml.safe_load(resolved_config_path.read_text(encoding="utf-8")) or {}
    settings = JobSearchConfig.model_validate(raw_config)

    resolved_profile_path = (resolved_config_path.parent / settings.profile_markdown_path).resolve()
    profile_markdown = resolved_profile_path.read_text(encoding="utf-8")

    return LoadedJobSearchConfig(
        config_path=resolved_config_path,
        profile_markdown_path=resolved_profile_path,
        settings=settings,
        profile_markdown=profile_markdown,
    )
