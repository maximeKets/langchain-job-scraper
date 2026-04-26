from __future__ import annotations

import time

from src.scripts.scraper_benchmark_utils import (
    build_single_url_parser,
    report_failure,
    report_success,
)
from src.tools.custom_stealth_tools import fetch_page_with_curl_cffi


def main() -> None:
    parser = build_single_url_parser(
        description="Benchmark du tool custom curl-cffi.",
        tool_name="fetch_page_with_curl_cffi",
    )
    parser.add_argument(
        "--impersonate",
        default="chrome124",
        help="Empreinte TLS a utiliser pour curl-cffi.",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        text = fetch_page_with_curl_cffi.invoke(
            {
                "url": args.url,
                "impersonate": args.impersonate,
                "timeout_seconds": args.timeout,
            }
        )
        report_success(
            category="custom",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
            metadata={"impersonate": args.impersonate},
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

