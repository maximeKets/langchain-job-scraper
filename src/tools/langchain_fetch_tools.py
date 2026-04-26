from __future__ import annotations

import httpx
import requests
from langchain_core.tools import tool

from src.tools.retrieval_utils import (
    DEFAULT_TIMEOUT_SECONDS,
    build_default_headers,
    html_to_text,
)


@tool
def fetch_page_with_httpx(url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Fetch a recruitment page with httpx and return cleaned visible text."""
    response = httpx.get(
        url,
        headers=build_default_headers(),
        follow_redirects=True,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return html_to_text(response.text)


@tool
def fetch_page_with_requests(
    url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> str:
    """Fetch a recruitment page with requests and return cleaned visible text."""
    response = requests.get(
        url,
        headers=build_default_headers(),
        allow_redirects=True,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return html_to_text(response.text)

