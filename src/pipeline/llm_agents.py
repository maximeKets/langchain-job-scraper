from __future__ import annotations

import json
import logging
import re
import unicodedata
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


class LeverDiscoveryQueryEnvelope(BaseModel):
    queries: list[str] = Field(default_factory=list)


class RelevanceExplanation(BaseModel):
    relevance_reason: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class DigestSummaryOutput(BaseModel):
    subject: str
    intro: str
    highlights: list[str] = Field(default_factory=list)


MAX_LEVER_DISCOVERY_QUERIES = 12
MAX_LEVER_DISCOVERY_TERMS = 4
WTTJ_QUERY_EXTRA_TERMS = 1
WTTJ_PRIORITY_QUERY_TERMS = (
    "python",
    "fastapi",
    "rag",
    "llm",
    "ai",
    "ia",
    "automation",
    "langchain",
)


def can_use_llm(model_name: str | None = None) -> bool:
    return bool(settings.OPENAI_API_KEY and (model_name or settings.MODEL_NAME))


def build_chat_model(temperature: float = 0.0, model_name: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(model=model_name or settings.MODEL_NAME, temperature=temperature)


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
        model=build_chat_model(model_name=settings.MODEL_NAME_AUGMENTED),
        tools=[],
        system_prompt=(
            "You build a concise source-specific search plan for job scraping. "
            "Create relevant SearchIntent items for each enabled source, one per target title, "
            "using short high-signal queries. "
            "For Welcome to the Jungle / WTTJ, the query is sent directly to Algolia without "
            "structured filters. Keep WTTJ queries broad: use the target title plus at most one "
            "high-signal skill, and do not include location, remote policy, contract type, "
            "seniority, exclusions, or long keyword lists. Local scoring will handle filtering."
        ),
        response_format=SearchPlanEnvelope,
    )


@lru_cache(maxsize=1)
def get_lever_discovery_query_agent():
    return create_agent(
        model=build_chat_model(temperature=0.2),
        tools=[],
        system_prompt=(
            "You create Google search queries for discovering public Lever job board URLs. "
            "Return broad, short, high-recall queries that include site:jobs.lever.co. "
            "Each query must have at most one target title plus at most two extra terms. "
            "Do not include negative filters, long keyword lists, every skill, or every location. "
            "Do not invent company slugs; generate search queries only."
        ),
        response_format=LeverDiscoveryQueryEnvelope,
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
            "target_titles": job_config.search.target_titles or parsed_profile.target_titles,
            "target_locations": job_config.search.target_locations or parsed_profile.target_locations,
            "remote_policy": job_config.search.remote_policy or parsed_profile.remote_policy,
            "contract_types": job_config.search.contract_types or parsed_profile.contract_types,
            "seniority": job_config.search.seniority or parsed_profile.seniority,
            "required_keywords": job_config.search.required_keywords or parsed_profile.required_keywords,
            "bonus_keywords": job_config.search.bonus_keywords or parsed_profile.bonus_keywords,
            "excluded_keywords": job_config.search.excluded_keywords or parsed_profile.excluded_keywords,
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
        target_titles=job_config.search.target_titles,
        target_locations=job_config.search.target_locations,
        remote_policy=job_config.search.remote_policy,
        contract_types=job_config.search.contract_types,
        seniority=job_config.search.seniority,
        required_keywords=job_config.search.required_keywords,
        bonus_keywords=job_config.search.bonus_keywords,
        excluded_keywords=job_config.search.excluded_keywords,
        core_skills=job_config.search.required_keywords + job_config.search.bonus_keywords[:3],
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

    for source in job_config.sources.enabled:
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


def _fold_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _has_query_term(text: str, term: str) -> bool:
    normalized_text = f" {_fold_search_text(text)} "
    normalized_term = f" {_fold_search_text(term)} "
    return normalized_term in normalized_text


def _clean_search_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _wttj_extra_terms(intent: SearchIntent, candidate_profile: CandidateProfile) -> list[str]:
    title_has_priority_term = any(
        _has_query_term(intent.title, term)
        for term in [*WTTJ_PRIORITY_QUERY_TERMS, *candidate_profile.required_keywords]
    )
    if title_has_priority_term:
        return []

    profile_terms = candidate_profile.required_keywords + candidate_profile.bonus_keywords
    profile_term_lookup = {_fold_search_text(term): term for term in profile_terms}
    priority_terms = [
        profile_term_lookup.get(_fold_search_text(term), term)
        for term in WTTJ_PRIORITY_QUERY_TERMS
        if _fold_search_text(term) in profile_term_lookup or _has_query_term(intent.query, term)
    ]
    candidates = [*priority_terms, *profile_terms]

    extras: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        normalized = _fold_search_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _has_query_term(intent.title, term):
            continue
        extras.append(term)
        if len(extras) >= WTTJ_QUERY_EXTRA_TERMS:
            break
    return extras


def _complete_search_intent(
    intent: SearchIntent,
    candidate_profile: CandidateProfile,
) -> SearchIntent:
    updates = {
        "locations": intent.locations or candidate_profile.target_locations,
        "remote_policy": candidate_profile.remote_policy or intent.remote_policy,
        "contract_types": intent.contract_types or candidate_profile.contract_types,
        "required_keywords": intent.required_keywords or candidate_profile.required_keywords,
        "bonus_keywords": intent.bonus_keywords or candidate_profile.bonus_keywords,
        "excluded_keywords": intent.excluded_keywords or candidate_profile.excluded_keywords,
    }
    return intent.model_copy(update=updates)


def _normalize_wttj_intent(
    intent: SearchIntent,
    candidate_profile: CandidateProfile,
) -> SearchIntent:
    title = _clean_search_query(intent.title or intent.query)
    query_parts = [title, *_wttj_extra_terms(intent, candidate_profile)]
    query = _clean_search_query(" ".join(part for part in query_parts if part))
    return intent.model_copy(update={"query": query or _clean_search_query(intent.query)})


def normalize_search_intents(
    intents: list[SearchIntent],
    candidate_profile: CandidateProfile,
) -> list[SearchIntent]:
    normalized_intents: list[SearchIntent] = []
    seen: set[tuple[str, str, str]] = set()
    for intent in intents:
        completed = _complete_search_intent(intent, candidate_profile)
        if completed.source == "wttj":
            completed = _normalize_wttj_intent(completed, candidate_profile)

        key = (
            completed.source.casefold(),
            completed.title.casefold(),
            completed.query.casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized_intents.append(completed)
    return normalized_intents


def build_search_plan_with_agent(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
) -> list[SearchIntent]:
    fallback = normalize_search_intents(
        fallback_build_search_plan(candidate_profile, job_config),
        candidate_profile,
    )
    if not can_use_llm(settings.MODEL_NAME_AUGMENTED):
        logger.info("OpenAI API key/model not configured; using fallback search plan")
        return fallback

    prompt = (
        "Candidate profile:\n"
        f"{candidate_profile.model_dump_json(indent=2)}\n\n"
        "Target sources:\n"
        f"{json.dumps(job_config.sources.enabled, ensure_ascii=True)}"
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
                if intent.source in job_config.sources.enabled
            ]
            normalized_intents = normalize_search_intents(intents, candidate_profile)
            logger.info("Search plan agent returned intents=%s", len(normalized_intents))
            return normalized_intents
        logger.warning("Search plan agent returned no search intents; using fallback")
    except Exception:
        logger.exception("Search plan agent failed; using fallback")
    return fallback


def _clean_query_fragment(fragment: str) -> str:
    cleaned = "".join(char for char in fragment if char.isprintable()).strip()
    return cleaned.strip("'\"")


def _quote_query_fragment(fragment: str) -> str:
    if not fragment:
        return fragment
    if " " in fragment:
        return f'"{fragment}"'
    return fragment


def _simplify_lever_discovery_query(query: str) -> str | None:
    fragments = re.findall(r'"[^"]+"|\S+', query)
    terms: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        if fragment.startswith("site:"):
            continue
        if fragment.startswith("-"):
            continue

        cleaned = _clean_query_fragment(fragment)
        if not cleaned or cleaned.startswith("-"):
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(cleaned)
        if len(terms) >= MAX_LEVER_DISCOVERY_TERMS:
            break

    if not terms:
        return None
    return " ".join(["site:jobs.lever.co", *[_quote_query_fragment(term) for term in terms]])


def _dedupe_queries(queries: list[str], limit: int = MAX_LEVER_DISCOVERY_QUERIES) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = _simplify_lever_discovery_query(query)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def fallback_build_lever_discovery_queries(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
) -> list[str]:
    titles = candidate_profile.target_titles or job_config.search.target_titles or ["AI Engineer"]
    required_keywords = candidate_profile.required_keywords or job_config.search.required_keywords
    bonus_keywords = candidate_profile.bonus_keywords or job_config.search.bonus_keywords
    priority_keywords = [
        keyword
        for keyword in ["python", "ai", "llm", "rag", "fastapi", "langchain"]
        if keyword in {term.casefold() for term in required_keywords + bonus_keywords}
    ]
    if not priority_keywords:
        priority_keywords = (required_keywords + bonus_keywords)[:3]

    queries: list[str] = []
    for title in titles:
        queries.append(f'site:jobs.lever.co "{title}"')
        if priority_keywords:
            queries.append(f'site:jobs.lever.co "{title}" {priority_keywords[0]}')
        if candidate_profile.remote_policy != "onsite":
            queries.append(f'site:jobs.lever.co "{title}" remote')

    return _dedupe_queries(queries)


def build_lever_discovery_queries_with_agent(
    candidate_profile: CandidateProfile,
    job_config: JobSearchConfig,
) -> list[str]:
    fallback = fallback_build_lever_discovery_queries(candidate_profile, job_config)
    if not can_use_llm():
        logger.info("OpenAI API key/model not configured; using fallback Lever discovery queries")
        return fallback

    prompt = (
        "Candidate profile:\n"
        f"{candidate_profile.model_dump_json(indent=2)}\n\n"
        "Job search config:\n"
        f"{json.dumps(job_config.model_dump(), ensure_ascii=True, indent=2)}\n\n"
        "Generate 8-12 broad Google queries to discover relevant Lever company boards. "
        "Keep each query short: site:jobs.lever.co plus a title and at most two extra terms."
    )
    try:
        logger.info("Invoking LangChain Lever discovery query agent")
        result = get_lever_discovery_query_agent().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        structured = result.get("structured_response")
        if isinstance(structured, LeverDiscoveryQueryEnvelope) and structured.queries:
            queries = _dedupe_queries(structured.queries)
            logger.info("Lever discovery query agent returned queries=%s", len(queries))
            return queries
        logger.warning("Lever discovery query agent returned no queries; using fallback")
    except Exception:
        logger.exception("Lever discovery query agent failed; using fallback")
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
