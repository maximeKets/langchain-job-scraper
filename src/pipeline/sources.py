from __future__ import annotations

import logging
from typing import Any

import requests

from src.db.operations import get_active_company_tokens
from src.pipeline.config import JobSearchConfig
from src.pipeline.models import NormalizedJobOffer, SearchIntent
from src.pipeline.scoring import (
    canonicalize_job_url,
    normalize_contract_type,
    normalize_remote_policy,
    normalize_text,
    parse_datetime,
)
from src.tools.retrieval_utils import build_default_headers, html_to_text

logger = logging.getLogger(__name__)

WTTJ_ALGOLIA_APP_ID = "CSEKHVMS53"
WTTJ_ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
WTTJ_ALGOLIA_INDEX_PREFIX = "wttj_jobs_production"


def filter_intents_for_source(search_intents: list[SearchIntent], source: str) -> list[SearchIntent]:
    return [intent for intent in search_intents if intent.source == source]


def offer_matches_any_intent(
    title: str,
    description: str,
    intents: list[SearchIntent],
) -> list[SearchIntent]:
    combined_text = normalize_text(f"{title} {description}")
    matches: list[SearchIntent] = []
    for intent in intents:
        title_match = normalize_text(intent.title) in combined_text or normalize_text(title) in normalize_text(intent.query)
        keyword_match = any(
            normalize_text(keyword) in combined_text for keyword in intent.required_keywords
        )
        if title_match or keyword_match or not intent.required_keywords:
            matches.append(intent)
    return matches


def dedupe_offers(offers: list[NormalizedJobOffer]) -> list[NormalizedJobOffer]:
    deduped: dict[str, NormalizedJobOffer] = {}
    for offer in offers:
        canonical_url = canonicalize_job_url(offer.url)
        existing = deduped.get(canonical_url)
        if existing is None:
            deduped[canonical_url] = offer.model_copy(update={"canonical_url": canonical_url})
            continue

        merged_queries = sorted(set(existing.matched_queries + offer.matched_queries))
        merged_offer = existing.model_copy(
            update={
                "description": existing.description or offer.description,
                "published_date": existing.published_date or offer.published_date,
                "matched_queries": merged_queries,
                "source_payload": existing.source_payload or offer.source_payload,
            }
        )
        deduped[canonical_url] = merged_offer
    result = list(deduped.values())
    logger.info("Deduplicated offers: input=%s output=%s", len(offers), len(result))
    return result


def parse_wttj_hits(hits: list[dict[str, Any]], locale: str, intent: SearchIntent) -> list[NormalizedJobOffer]:
    offers: list[NormalizedJobOffer] = []
    for hit in hits:
        offices = hit.get("offices") or []
        office = offices[0] if offices else {}
        location = ", ".join(
            part for part in [office.get("city"), office.get("state"), office.get("country")] if part
        ) or None
        organization = hit.get("organization") or {}
        slug = hit.get("slug") or hit.get("reference") or hit.get("objectID")
        company_slug = organization.get("slug") or "unknown-company"
        url = f"https://www.welcometothejungle.com/{locale}/companies/{company_slug}/jobs/{slug}"
        description = " ".join(
            value
            for value in [
                hit.get("summary"),
                " ".join(hit.get("key_missions") or []),
            ]
            if value
        )

        offers.append(
            NormalizedJobOffer(
                source="wttj",
                source_id=str(hit.get("reference") or hit.get("objectID") or slug),
                title=hit.get("name") or "Untitled role",
                company=organization.get("name") or company_slug,
                url=url,
                canonical_url=canonicalize_job_url(url),
                category=intent.title,
                location=location,
                remote_policy=normalize_remote_policy(hit.get("remote")),
                employment_type=normalize_contract_type(
                    hit.get("employment_type") or hit.get("contract_type")
                ),
                description=description or None,
                published_date=parse_datetime(hit.get("published_at")),
                matched_queries=[intent.query],
                source_payload=hit,
            )
        )
    return offers


def fetch_wttj_jobs(
    job_config: JobSearchConfig,
    search_intents: list[SearchIntent],
) -> list[NormalizedJobOffer]:
    intents = filter_intents_for_source(search_intents, "wttj")
    if not intents:
        logger.info("WTTJ scraper skipped: no search intents")
        return []

    logger.info("WTTJ scraper running: intents=%s", len(intents))
    offers: list[NormalizedJobOffer] = []
    session = requests.Session()
    for intent in intents:
        logger.info("WTTJ query started: %s", intent.query)
        payload = {
            "requests": [
                {
                    "indexName": f"{WTTJ_ALGOLIA_INDEX_PREFIX}_{job_config.wttj_locale}",
                    "params": (
                        f"query={intent.query}"
                        f"&hitsPerPage={job_config.wttj_hits_per_page}"
                        "&page=0"
                    ),
                }
            ]
        }
        headers = {
            **build_default_headers(),
            "Content-Type": "application/json",
            "Origin": "https://www.welcometothejungle.com",
            "Referer": "https://www.welcometothejungle.com/fr/jobs",
            "X-Algolia-API-Key": WTTJ_ALGOLIA_API_KEY,
            "X-Algolia-Application-Id": WTTJ_ALGOLIA_APP_ID,
        }

        try:
            response = session.post(
                f"https://{WTTJ_ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/*/queries",
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            hits = response.json().get("results", [{}])[0].get("hits", [])
            parsed_offers = parse_wttj_hits(hits, job_config.wttj_locale, intent)
            logger.info(
                "WTTJ query completed: query=%s hits=%s parsed_offers=%s",
                intent.query,
                len(hits),
                len(parsed_offers),
            )
            offers.extend(parsed_offers)
        except Exception as error:
            logger.warning("WTTJ scraping failed for query '%s': %s", intent.query, error)

    return dedupe_offers(offers)


def parse_greenhouse_jobs(
    board_token: str,
    jobs: list[dict[str, Any]],
    intents: list[SearchIntent],
) -> list[NormalizedJobOffer]:
    offers: list[NormalizedJobOffer] = []
    for job in jobs:
        content = html_to_text(job.get("content") or "")
        matched_intents = offer_matches_any_intent(job.get("title", ""), content, intents)
        if not matched_intents:
            continue

        metadata_entries = job.get("metadata") or []
        metadata_map = {
            entry.get("name", "").casefold(): entry.get("value")
            for entry in metadata_entries
            if isinstance(entry, dict)
        }
        location = (job.get("location") or {}).get("name")
        employment_type = normalize_contract_type(
            metadata_map.get("employment type") or metadata_map.get("type")
        )
        remote_policy = "remote" if "remote" in normalize_text(location) else None

        offers.append(
            NormalizedJobOffer(
                source="greenhouse",
                source_id=str(job.get("id")),
                title=job.get("title") or "Untitled role",
                company=board_token.replace("-", " ").title(),
                url=job.get("absolute_url") or "",
                canonical_url=canonicalize_job_url(job.get("absolute_url") or ""),
                category=matched_intents[0].title,
                location=location,
                remote_policy=normalize_remote_policy(remote_policy),
                employment_type=employment_type,
                description=content or None,
                published_date=parse_datetime(job.get("updated_at")),
                matched_queries=[intent.query for intent in matched_intents],
                source_payload=job,
            )
        )
    return offers


def fetch_greenhouse_jobs(
    job_config: JobSearchConfig,
    search_intents: list[SearchIntent],
) -> list[NormalizedJobOffer]:
    intents = filter_intents_for_source(search_intents, "greenhouse")
    if not intents or not job_config.greenhouse_board_tokens:
        logger.info(
            "Greenhouse scraper skipped: intents=%s board_tokens=%s",
            len(intents),
            len(job_config.greenhouse_board_tokens),
        )
        return []

    logger.info(
        "Greenhouse scraper running: intents=%s board_tokens=%s",
        len(intents),
        len(job_config.greenhouse_board_tokens),
    )
    offers: list[NormalizedJobOffer] = []
    for board_token in job_config.greenhouse_board_tokens:
        logger.info("Greenhouse board fetch started: %s", board_token)
        try:
            response = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true",
                headers=build_default_headers(),
                timeout=20,
            )
            response.raise_for_status()
            jobs = response.json().get("jobs", [])
            parsed_offers = parse_greenhouse_jobs(board_token, jobs, intents)
            logger.info(
                "Greenhouse board fetch completed: board=%s jobs=%s parsed_offers=%s",
                board_token,
                len(jobs),
                len(parsed_offers),
            )
            offers.extend(parsed_offers)
        except Exception as error:
            logger.warning(
                "Greenhouse scraping failed for board '%s': %s", board_token, error
            )
    return dedupe_offers(offers)


def parse_lever_jobs(
    company_token: str,
    jobs: list[dict[str, Any]],
    intents: list[SearchIntent],
) -> list[NormalizedJobOffer]:
    offers: list[NormalizedJobOffer] = []
    for job in jobs:
        description = html_to_text(job.get("descriptionPlain") or job.get("description") or "")
        matched_intents = offer_matches_any_intent(job.get("text", ""), description, intents)
        if not matched_intents:
            continue

        categories = job.get("categories") or {}
        location = categories.get("location")
        remote_policy = normalize_remote_policy(
            job.get("workplaceType")
            or ("remote" if "remote" in normalize_text(location) else None)
        )
        employment_type = normalize_contract_type(categories.get("commitment"))
        url = job.get("hostedUrl") or job.get("applyUrl") or ""

        offers.append(
            NormalizedJobOffer(
                source="lever",
                source_id=str(job.get("id")),
                title=job.get("text") or "Untitled role",
                company=company_token.replace("-", " ").title(),
                url=url,
                canonical_url=canonicalize_job_url(url),
                category=matched_intents[0].title,
                location=location,
                remote_policy=remote_policy,
                employment_type=employment_type,
                description=description or None,
                published_date=parse_datetime(job.get("createdAt")),
                matched_queries=[intent.query for intent in matched_intents],
                source_payload=job,
            )
        )
    return offers


def fetch_lever_jobs(
    job_config: JobSearchConfig,
    search_intents: list[SearchIntent],
) -> list[NormalizedJobOffer]:
    intents = filter_intents_for_source(search_intents, "lever")
    company_tokens = sorted(
        {
            token.strip().lower()
            for token in [*job_config.lever_company_tokens, *get_active_company_tokens("lever")]
            if token.strip()
        }
    )
    if not intents or not company_tokens:
        logger.info(
            "Lever scraper skipped: intents=%s company_tokens=%s",
            len(intents),
            len(company_tokens),
        )
        return []

    logger.info(
        "Lever scraper running: intents=%s company_tokens=%s",
        len(intents),
        len(company_tokens),
    )
    offers: list[NormalizedJobOffer] = []
    for company_token in company_tokens:
        logger.info("Lever company fetch started: %s", company_token)
        try:
            response = requests.get(
                f"https://api.lever.co/v0/postings/{company_token}?mode=json",
                headers=build_default_headers(),
                timeout=20,
            )
            response.raise_for_status()
            jobs = response.json()
            parsed_offers = parse_lever_jobs(company_token, jobs, intents)
            logger.info(
                "Lever company fetch completed: company=%s jobs=%s parsed_offers=%s",
                company_token,
                len(jobs),
                len(parsed_offers),
            )
            offers.extend(parsed_offers)
        except Exception as error:
            logger.warning("Lever scraping failed for company '%s': %s", company_token, error)
    return dedupe_offers(offers)
