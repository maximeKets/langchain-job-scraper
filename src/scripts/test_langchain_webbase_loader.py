from __future__ import annotations

import time

from src.scripts.scraper_benchmark_utils import (
    build_single_url_parser,
    report_failure,
    report_success,
)
from langchain_community.document_loaders import WebBaseLoader


def main() -> None:
    parser = build_single_url_parser(
        description="Benchmark du WebBaseLoader de langchain-community.",
        tool_name="WebBaseLoader",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        loader = WebBaseLoader(
            web_paths=[args.url],
            requests_per_second=1,
            raise_for_status=True,
            show_progress=False,
        )
        docs = loader.load()
        text = docs[0].page_content if docs else ""
        report_success(
            category="langchain-community",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
            metadata={"document_count": len(docs)},
        )
    except Exception as error:
        report_failure(
            category="langchain-community",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            error=error,
        )


if __name__ == "__main__":
    main()
