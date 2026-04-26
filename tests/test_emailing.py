from __future__ import annotations

from src.config import settings
from src.pipeline.emailing import send_digest_email


def test_send_digest_email_returns_false_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "mock")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    delivered = send_digest_email(
        recipient_email="test@example.com",
        subject="Digest",
        html_body="<p>Hello</p>",
    )

    assert delivered is False


def test_send_digest_email_returns_false_when_live_password_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "live")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")

    delivered = send_digest_email(
        recipient_email="test@example.com",
        subject="Digest",
        html_body="<p>Hello</p>",
    )

    assert delivered is False


def test_send_digest_email_returns_true_after_live_smtp_success(monkeypatch) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int) -> None:
            calls.append(("connect", (host, port)))

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *args: object) -> None:
            calls.append(("close", args))

        def starttls(self) -> None:
            calls.append(("starttls", ()))

        def login(self, user: str, password: str) -> None:
            calls.append(("login", (user, password)))

        def sendmail(self, sender: str, recipient: str, message: str) -> None:
            calls.append(("sendmail", (sender, recipient, message)))

    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "live")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_USER", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 2525)
    monkeypatch.setattr("src.pipeline.emailing.smtplib.SMTP", FakeSMTP)

    delivered = send_digest_email(
        recipient_email="test@example.com",
        subject="Digest",
        html_body="<p>Hello</p>",
    )

    assert delivered is True
    assert calls[0] == ("connect", ("smtp.example.com", 2525))
    assert ("login", ("sender@example.com", "secret")) in calls
    assert any(call[0] == "sendmail" for call in calls)
