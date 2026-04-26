from __future__ import annotations

from src.config import settings
from src.db.operations import get_active_company_tokens
from src.pipeline.lever_discovery import (
    LeverValidation,
    discover_lever_companies,
    extract_lever_company_token,
    search_lever_urls_with_serper,
)


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def test_extract_lever_company_token_from_job_url() -> None:
    assert (
        extract_lever_company_token("https://jobs.lever.co/scaleai/senior-ai-engineer")
        == "scaleai"
    )
    assert extract_lever_company_token("https://example.com/scaleai/job") is None
    assert extract_lever_company_token("https://jobs.lever.co/") is None


def test_search_lever_urls_with_serper_extracts_organic_and_sitelinks(monkeypatch) -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            return FakeResponse(
                {
                    "organic": [
                        {
                            "link": "https://jobs.lever.co/scaleai/role-1",
                            "sitelinks": [
                                {"link": "https://jobs.lever.co/langchain/role-2"},
                            ],
                        }
                    ]
                }
            )

    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")

    links = search_lever_urls_with_serper("site:jobs.lever.co AI Engineer", session=FakeSession())

    assert links == [
        "https://jobs.lever.co/scaleai/role-1",
        "https://jobs.lever.co/langchain/role-2",
    ]


def test_discover_lever_companies_persists_active_valid_tokens(monkeypatch, temp_db: str) -> None:
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(
        "src.pipeline.lever_discovery.search_lever_urls_with_serper",
        lambda query, session: [
            "https://jobs.lever.co/scaleai/role-1",
            "https://jobs.lever.co/inactiveco/role-2",
            "https://example.com/not-lever",
        ],
    )
    monkeypatch.setattr(
        "src.pipeline.lever_discovery.validate_lever_company_token",
        lambda token, session: LeverValidation(
            token=token,
            is_active=token == "scaleai",
            job_count=3 if token == "scaleai" else 0,
        ),
    )

    persisted = discover_lever_companies(["site:jobs.lever.co AI Engineer"])

    assert persisted == ["scaleai"]
    assert get_active_company_tokens("lever") == ["scaleai"]
