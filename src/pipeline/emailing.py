from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import settings
from src.pipeline.llm_agents import DigestSummaryOutput
from src.pipeline.models import DigestEntry

logger = logging.getLogger(__name__)


def render_digest_email(
    digest_entries: list[DigestEntry],
    digest_summary: DigestSummaryOutput,
) -> str:
    if not digest_entries:
        return f"""
        <html>
          <body>
            <h2>{digest_summary.subject}</h2>
            <p>{digest_summary.intro}</p>
          </body>
        </html>
        """.strip()

    cards = []
    for entry in digest_entries:
        cards.append(
            f"""
            <li style="margin-bottom: 18px;">
              <strong>{entry.title}</strong> - {entry.company}<br/>
              Score: <strong>{entry.relevance_score}/100</strong><br/>
              Source: {entry.source} | Zone: {entry.location or 'N/A'}<br/>
              <a href="{entry.url}">{entry.url}</a><br/>
              <em>{entry.relevance_reason}</em>
            </li>
            """.strip()
        )

    highlight_block = "".join(
        f"<li>{highlight}</li>" for highlight in digest_summary.highlights
    )

    return f"""
    <html>
      <body>
        <h2>{digest_summary.subject}</h2>
        <p>{digest_summary.intro}</p>
        <ul>{highlight_block}</ul>
        <hr/>
        <ol>{''.join(cards)}</ol>
      </body>
    </html>
    """.strip()


def send_digest_email(recipient_email: str, subject: str, html_body: str) -> bool:
    if settings.EMAIL_DELIVERY_MODE != "live" or not settings.SMTP_PASSWORD:
        logger.info(
            "Email simulation mode: recipient=%s subject=%s body_chars=%s",
            recipient_email,
            subject,
            len(html_body),
        )
        logger.debug("Simulated email body:\n%s", html_body)
        return False

    logger.info(
        "Sending live email: smtp_host=%s smtp_port=%s recipient=%s subject=%s",
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        recipient_email,
        subject,
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, recipient_email, msg.as_string())
    logger.info("Live email sent: recipient=%s subject=%s", recipient_email, subject)
    return True
