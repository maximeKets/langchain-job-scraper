from __future__ import annotations

import os

from bs4 import BeautifulSoup

DEFAULT_RECRUITMENT_URL = os.getenv(
    "SCRAPER_TEST_URL",
    "https://www.welcometothejungle.com/fr/jobs?query=data&page=1",
)
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "30"))
DEFAULT_USER_AGENT = os.getenv(
    "SCRAPER_USER_AGENT",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 "
        "LangChainJobScraper/0.1"
    ),
)
MAX_TEXT_LENGTH = int(os.getenv("SCRAPER_MAX_TEXT_LENGTH", "15000"))

os.environ.setdefault("USER_AGENT", DEFAULT_USER_AGENT)


def build_default_headers(user_agent: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def html_to_text(html: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(
        ["script", "style", "noscript", "svg", "img", "header", "footer", "nav"]
    ):
        element.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:max_length]

