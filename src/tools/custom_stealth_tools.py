from __future__ import annotations

from curl_cffi import requests as curl_requests
from langchain_core.tools import tool

from src.tools.retrieval_utils import (
    DEFAULT_TIMEOUT_SECONDS,
    build_default_headers,
    html_to_text,
)


@tool
def fetch_page_with_curl_cffi(
    url: str,
    impersonate: str = "chrome124",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Fetch a page with curl-cffi and a Chrome TLS fingerprint."""
    response = curl_requests.get(
        url,
        headers=build_default_headers(),
        impersonate=impersonate,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return html_to_text(response.text)


@tool
def fetch_page_with_seleniumbase(
    url: str,
    headless: bool = True,
    wait_seconds: int = 4,
) -> str:
    """Fetch a JS-heavy page with SeleniumBase UC mode and return cleaned text."""
    from seleniumbase import Driver

    driver = Driver(uc=True, headless=headless)
    try:
        driver.get(url)
        driver.sleep(wait_seconds)
        return html_to_text(driver.page_source)
    finally:
        driver.quit()

