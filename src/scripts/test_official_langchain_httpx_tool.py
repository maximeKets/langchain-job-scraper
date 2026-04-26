from __future__ import annotations

import time

from src.scripts.scraper_benchmark_utils import (
    build_single_url_parser,
    report_failure,
    report_success,
)
from src.tools.langchain_fetch_tools import fetch_page_with_httpx


def main() -> None:
    parser = build_single_url_parser(
        description="Benchmark du tool officiel LangChain base sur httpx.",
        tool_name="fetch_page_with_httpx",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        text = fetch_page_with_httpx.invoke(
            {"url": args.url, "timeout_seconds": args.timeout}
        )
        report_success(
            category="official-langchain",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
        )
    except Exception as error:
        report_failure(
            category="official-langchain",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            error=error,
        )


if __name__ == "__main__":
    main()

