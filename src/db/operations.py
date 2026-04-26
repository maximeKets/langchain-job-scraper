from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any, List, Optional

from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.config import resolve_database_url, settings
from src.db.models import Base, CompanySource, JobOffer
from src.pipeline.scoring import canonicalize_job_url

DB_PATH = settings.DB_PATH
engine = create_engine(DB_PATH)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

JOB_OFFERS_MIGRATION_COLUMNS = {
    "source": "VARCHAR(100)",
    "location": "VARCHAR(255)",
    "remote_policy": "VARCHAR(100)",
    "employment_type": "VARCHAR(100)",
    "relevance_score": "INTEGER",
    "relevance_reason": "TEXT",
    "score_breakdown_json": "TEXT",
    "source_payload": "TEXT",
    "sent_at": "DATETIME",
}


def configure_database(db_path: str | None = None) -> None:
    """Reconfigure the SQLAlchemy engine. Useful for tests."""
    global DB_PATH, engine, SessionLocal
    DB_PATH = resolve_database_url(db_path or os.environ.get("DB_PATH", "sqlite:///sqlite.db"))
    engine = create_engine(DB_PATH)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_job_offer_columns() -> None:
    inspector = inspect(engine)
    if "job_offers" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("job_offers")}
    with engine.begin() as connection:
        for column_name, column_sql in JOB_OFFERS_MIGRATION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE job_offers ADD COLUMN {column_name} {column_sql}")
                )


def init_db() -> None:
    """Initialise la base de données en créant les tables si elles n'existent pas."""
    Base.metadata.create_all(bind=engine)
    ensure_job_offer_columns()


def _serialize_offer_payload(payload: Any) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=True)


def _extract_offer_dict(
    offer: Any,
    company: Optional[str] = None,
    url: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    if hasattr(offer, "model_dump"):
        return offer.model_dump()
    if isinstance(offer, dict):
        return offer
    return {
        "title": offer,
        "company": company,
        "url": url,
        "category": category,
        "description": description,
    }


def upsert_scored_job_offer(offer: Any) -> JobOffer:
    offer_data = _extract_offer_dict(offer)
    canonical_url = canonicalize_job_url(offer_data["canonical_url"] or offer_data["url"])

    with SessionLocal() as session:
        stmt = select(JobOffer).where(JobOffer.url == canonical_url)
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            existing.title = offer_data["title"]
            existing.company = offer_data["company"]
            existing.category = offer_data["category"]
            existing.source = offer_data.get("source")
            existing.location = offer_data.get("location")
            existing.remote_policy = offer_data.get("remote_policy")
            existing.employment_type = offer_data.get("employment_type")
            existing.published_date = offer_data.get("published_date")
            existing.description = offer_data.get("description")
            existing.relevance_score = offer_data.get("relevance_score")
            existing.relevance_reason = offer_data.get("relevance_reason")
            existing.score_breakdown_json = _serialize_offer_payload(
                offer_data.get("score_breakdown_json")
            )
            existing.source_payload = _serialize_offer_payload(offer_data.get("source_payload"))
            session.commit()
            session.refresh(existing)
            return existing

        new_offer = JobOffer(
            title=offer_data["title"],
            company=offer_data["company"],
            url=canonical_url,
            category=offer_data["category"],
            source=offer_data.get("source"),
            location=offer_data.get("location"),
            remote_policy=offer_data.get("remote_policy"),
            employment_type=offer_data.get("employment_type"),
            published_date=offer_data.get("published_date"),
            description=offer_data.get("description"),
            relevance_score=offer_data.get("relevance_score"),
            relevance_reason=offer_data.get("relevance_reason"),
            score_breakdown_json=_serialize_offer_payload(
                offer_data.get("score_breakdown_json")
            ),
            source_payload=_serialize_offer_payload(offer_data.get("source_payload")),
            status="new",
        )
        session.add(new_offer)
        session.commit()
        session.refresh(new_offer)
        return new_offer


def upsert_job_offer(
    title: Any,
    company: Optional[str] = None,
    url: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
) -> bool:
    """Backwards-compatible wrapper around the scored job upsert."""
    offer_data = _extract_offer_dict(title, company, url, category, description)
    offer_data.setdefault("source", "legacy")
    offer_data.setdefault("location", None)
    offer_data.setdefault("remote_policy", None)
    offer_data.setdefault("employment_type", None)
    offer_data.setdefault("published_date", None)
    offer_data.setdefault("relevance_score", None)
    offer_data.setdefault("relevance_reason", None)
    offer_data.setdefault("score_breakdown_json", {})
    offer_data.setdefault("source_payload", {})
    offer_data.setdefault("canonical_url", offer_data["url"])

    try:
        existing = upsert_scored_job_offer(offer_data)
        return existing is not None
    except IntegrityError:
        return False


def get_new_offers() -> List[JobOffer]:
    """Récupère toutes les offres dont le statut est 'new'."""
    with SessionLocal() as session:
        stmt = select(JobOffer).where(JobOffer.status == "new")
        return session.scalars(stmt).all()


def get_pending_digest_offers(
    min_relevance_score: int,
    limit: int | None = None,
) -> List[JobOffer]:
    with SessionLocal() as session:
        stmt = (
            select(JobOffer)
            .where(JobOffer.status == "new")
            .where(JobOffer.relevance_score.is_not(None))
            .where(JobOffer.relevance_score >= min_relevance_score)
            .order_by(
                JobOffer.relevance_score.desc(),
                JobOffer.published_date.desc(),
                JobOffer.created_at.desc(),
            )
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return session.scalars(stmt).all()


def mark_offers_as_sent(offer_ids: List[int]) -> None:
    """Marque une liste d'offres comme envoyées."""
    if not offer_ids:
        return

    with SessionLocal() as session:
        stmt = (
            update(JobOffer)
            .where(JobOffer.id.in_(offer_ids))
            .values(status="sent", sent_at=datetime.now(UTC).replace(tzinfo=None))
        )
        session.execute(stmt)
        session.commit()


def upsert_company_source(
    *,
    source: str,
    token: str,
    company_name: str | None,
    discovery_query: str | None,
    discovery_url: str | None,
    is_active: bool,
    last_validated_at: datetime | None,
    last_seen_job_at: datetime | None,
    last_job_count: int,
) -> CompanySource:
    normalized_source = source.strip().lower()
    normalized_token = token.strip().lower()

    with SessionLocal() as session:
        stmt = select(CompanySource).where(
            CompanySource.source == normalized_source,
            CompanySource.token == normalized_token,
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if existing:
            existing.company_name = company_name or existing.company_name
            existing.discovery_query = discovery_query or existing.discovery_query
            existing.discovery_url = discovery_url or existing.discovery_url
            existing.is_active = is_active
            existing.last_validated_at = last_validated_at
            existing.last_seen_job_at = last_seen_job_at
            existing.last_job_count = last_job_count
            session.commit()
            session.refresh(existing)
            return existing

        company_source = CompanySource(
            source=normalized_source,
            token=normalized_token,
            company_name=company_name,
            discovery_query=discovery_query,
            discovery_url=discovery_url,
            is_active=is_active,
            last_validated_at=last_validated_at,
            last_seen_job_at=last_seen_job_at,
            last_job_count=last_job_count,
        )
        session.add(company_source)
        session.commit()
        session.refresh(company_source)
        return company_source


def get_active_company_tokens(source: str) -> List[str]:
    with SessionLocal() as session:
        stmt = (
            select(CompanySource.token)
            .where(CompanySource.source == source.strip().lower())
            .where(CompanySource.is_active.is_(True))
            .order_by(CompanySource.last_seen_job_at.desc(), CompanySource.token.asc())
        )
        return list(session.scalars(stmt).all())
