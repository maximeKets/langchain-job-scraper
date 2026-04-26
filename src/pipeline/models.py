from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile_id: str
    candidate_summary: str
    experience_summary: str = ""
    target_titles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    remote_policy: str = "flexible"
    contract_types: list[str] = Field(default_factory=list)
    seniority: str = "mid"
    required_keywords: list[str] = Field(default_factory=list)
    bonus_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    raw_markdown: str


class SearchIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    title: str
    query: str
    locations: list[str] = Field(default_factory=list)
    remote_policy: str = "flexible"
    contract_types: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    bonus_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)


class NormalizedJobOffer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    source_id: str
    title: str
    company: str
    url: str
    canonical_url: str
    category: str
    location: str | None = None
    remote_policy: str | None = None
    employment_type: str | None = None
    description: str | None = None
    published_date: datetime | None = None
    matched_queries: list[str] = Field(default_factory=list)
    source_payload: dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    blocked: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    title_family_score: int = 0
    skills_score: int = 0
    location_remote_score: int = 0
    seniority_score: int = 0
    contract_score: int = 0
    bonus_score: int = 0
    matched_required_keywords: list[str] = Field(default_factory=list)
    matched_bonus_keywords: list[str] = Field(default_factory=list)
    total_score: int = 0


class ScoredJobOffer(NormalizedJobOffer):
    relevance_score: int
    relevance_reason: str
    score_breakdown_json: dict[str, Any]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class DigestEntry(BaseModel):
    offer_id: int
    title: str
    company: str
    relevance_score: int
    location: str | None = None
    source: str
    url: str
    relevance_reason: str
