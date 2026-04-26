from __future__ import annotations

import time

from src.scripts.scraper_benchmark_utils import (
    build_single_url_parser,
    report_failure,
    report_success,
)
from src.tools.custom_stealth_tools import fetch_page_with_seleniumbase


def main() -> None:
    parser = build_single_url_parser(
        description="Benchmark du tool custom SeleniumBase UC.",
        tool_name="fetch_page_with_seleniumbase",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Desactive le mode headless pour observer le navigateur.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=4,
        help="Temps d'attente apres la navigation.",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        text = fetch_page_with_seleniumbase.invoke(
            {
                "url": args.url,
                "headless": not args.show_browser,
                "wait_seconds": args.wait_seconds,
            }
        )
        report_success(
            category="custom",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
            metadata={
                "headless": not args.show_browser,
                "wait_seconds": args.wait_seconds,
            },
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
    main()
