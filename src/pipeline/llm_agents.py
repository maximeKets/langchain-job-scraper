from __future__ import annotations

import json
import logging
from functools import lru_cache

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import settings
from src.pipeline.config import JobSearchConfig
from src.pipeline.models import CandidateProfile, DigestEntry, NormalizedJobOffer, ScoreBreakdown, SearchIntent

logger = logging.getLogger(__name__)


class SearchPlanEnvelope(BaseModel):
    search_intents: list[SearchIntent] = Field(default_factory=list)


class RelevanceExplanation(BaseModel):
    relevance_reason: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class DigestSummaryOutput(BaseModel):
    subject: str
    intro: str
    highlights: list[str] = Field(default_factory=list)


def can_use_llm() -> bool:
    return bool(settings.OPENAI_API_KEY and settings.MODEL_NAME)


def build_chat_model(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(model=settings.MODEL_NAME, temperature=temperature)


@lru_cache(maxsize=1)
def get_profile_parser_agent():
    return create_agent(
        model=build_chat_model(),
        tools=[],
        system_prompt=(
            "You extract a structured candidate profile from a markdown CV and a stable YAML job search config. "
            "Prefer the YAML config for explicit preferences, enrich it with concise insights from the markdown CV, "
            "and return a complete CandidateProfile."
        ),
        response_format=CandidateProfile,
    )


@lru_cache(maxsize=1)
def get_search_plan_agent():
    return create_agent(
        model=build_chat_model(),
        tools=[],
        system_prompt=(
            "You build a concise source-specific search plan for job scraping. "
            "Create relevant SearchIntent items for each enabled source, one per target title, "
            "using short high-signal queries."
        ),
        response_format=SearchPlanEnvelope,
    )


@lru_cache(maxsize=1)
def get_relevance_explainer_agent():
    return create_agent(
        model=build_chat_model(),
        tools=[],
        system_prompt=(
            "You explain a deterministic job relevance score. "
            "Do not change the score. Produce a short explanation plus strengths and gaps that are faithful "
            "to the provided breakdown."
        ),
        response_format=RelevanceExplanation,
    )


@lru_cache(maxsize=1)
def get_digest_summary_agent():
    return create_agent(
        model=build_chat_model(temperature=0.2),
        tools=[],
        system_prompt=(
            "You write a concise email digest for relevant job opportunities. "
            "Return a short subject, a brief intro, and 2-4 highlights."
        ),
        response_format=DigestSummaryOutput,
    )


def merge_candidate_profile(
    parsed_profile: CandidateProfile,
    job_config: JobSearchConfig,
    raw_markdown: str,
) -> CandidateProfile:
    merged = parsed_profile.model_copy(
        update={
            "profile_id": job_config.profile_id,
            "target_titles": job_config.target_titles or parsed_profile.target_titles,
            "target_locations": job_config.target_locations or parsed_profile.target_locations,
            "remote_policy": job_config.remote_policy or parsed_profile.remote_policy,
            "contract_types": job_config.contract_types or parsed_profile.contract_types,
            "seniority": job_config.seniority or parsed_profile.seniority,
            "required_keywords": job_config.required_keywords or parsed_profile.required_keywords,
            "bonus_keywords": job_config.bonus_keywords or parsed_profile.bonus_keywords,
            "excluded_keywords": job_config.excluded_keywords or parsed_profile.excluded_keywords,
            "raw_markdown": raw_markdown,
        }
    )
    if not merged.candidate_summary:
        merged.candidate_summary = raw_markdown[:300]
    return merged


def fallback_parse_candidate_profile(
    job_config: JobSearchConfig,
    raw_markdown: str,
) -> CandidateProfile:
    paragraphs = [line.strip() for line in raw_markdown.splitlines() if line.strip()]
    summary = " ".join(paragraphs[:4])[:500]
    return CandidateProfile(
        profile_id=job_config.profile_id,
        candidate_summary=summary or "Candidate profile imported from markdown CV.",
        experience_summary=summary or "Experience extracted from markdown profile.",
        target_titles=job_config.target_titles,
        target_locations=job_config.target_locations,
        remote_policy=job_config.remote_policy,
        contract_types=job_config.contract_types,
        seniority=job_config.seniority,
        required_keywords=job_config.required_keywords,
        bonus_keywords=job_config.bonus_keywords,
        excluded_keywords=job_config.excluded_keywords,
        core_skills=job_config.required_keywords + job_config.bonus_keywords[:3],
        preferred_domains=["data", "ai", "ml", "software"],
        raw_markdown=raw_markdown,
    )


def parse_candidate_profile_with_agent(
    job_config: JobSearchConfig,
    raw_markdown: str,
) -> CandidateProfile:
    fallback = fallback_parse_candidate_profile(job_config, raw_markdown)
    if not can_use_llm():
        logger.info("OpenAI API key/model not configured; using fallback candidate profile parser")
        return fallback

    prompt = (
        "Job search config:\n"
        f"{json.dumps(job_config.model_dump(), ensure_ascii=True, indent=2)}\n\n"
        "Candidate markdown CV:\n"
        f"{raw_markdown}"
    )
    try:
        logger.info("Invoking LangChain profile parser agent")
        result = get_profile_parser_agent().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        structured = result.get("structured_response")
        if isinstance(structured, CandidateProfile):
            logger.info("Profile parser agent returned structured CandidateProfile")
            return merge_candidate_profile(structured, job_config, raw_markdown)
        logger.warning("Profile parser agent returned no structured CandidateProfile; using fallback")
    except Exception:
        logger.exception("Profile parser agent failed; using fallback")
    return fallback


def fallback_build_search_plan(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
) -> list[SearchIntent]:
    search_intents: list[SearchIntent] = []
    title_candidates = candidate_profile.target_titles or ["Data Engineer"]
    required_keywords = candidate_profile.required_keywords[:3]

    for source in job_config.target_sources:
        for title in title_candidates:
            query_parts = [title]
            query_parts.extend(required_keywords)
            if candidate_profile.target_locations:
                query_parts.append(candidate_profile.target_locations[0])
            query = " ".join(part for part in query_parts if part).strip()
            search_intents.append(
                SearchIntent(
                    source=source,
                    title=title,
                    query=query,
                    locations=candidate_profile.target_locations,
                    remote_policy=candidate_profile.remote_policy,
                    contract_types=candidate_profile.contract_types,
                    required_keywords=candidate_profile.required_keywords,
                    bonus_keywords=candidate_profile.bonus_keywords,
                    excluded_keywords=candidate_profile.excluded_keywords,
                )
            )
    return search_intents


def build_search_plan_with_agent(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
) -> list[SearchIntent]:
    fallback = fallback_build_search_plan(candidate_profile, job_config)
    if not can_use_llm():
        logger.info("OpenAI API key/model not configured; using fallback search plan")
        return fallback

    prompt = (
        "Candidate profile:\n"
        f"{candidate_profile.model_dump_json(indent=2)}\n\n"
        "Target sources:\n"
        f"{json.dumps(job_config.target_sources, ensure_ascii=True)}"
    )
    try:
        logger.info("Invoking LangChain search plan agent")
        result = get_search_plan_agent().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        structured = result.get("structured_response")
        if isinstance(structured, SearchPlanEnvelope) and structured.search_intents:
            intents = [
                intent
                for intent in structured.search_intents
                if intent.source in job_config.target_sources
            ]
            logger.info("Search plan agent returned intents=%s", len(intents))
            return intents
        logger.warning("Search plan agent returned no search intents; using fallback")
    except Exception:
        logger.exception("Search plan agent failed; using fallback")
    return fallback


def enrich_score_with_agent(
    candidate_profile: CandidateProfile,
    offer: NormalizedJobOffer,
    breakdown: ScoreBreakdown,
    fallback_reason: str,
    fallback_strengths: list[str],
    fallback_gaps: list[str],
) -> RelevanceExplanation:
    fallback = RelevanceExplanation(
        relevance_reason=fallback_reason,
        strengths=fallback_strengths,
        gaps=fallback_gaps,
    )
    if not can_use_llm():
        logger.debug("OpenAI API key/model not configured; using fallback relevance explanation")
        return fallback

    prompt = (
        "Candidate profile:\n"
        f"{candidate_profile.model_dump_json(indent=2)}\n\n"
        "Offer:\n"
        f"{offer.model_dump_json(indent=2)}\n\n"
        "Deterministic score breakdown:\n"
        f"{breakdown.model_dump_json(indent=2)}"
    )
    try:
        logger.info("Invoking LangChain relevance explainer agent for offer=%s", offer.source_id)
        result = get_relevance_explainer_agent().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        structured = result.get("structured_response")
        if isinstance(structured, RelevanceExplanation):
            return structured
        logger.warning(
            "Relevance explainer agent returned no structured explanation for offer=%s; using fallback",
            offer.source_id,
        )
    except Exception:
        logger.exception(
            "Relevance explainer agent failed for offer=%s; using fallback",
            offer.source_id,
        )
    return fallback


def fallback_digest_summary(
    candidate_profile: CandidateProfile,
    digest_entries: list[DigestEntry],
) -> DigestSummaryOutput:
    if not digest_entries:
        return DigestSummaryOutput(
            subject=f"Aucune nouvelle offre pertinente pour {candidate_profile.profile_id}",
            intro="Aucune nouvelle offre n'a depasse le seuil de pertinence aujourd'hui.",
            highlights=[],
        )

    best_offer = digest_entries[0]
    return DigestSummaryOutput(
        subject=f"Top {len(digest_entries)} offres pour {candidate_profile.profile_id}",
        intro=(
            f"Voici les meilleures opportunites identifiees aujourd'hui. "
            f"La meilleure offre est {best_offer.title} chez {best_offer.company} "
            f"avec un score de {best_offer.relevance_score}/100."
        ),
        highlights=[
            f"{entry.company}: {entry.title} ({entry.relevance_score}/100)"
            for entry in digest_entries[:3]
        ],
    )


def build_digest_summary_with_agent(
    candidate_profile: CandidateProfile,
    digest_entries: list[DigestEntry],
) -> DigestSummaryOutput:
    fallback = fallback_digest_summary(candidate_profile, digest_entries)
    if not can_use_llm():
        logger.info("OpenAI API key/model not configured; using fallback digest summary")
        return fallback

    prompt = (
        "Candidate profile:\n"
        f"{candidate_profile.model_dump_json(indent=2)}\n\n"
        "Digest entries:\n"
        f"{json.dumps([entry.model_dump() for entry in digest_entries], ensure_ascii=True, indent=2)}"
    )
    try:
        logger.info("Invoking LangChain digest summary agent for entries=%s", len(digest_entries))
        result = get_digest_summary_agent().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        structured = result.get("structured_response")
        if isinstance(structured, DigestSummaryOutput):
            return structured
        logger.warning("Digest summary agent returned no structured output; using fallback")
    except Exception:
        logger.exception("Digest summary agent failed; using fallback")
    return fallback
