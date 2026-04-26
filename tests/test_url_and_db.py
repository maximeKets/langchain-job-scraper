from __future__ import annotations

from src.db.operations import get_pending_digest_offers, mark_offers_as_sent, upsert_scored_job_offer
from src.pipeline.models import ScoredJobOffer
from src.pipeline.scoring import canonicalize_job_url


def test_canonicalize_job_url_removes_tracking_params() -> None:
    raw_url = "https://jobs.example.com/opening/123?utm_source=test&gh_src=abc&keep=1#fragment"
    canonical = canonicalize_job_url(raw_url)

    assert canonical == "https://jobs.example.com/opening/123?keep=1"


def test_upsert_scored_job_offer_updates_existing_record(temp_db: str) -> None:
    first = ScoredJobOffer(
        source="greenhouse",
        source_id="1",
        title="Data Engineer",
        company="Acme",
        url="https://boards.greenhouse.io/acme/jobs/1?gh_src=abc",
        canonical_url="https://boards.greenhouse.io/acme/jobs/1",
        category="Data Engineer",
        location="Paris",
        remote_policy="hybrid",
        employment_type="full_time",
        description="Python SQL role",
        matched_queries=["Data Engineer Paris"],
        source_payload={"version": 1},
        relevance_score=72,
        relevance_reason="Strong match",
        score_breakdown_json={"total_score": 72},
        strengths=["Strong title alignment"],
        gaps=[],
    )
    second = first.model_copy(
        update={
            "description": "Updated description",
            "relevance_score": 81,
            "relevance_reason": "Updated match",
            "score_breakdown_json": {"total_score": 81},
        }
    )

    created = upsert_scored_job_offer(first)
    updated = upsert_scored_job_offer(second)

    assert created.id == updated.id
    assert updated.relevance_score == 81


def test_mark_offers_as_sent_only_affects_selected_offers(temp_db: str) -> None:
    offer = ScoredJobOffer(
        source="wttj",
        source_id="2",
        title="AI Engineer",
        company="Beta",
        url="https://www.welcometothejungle.com/fr/companies/beta/jobs/2",
        canonical_url="https://www.welcometothejungle.com/fr/companies/beta/jobs/2",
        category="AI Engineer",
        location="Paris",
        remote_policy="hybrid",
        employment_type="full_time",
        description="LLM role",
        matched_queries=["AI Engineer Paris"],
        source_payload={"version": 1},
        relevance_score=90,
        relevance_reason="Excellent match",
        score_breakdown_json={"total_score": 90},
        strengths=["Great alignment"],
        gaps=[],
    )

    stored = upsert_scored_job_offer(offer)
    pending = get_pending_digest_offers(60, 10)
    assert pending and pending[0].status == "new"

    mark_offers_as_sent([stored.id])
    pending_after = get_pending_digest_offers(60, 10)
    assert pending_after == []
