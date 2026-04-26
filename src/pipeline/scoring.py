from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.pipeline.config import JobSearchConfig
from src.pipeline.models import CandidateProfile, NormalizedJobOffer, ScoreBreakdown, ScoredJobOffer

TRACKING_QUERY_PARAMS = {
    "gh_src",
    "gh_jid",
    "lever-source",
    "lever-via",
    "ref",
    "src",
    "source",
    "trk",
}

REMOTE_POLICY_MAP = {
    "full_remote": "remote",
    "remote": "remote",
    "remote_only": "remote",
    "flexible": "flexible",
    "punctual": "hybrid",
    "hybrid": "hybrid",
    "on_site": "onsite",
    "onsite": "onsite",
    "office": "onsite",
}

CONTRACT_TYPE_MAP = {
    "cdi": "full_time",
    "full_time": "full_time",
    "full-time": "full_time",
    "permanent": "full_time",
    "contract": "contract",
    "freelance": "contract",
    "internship": "internship",
    "stage": "internship",
    "alternance": "apprenticeship",
    "apprenticeship": "apprenticeship",
}


def canonicalize_job_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/") or "/"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower().replace(":443", "").replace(":80", "")
    return urlunparse((scheme, netloc, path, "", urlencode(query), ""))


def parse_datetime(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def normalize_remote_policy(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return REMOTE_POLICY_MAP.get(normalized, normalized)


def normalize_contract_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return CONTRACT_TYPE_MAP.get(normalized, normalized)


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", (value or "").casefold()).strip()


def tokenize(value: str | None) -> set[str]:
    return {token for token in normalize_text(value).split() if token}


def overlap_ratio(reference: str, candidate: str) -> float:
    reference_tokens = tokenize(reference)
    candidate_tokens = tokenize(candidate)
    if not reference_tokens or not candidate_tokens:
        return 0.0
    return len(reference_tokens & candidate_tokens) / len(reference_tokens)


def find_matching_keywords(keywords: Iterable[str], text: str) -> list[str]:
    normalized_text = normalize_text(text)
    matches: list[str] = []
    for keyword in keywords:
        if normalize_text(keyword) and normalize_text(keyword) in normalized_text:
            matches.append(keyword)
    return matches


def location_matches(target_locations: list[str], offer_location: str | None) -> bool:
    if not target_locations:
        return True
    normalized_offer_location = normalize_text(offer_location)
    return any(normalize_text(location) in normalized_offer_location for location in target_locations)


def remote_policy_is_compatible(desired_policy: str, offer_policy: str | None) -> bool:
    normalized_desired = normalize_remote_policy(desired_policy) or "flexible"
    normalized_offer = normalize_remote_policy(offer_policy) or "unknown"

    if normalized_desired == "flexible":
        return True
    if normalized_desired == "remote":
        return normalized_offer in {"remote", "hybrid", "flexible"}
    if normalized_desired == "hybrid":
        return normalized_offer in {"hybrid", "flexible", "onsite"}
    if normalized_desired == "onsite":
        return normalized_offer in {"onsite", "hybrid", "flexible"}
    return True


def contract_type_is_compatible(
    desired_contracts: list[str], offer_contract_type: str | None
) -> bool:
    if not desired_contracts:
        return True
    normalized_offer = normalize_contract_type(offer_contract_type)
    normalized_desired = {normalize_contract_type(item) for item in desired_contracts}
    return normalized_offer in normalized_desired


def score_offer(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
    offer: NormalizedJobOffer,
) -> tuple[ScoreBreakdown, list[str], list[str]]:
    text = " ".join(
        part
        for part in [
            offer.title,
            offer.company,
            offer.location,
            offer.remote_policy,
            offer.employment_type,
            offer.description,
            offer.category,
        ]
        if part
    )

    blocked_reasons: list[str] = []
    strengths: list[str] = []
    gaps: list[str] = []

    matched_required_keywords = find_matching_keywords(candidate_profile.required_keywords, text)
    matched_bonus_keywords = find_matching_keywords(candidate_profile.bonus_keywords, text)
    matched_excluded_keywords = find_matching_keywords(candidate_profile.excluded_keywords, text)

    if matched_excluded_keywords:
        blocked_reasons.append(
            f"Excluded keywords detected: {', '.join(matched_excluded_keywords)}"
        )

    if not remote_policy_is_compatible(job_config.remote_policy, offer.remote_policy):
        blocked_reasons.append("Remote policy mismatch")

    location_is_compatible = location_matches(job_config.target_locations, offer.location)
    if not location_is_compatible and normalize_remote_policy(offer.remote_policy) not in {
        "remote",
        "flexible",
    }:
        blocked_reasons.append("Location mismatch")

    if not contract_type_is_compatible(job_config.contract_types, offer.employment_type):
        blocked_reasons.append("Contract type mismatch")

    title_score_ratio = max(
        (overlap_ratio(target_title, offer.title) for target_title in candidate_profile.target_titles),
        default=0.0,
    )
    title_family_score = round(30 * title_score_ratio)
    if title_family_score:
        strengths.append("Strong title alignment")
    else:
        gaps.append("Title alignment is weak")

    if candidate_profile.required_keywords:
        skills_score = round(
            25 * (len(matched_required_keywords) / len(candidate_profile.required_keywords))
        )
    else:
        skills_score = 25

    if matched_required_keywords:
        strengths.append(
            f"Required skills matched: {', '.join(matched_required_keywords[:4])}"
        )
    elif candidate_profile.required_keywords:
        gaps.append("Required skills are not clearly present")

    if location_is_compatible and remote_policy_is_compatible(
        job_config.remote_policy, offer.remote_policy
    ):
        location_remote_score = 20
        strengths.append("Location and remote policy are compatible")
    elif remote_policy_is_compatible(job_config.remote_policy, offer.remote_policy):
        location_remote_score = 10
    else:
        location_remote_score = 0

    seniority_text = " ".join(
        part for part in [offer.title, offer.description, offer.employment_type] if part
    )
    if normalize_text(job_config.seniority) in normalize_text(seniority_text):
        seniority_score = 10
        strengths.append("Seniority appears aligned")
    elif not job_config.seniority:
        seniority_score = 10
    else:
        seniority_score = 4
        gaps.append("Seniority is not explicit")

    if contract_type_is_compatible(job_config.contract_types, offer.employment_type):
        contract_score = 10
    else:
        contract_score = 0
        if job_config.contract_types:
            gaps.append("Contract type is not in target preferences")

    if candidate_profile.bonus_keywords:
        bonus_score = round(
            5 * (len(matched_bonus_keywords) / len(candidate_profile.bonus_keywords))
        )
    else:
        bonus_score = 0
    if matched_bonus_keywords:
        strengths.append(f"Bonus signals matched: {', '.join(matched_bonus_keywords[:3])}")

    total_score = (
        title_family_score
        + skills_score
        + location_remote_score
        + seniority_score
        + contract_score
        + bonus_score
    )

    breakdown = ScoreBreakdown(
        blocked=bool(blocked_reasons),
        blocked_reasons=blocked_reasons,
        title_family_score=title_family_score,
        skills_score=skills_score,
        location_remote_score=location_remote_score,
        seniority_score=seniority_score,
        contract_score=contract_score,
        bonus_score=bonus_score,
        matched_required_keywords=matched_required_keywords,
        matched_bonus_keywords=matched_bonus_keywords,
        total_score=0 if blocked_reasons else total_score,
    )

    if blocked_reasons and not gaps:
        gaps.extend(blocked_reasons)

    return breakdown, strengths[:4], gaps[:4]


def build_fallback_relevance_reason(
    offer: NormalizedJobOffer,
    breakdown: ScoreBreakdown,
    strengths: list[str],
    gaps: list[str],
) -> str:
    if breakdown.blocked:
        return (
            f"{offer.title} was blocked because "
            f"{'; '.join(breakdown.blocked_reasons[:2]).lower()}."
        )

    positive_summary = ", ".join(strengths[:2]) if strengths else "basic alignment"
    if gaps:
        return (
            f"{offer.title} scores {breakdown.total_score}/100 thanks to {positive_summary.lower()}, "
            f"with caution on {gaps[0].lower()}."
        )
    return f"{offer.title} scores {breakdown.total_score}/100 with {positive_summary.lower()}."


def build_scored_offer(
    offer: NormalizedJobOffer,
    breakdown: ScoreBreakdown,
    strengths: list[str],
    gaps: list[str],
    relevance_reason: str,
) -> ScoredJobOffer:
    return ScoredJobOffer(
        **offer.model_dump(),
        relevance_score=breakdown.total_score,
        relevance_reason=relevance_reason,
        score_breakdown_json=json.loads(breakdown.model_dump_json()),
        strengths=strengths,
        gaps=gaps,
    )
