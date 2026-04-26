from __future__ import annotations

import json

from src.agents import summarizer
from src.db.operations import get_pending_digest_offers, upsert_scored_job_offer
from src.pipeline.models import ScoredJobOffer


def make_offer(source_id: str, score: int) -> ScoredJobOffer:
    return ScoredJobOffer(
        source="wttj",
        source_id=source_id,
        title=f"AI Engineer {source_id}",
        company="Example Co",
        url=f"https://example.com/jobs/{source_id}",
        canonical_url=f"https://example.com/jobs/{source_id}",
        category="AI Engineer",
        location="Remote France",
        remote_policy="remote",
        employment_type="full_time",
        description="Python FastAPI RAG automation role",
        matched_queries=["AI Engineer Python FastAPI"],
        source_payload={"fixture": True},
        relevance_score=score,
        relevance_reason="Strong match",
        score_breakdown_json={"total_score": score},
        strengths=["Strong title alignment"],
        gaps=[],
    )


def test_get_unread_jobs_returns_all_pending_offers_above_min_score(temp_db: str) -> None:
    high_offer = upsert_scored_job_offer(make_offer("high", 80))
    upsert_scored_job_offer(make_offer("low", 40))

    payload = json.loads(summarizer.get_unread_jobs.invoke({}))

    assert payload["min_relevance_score"] == 60
    assert [job["id"] for job in payload["jobs"]] == [high_offer.id]


def test_send_summary_email_marks_offers_sent_after_success(monkeypatch, temp_db: str) -> None:
    offer = upsert_scored_job_offer(make_offer("send-success", 80))
    monkeypatch.setattr(
        summarizer,
        "send_digest_email",
        lambda recipient_email, subject, html_body: None,
    )

    result = summarizer.send_summary_email.invoke(
        {
            "recipient_email": "test@example.com",
            "subject": "Digest",
            "html_body": "<p>Hello</p>",
            "offer_ids_to_mark_sent": [offer.id],
        }
    )

    assert "Email sent successfully" in result
    assert get_pending_digest_offers(60) == []


def test_send_summary_email_does_not_mark_sent_after_failure(monkeypatch, temp_db: str) -> None:
    offer = upsert_scored_job_offer(make_offer("send-failure", 80))

    def fail_send(recipient_email: str, subject: str, html_body: str) -> None:
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(summarizer, "send_digest_email", fail_send)

    result = summarizer.send_summary_email.invoke(
        {
            "recipient_email": "test@example.com",
            "subject": "Digest",
            "html_body": "<p>Hello</p>",
            "offer_ids_to_mark_sent": [offer.id],
        }
    )

    assert "Failed to send email" in result
    assert [pending.id for pending in get_pending_digest_offers(60)] == [offer.id]
