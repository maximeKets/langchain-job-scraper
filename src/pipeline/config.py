from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PIPELINE_CONFIG_PATH = PROJECT_ROOT / "config/job_search.yaml"


class CandidateSearchPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_locations: list[str] = Field(default_factory=list)
    remote_policy: str = "flexible"
    target_titles: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    required_keywords: list[str] = Field(default_factory=list)
    bonus_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)


class WttjSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hits_per_page: int = 20
    locale: str = "fr"


class GreenhouseSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_tokens: list[str] = Field(default_factory=list)


class LeverSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_tokens: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(
        default_factory=lambda: ["wttj", "greenhouse", "lever"]
    )
    wttj: WttjSourceConfig = Field(default_factory=WttjSourceConfig)
    greenhouse: GreenhouseSourceConfig = Field(default_factory=GreenhouseSourceConfig)
    lever: LeverSourceConfig = Field(default_factory=LeverSourceConfig)


class DigestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_email: str
    min_relevance_score: int = 65


class JobSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_markdown_path: str
    search: CandidateSearchPreferences = Field(default_factory=CandidateSearchPreferences)
    sources: SourceConfig = Field(default_factory=SourceConfig)
    digest: DigestConfig


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
