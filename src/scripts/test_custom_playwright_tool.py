from __future__ import annotations

import asyncio
import time

from src.scripts.scraper_benchmark_utils import (
    build_single_url_parser,
    report_failure,
    report_success,
)
from src.tools.playwright_scraper import fetch_page_content


async def run() -> None:
    parser = build_single_url_parser(
        description="Benchmark du tool Playwright custom existant.",
        tool_name="fetch_page_content",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        text = await fetch_page_content.ainvoke({"url": args.url})
        if text.startswith("Error:") or text.startswith("Erreur fatale"):
            raise RuntimeError(text)
        report_success(
            category="custom",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
        )
    except Exception as error:
        report_failure(
            category="custom",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            error=error,
        )


if __name__ == "__main__":
    asyncio.run(run())
