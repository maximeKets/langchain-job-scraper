from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import List

from langchain.agents import create_agent
from langchain_core.tools import tool

from src.config import settings
from src.db.operations import get_pending_digest_offers, mark_offers_as_sent
from src.pipeline.config import load_job_search_config
from src.pipeline.emailing import send_digest_email

logger = logging.getLogger(__name__)


@tool
def get_unread_jobs() -> str:
    """
    Retrieve all unsent job offers whose relevance score is greater than or equal
    to the configured min_relevance_score.

    Returns:
        A JSON string containing the relevant pending jobs.
    """
    loaded_config = load_job_search_config(settings.JOB_SEARCH_CONFIG_PATH)
    min_score = loaded_config.settings.digest.min_relevance_score
    offers = get_pending_digest_offers(min_relevance_score=min_score)

    if not offers:
        return json.dumps(
            {
                "min_relevance_score": min_score,
                "jobs": [],
                "message": "No unsent job offers met the relevance threshold.",
            },
            ensure_ascii=True,
        )

    jobs = [
        {
            "id": offer.id,
            "title": offer.title,
            "company": offer.company,
            "url": offer.url,
            "category": offer.category,
            "source": offer.source,
            "location": offer.location,
            "remote_policy": offer.remote_policy,
            "employment_type": offer.employment_type,
            "relevance_score": offer.relevance_score,
            "relevance_reason": offer.relevance_reason,
        }
        for offer in offers
    ]
    logger.info(
        "Summarizer retrieved pending relevant jobs: min_score=%s count=%s",
        min_score,
        len(jobs),
    )
    return json.dumps(
        {
            "min_relevance_score": min_score,
            "recipient_email": loaded_config.settings.digest.recipient_email,
            "jobs": jobs,
        },
        ensure_ascii=True,
    )


@tool
def send_summary_email(
    recipient_email: str,
    subject: str,
    html_body: str,
    offer_ids_to_mark_sent: List[int],
) -> str:
    """
    Send an email summary and mark the included job offers as sent only after
    successful email delivery.

    Args:
        recipient_email: Email recipient.
        subject: Email subject.
        html_body: HTML body to send.
        offer_ids_to_mark_sent: Database IDs of offers included in the email.
    """
    try:
        delivered = send_digest_email(
            recipient_email=recipient_email,
            subject=subject,
            html_body=html_body,
        )
        if not delivered:
            logger.info(
                "Summarizer email not delivered live; offers kept as new: recipient=%s offers=%s",
                recipient_email,
                len(offer_ids_to_mark_sent),
            )
            return "Email not delivered live; offers kept as new."

        mark_offers_as_sent(offer_ids_to_mark_sent)
        logger.info(
            "Summarizer email sent and offers marked sent: recipient=%s offers=%s",
            recipient_email,
            len(offer_ids_to_mark_sent),
        )
        return "Email sent successfully and database updated."
    except Exception as error:
        logger.exception("Summarizer failed to send email")
        return f"Failed to send email: {error}"


@lru_cache(maxsize=1)
def get_summarizer_agent():
    return create_agent(
        model=settings.MODEL_NAME,
        tools=[get_unread_jobs, send_summary_email],
        system_prompt=(
            "You summarize relevant job offers for the candidate. "
            "Use get_unread_jobs to retrieve every unsent offer whose score is at or above "
            "the configured min_relevance_score. Do not apply a top-N limit. "
            "If jobs are returned, format a concise HTML email grouped by source or category, "
            "include each job's title, company, location, score, reason, and URL, then call "
            f"send_summary_email. Use {settings.RECIPIENT_EMAIL} as the recipient unless "
            "the user provides another recipient."
        ),
    )


summarizer_agent = get_summarizer_agent()
