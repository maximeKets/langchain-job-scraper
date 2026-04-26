from __future__ import annotations

import logging
import operator
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from src.db.operations import (
    get_pending_digest_offers,
    init_db,
    mark_offers_as_sent,
    upsert_scored_job_offer,
)
from src.pipeline.config import DEFAULT_PIPELINE_CONFIG_PATH, JobSearchConfig, load_job_search_config
from src.pipeline.emailing import render_digest_email, send_digest_email
from src.pipeline.llm_agents import (
    build_lever_discovery_queries_with_agent,
    build_digest_summary_with_agent,
    build_search_plan_with_agent,
    enrich_score_with_agent,
    parse_candidate_profile_with_agent,
)
from src.pipeline.lever_discovery import discover_lever_companies
from src.pipeline.models import CandidateProfile, DigestEntry, NormalizedJobOffer, ScoredJobOffer, SearchIntent
from src.pipeline.scoring import (
    build_fallback_relevance_reason,
    build_scored_offer,
    score_offer,
)
from src.pipeline.sources import dedupe_offers, fetch_greenhouse_jobs, fetch_lever_jobs, fetch_wttj_jobs

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    config_path: str
    job_search_config: JobSearchConfig
    profile_markdown: str
    candidate_profile: CandidateProfile
    search_intents: list[SearchIntent]
    lever_discovery_queries: list[str]
    discovered_lever_company_tokens: list[str]
    source_jobs: Annotated[list[NormalizedJobOffer], operator.add]
    normalized_offers: list[NormalizedJobOffer]
    scored_offers: list[ScoredJobOffer]
    persisted_offer_ids: list[int]
    digest_entries: list[DigestEntry]
    digest_subject: str
    digest_html: str
    sent_offer_ids: list[int]
    run_summary: str


def load_config(state: PipelineState) -> dict[str, Any]:
    config_path = state.get("config_path") or str(DEFAULT_PIPELINE_CONFIG_PATH)
    logger.info("Loading job search config from %s", config_path)
    loaded = load_job_search_config(config_path)
    init_db()
    logger.info(
        "Config loaded for profile=%s sources=%s titles=%s locations=%s",
        loaded.settings.profile_id,
        ",".join(loaded.settings.sources.enabled),
        len(loaded.settings.search.target_titles),
        ",".join(loaded.settings.search.target_locations),
    )
    return {
        "job_search_config": loaded.settings,
        "profile_markdown": loaded.profile_markdown,
        "source_jobs": [],
    }


def parse_profile_agent(state: PipelineState) -> dict[str, Any]:
    logger.info("Parsing candidate profile")
    candidate_profile = parse_candidate_profile_with_agent(
        state["job_search_config"], state["profile_markdown"]
    )
    logger.info(
        "Candidate profile parsed: profile_id=%s target_titles=%s required_keywords=%s",
        candidate_profile.profile_id,
        len(candidate_profile.target_titles),
        len(candidate_profile.required_keywords),
    )
    return {"candidate_profile": candidate_profile}


def build_search_plan_agent(state: PipelineState) -> dict[str, Any]:
    logger.info("Building search plan")
    search_intents = build_search_plan_with_agent(
        state["candidate_profile"], state["job_search_config"]
    )
    by_source: dict[str, int] = {}
    for intent in search_intents:
        by_source[intent.source] = by_source.get(intent.source, 0) + 1
    logger.info("Search plan built: intents=%s by_source=%s", len(search_intents), by_source)
    return {"search_intents": search_intents}


def discover_lever_sources_agent(state: PipelineState) -> dict[str, Any]:
    job_config = state["job_search_config"]
    if "lever" not in job_config.sources.enabled:
        logger.info("Lever source discovery skipped: lever is not enabled")
        return {"lever_discovery_queries": [], "discovered_lever_company_tokens": []}

    queries = build_lever_discovery_queries_with_agent(state["candidate_profile"], job_config)
    discovered_tokens = discover_lever_companies(queries)
    logger.info(
        "Lever source discovery completed: queries=%s discovered_tokens=%s",
        len(queries),
        len(discovered_tokens),
    )
    return {
        "lever_discovery_queries": queries,
        "discovered_lever_company_tokens": discovered_tokens,
    }


def dispatch_scrapers(state: PipelineState) -> list[Send]:
    enabled_sources = set(state["job_search_config"].sources.enabled)
    scrapers = [
        Send(
            "wttj_scraper",
            {
                "job_search_config": state["job_search_config"],
                "search_intents": state["search_intents"],
            },
        ),
        Send(
            "greenhouse_scraper",
            {
                "job_search_config": state["job_search_config"],
                "search_intents": state["search_intents"],
            },
        ),
        Send(
            "lever_scraper",
            {
                "job_search_config": state["job_search_config"],
                "search_intents": state["search_intents"],
            },
        ),
    ]
    dispatched = [send.node for send in scrapers if send.node.replace("_scraper", "") in enabled_sources]
    logger.info("Dispatching scraper nodes: %s", ", ".join(dispatched) or "none")
    return [
        send for send in scrapers if send.node.replace("_scraper", "") in enabled_sources
    ]


def wttj_scraper(state: PipelineState) -> dict[str, Any]:
    logger.info("Starting WTTJ scraper")
    jobs = fetch_wttj_jobs(state["job_search_config"], state["search_intents"])
    logger.info("WTTJ scraper completed: offers=%s", len(jobs))
    return {"source_jobs": jobs}


def greenhouse_scraper(state: PipelineState) -> dict[str, Any]:
    logger.info("Starting Greenhouse scraper")
    jobs = fetch_greenhouse_jobs(state["job_search_config"], state["search_intents"])
    logger.info("Greenhouse scraper completed: offers=%s", len(jobs))
    return {"source_jobs": jobs}


def lever_scraper(state: PipelineState) -> dict[str, Any]:
    logger.info("Starting Lever scraper")
    jobs = fetch_lever_jobs(state["job_search_config"], state["search_intents"])
    logger.info("Lever scraper completed: offers=%s", len(jobs))
    return {"source_jobs": jobs}


def normalize_offers(state: PipelineState) -> dict[str, Any]:
    source_jobs = state.get("source_jobs", [])
    normalized_offers = dedupe_offers(source_jobs)
    logger.info(
        "Normalized offers: source_jobs=%s unique_offers=%s",
        len(source_jobs),
        len(normalized_offers),
    )
    return {"normalized_offers": normalized_offers}


def score_offers_agent(state: PipelineState) -> dict[str, Any]:
    scored_offers: list[ScoredJobOffer] = []
    candidate_profile = state["candidate_profile"]
    job_config = state["job_search_config"]
    normalized_offers = state.get("normalized_offers", [])

    logger.info("Scoring offers: count=%s", len(normalized_offers))

    for index, offer in enumerate(normalized_offers, start=1):
        logger.info(
            "Scoring offer %s/%s: %s at %s",
            index,
            len(normalized_offers),
            offer.title,
            offer.company,
        )
        breakdown, strengths, gaps = score_offer(candidate_profile, job_config, offer)
        fallback_reason = build_fallback_relevance_reason(offer, breakdown, strengths, gaps)
        explanation = enrich_score_with_agent(
            candidate_profile,
            offer,
            breakdown,
            fallback_reason,
            strengths,
            gaps,
        )
        scored_offers.append(
            build_scored_offer(
                offer=offer,
                breakdown=breakdown,
                strengths=explanation.strengths or strengths,
                gaps=explanation.gaps or gaps,
                relevance_reason=explanation.relevance_reason or fallback_reason,
            )
        )

    logger.info("Scoring completed: scored_offers=%s", len(scored_offers))
    return {"scored_offers": scored_offers}


def persist_offers(state: PipelineState) -> dict[str, Any]:
    persisted_offer_ids: list[int] = []
    scored_offers = state.get("scored_offers", [])
    logger.info("Persisting scored offers: count=%s", len(scored_offers))
    for offer in scored_offers:
        persisted_offer = upsert_scored_job_offer(offer)
        persisted_offer_ids.append(persisted_offer.id)
    logger.info("Persistence completed: persisted_offer_ids=%s", persisted_offer_ids)
    return {"persisted_offer_ids": persisted_offer_ids}


def build_digest_agent(state: PipelineState) -> dict[str, Any]:
    logger.info(
        "Building digest: min_relevance_score=%s limit=all",
        state["job_search_config"].digest.min_relevance_score,
    )
    pending_offers = get_pending_digest_offers(
        min_relevance_score=state["job_search_config"].digest.min_relevance_score,
    )

    digest_entries = [
        DigestEntry(
            offer_id=offer.id,
            title=offer.title,
            company=offer.company,
            relevance_score=offer.relevance_score or 0,
            location=offer.location,
            source=offer.source or "unknown",
            url=offer.url,
            relevance_reason=offer.relevance_reason or "No relevance explanation available.",
        )
        for offer in pending_offers
    ]

    digest_summary = build_digest_summary_with_agent(
        state["candidate_profile"], digest_entries
    )
    digest_html = render_digest_email(digest_entries, digest_summary)
    logger.info(
        "Digest built: entries=%s subject=%s",
        len(digest_entries),
        digest_summary.subject,
    )
    return {
        "digest_entries": digest_entries,
        "digest_subject": digest_summary.subject,
        "digest_html": digest_html,
    }


def send_email(state: PipelineState) -> dict[str, Any]:
    digest_entries = state.get("digest_entries", [])
    if not digest_entries:
        logger.info("No pending offers met the digest threshold; email will not be sent")
        return {
            "sent_offer_ids": [],
            "run_summary": "No pending offers met the digest threshold.",
        }

    offer_ids = [entry.offer_id for entry in digest_entries]
    logger.info(
        "Sending digest email: recipient=%s offers=%s",
        state["job_search_config"].digest.recipient_email,
        len(offer_ids),
    )
    delivered = send_digest_email(
        recipient_email=state["job_search_config"].digest.recipient_email,
        subject=state["digest_subject"],
        html_body=state["digest_html"],
    )
    if not delivered:
        logger.info("Email not delivered live; offers kept as new: offer_ids=%s", offer_ids)
        return {
            "sent_offer_ids": [],
            "run_summary": "Email not delivered live; offers kept as new.",
        }

    mark_offers_as_sent(offer_ids)
    logger.info("Digest email sent and offers marked as sent: offer_ids=%s", offer_ids)
    return {
        "sent_offer_ids": offer_ids,
        "run_summary": (
            f"Sent {len(offer_ids)} offers to "
            f"{state['job_search_config'].digest.recipient_email}."
        ),
    }


def get_job_search_graph():
    builder = StateGraph(PipelineState)
    builder.add_node("load_config", load_config)
    builder.add_node("parse_profile_agent", parse_profile_agent)
    builder.add_node("build_search_plan_agent", build_search_plan_agent)
    builder.add_node("discover_lever_sources_agent", discover_lever_sources_agent)
    builder.add_node("wttj_scraper", wttj_scraper)
    builder.add_node("greenhouse_scraper", greenhouse_scraper)
    builder.add_node("lever_scraper", lever_scraper)
    builder.add_node("normalize_offers", normalize_offers)
    builder.add_node("score_offers_agent", score_offers_agent)
    builder.add_node("persist_offers", persist_offers)
    builder.add_node("build_digest_agent", build_digest_agent)
    builder.add_node("send_email", send_email)

    builder.add_edge(START, "load_config")
    builder.add_edge("load_config", "parse_profile_agent")
    builder.add_edge("parse_profile_agent", "build_search_plan_agent")
    builder.add_edge("build_search_plan_agent", "discover_lever_sources_agent")
    builder.add_conditional_edges("discover_lever_sources_agent", dispatch_scrapers)
    builder.add_edge("wttj_scraper", "normalize_offers")
    builder.add_edge("greenhouse_scraper", "normalize_offers")
    builder.add_edge("lever_scraper", "normalize_offers")
    builder.add_edge("normalize_offers", "score_offers_agent")
    builder.add_edge("score_offers_agent", "persist_offers")
    builder.add_edge("persist_offers", "build_digest_agent")
    builder.add_edge("build_digest_agent", "send_email")
    builder.add_edge("send_email", END)

    return builder.compile()
