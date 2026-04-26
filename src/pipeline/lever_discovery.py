from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests

from src.config import settings
from src.db.operations import upsert_company_source
from src.pipeline.scoring import parse_datetime
from src.tools.retrieval_utils import build_default_headers

logger = logging.getLogger(__name__)

LEVER_HOST = "jobs.lever.co"
TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,254}$")


@dataclass(frozen=True)
class DiscoveredLeverCompany:
    token: str
    discovery_query: str
    discovery_url: str


@dataclass(frozen=True)
class LeverValidation:
    token: str
    is_active: bool
    job_count: int
    last_seen_job_at: datetime | None = None


def extract_lever_company_token(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != LEVER_HOST:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    token = path_parts[0].strip().lower()
    if not TOKEN_PATTERN.match(token):
        return None
    return token


def extract_links_from_serper_result(result: dict[str, Any]) -> list[str]:
    links: list[str] = []
    link = result.get("link")
    if isinstance(link, str):
        links.append(link)

    for sitelink in result.get("sitelinks") or []:
        if not isinstance(sitelink, dict):
            continue
        sitelink_url = sitelink.get("link")
        if isinstance(sitelink_url, str):
            links.append(sitelink_url)
    return links


def search_lever_urls_with_serper(
    query: str,
    *,
    session: requests.Session | None = None,
) -> list[str]:
    if not settings.SERPER_API_KEY:
        logger.info("Serper API key not configured; Lever discovery search skipped")
        return []

    client = session or requests.Session()
    response = client.post(
        settings.SERPER_SEARCH_URL,
        headers={
            **build_default_headers(),
            "X-API-KEY": settings.SERPER_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "q": query,
            "num": settings.SERPER_RESULTS_PER_QUERY,
            "gl": "fr",
            "hl": "en",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    links: list[str] = []
    for result in payload.get("organic") or []:
        if isinstance(result, dict):
            links.extend(extract_links_from_serper_result(result))
    return links


def validate_lever_company_token(
    token: str,
    *,
    session: requests.Session | None = None,
) -> LeverValidation:
    client = session or requests.Session()
    response = client.get(
        f"https://api.lever.co/v0/postings/{token}?mode=json",
        headers=build_default_headers(),
        timeout=20,
    )
    response.raise_for_status()
    jobs = response.json()
    if not isinstance(jobs, list):
        return LeverValidation(token=token, is_active=False, job_count=0)

    parsed_dates = [
        parsed
        for parsed in (parse_datetime(job.get("createdAt")) for job in jobs if isinstance(job, dict))
        if parsed is not None
    ]
    last_seen_job_at = max(parsed_dates) if parsed_dates else None
    return LeverValidation(
        token=token,
        is_active=bool(jobs),
        job_count=len(jobs),
        last_seen_job_at=last_seen_job_at,
    )


def discover_lever_companies(queries: list[str]) -> list[str]:
    if not queries:
        logger.info("Lever discovery skipped: no search queries")
        return []
    if not settings.SERPER_API_KEY:
        logger.info("Lever discovery skipped: SERPER_API_KEY is not configured")
        return []

    session = requests.Session()
    discovered_by_token: dict[str, DiscoveredLeverCompany] = {}
    for query in queries:
        logger.info("Lever discovery query started: %s", query)
        try:
            urls = search_lever_urls_with_serper(query, session=session)
        except Exception as error:
            logger.warning("Lever discovery Serper query failed for '%s': %s", query, error)
            continue

        for url in urls:
            token = extract_lever_company_token(url)
            if not token or token in discovered_by_token:
                continue
            discovered_by_token[token] = DiscoveredLeverCompany(
                token=token,
                discovery_query=query,
                discovery_url=url,
            )

    persisted_tokens: list[str] = []
    validated_at = datetime.now(UTC).replace(tzinfo=None)
    for discovered in discovered_by_token.values():
        try:
            validation = validate_lever_company_token(discovered.token, session=session)
        except Exception as error:
            logger.warning(
                "Lever discovery validation failed for company '%s': %s",
                discovered.token,
                error,
            )
            continue

        if not validation.is_active:
            logger.info("Lever discovery ignored inactive company: %s", discovered.token)
            continue

        upsert_company_source(
            source="lever",
            token=discovered.token,
            company_name=discovered.token.replace("-", " ").title(),
            discovery_query=discovered.discovery_query,
            discovery_url=discovered.discovery_url,
            is_active=True,
            last_validated_at=validated_at,
            last_seen_job_at=validation.last_seen_job_at,
            last_job_count=validation.job_count,
        )
        persisted_tokens.append(discovered.token)

    logger.info(
        "Lever discovery completed: queries=%s discovered=%s persisted=%s",
        len(queries),
        len(discovered_by_token),
        len(persisted_tokens),
    )
    return persisted_tokens
