from __future__ import annotations

import time

from src.scripts.scraper_benchmark_utils import (
    build_recursive_parser,
    combine_documents,
    report_failure,
    report_success,
)
from langchain_community.document_loaders import RecursiveUrlLoader
from src.tools.retrieval_utils import html_to_text


def main() -> None:
    parser = build_recursive_parser(
        description="Benchmark du RecursiveUrlLoader de langchain-community.",
        tool_name="RecursiveUrlLoader",
    )
    args = parser.parse_args()
    started_at = time.perf_counter()

    try:
        loader = RecursiveUrlLoader(
            url=args.url,
            max_depth=args.max_depth,
            timeout=args.timeout,
            extractor=html_to_text,
            link_regex=args.link_regex,
        )
        docs = loader.load()
        text, metadata = combine_documents(docs, max_docs=args.max_docs)
        report_success(
            category="langchain-community",
            tool_name=args.tool_name,
            target=args.url,
            started_at=started_at,
            text=text,
            preview_chars=args.preview_chars,
            metadata=metadata,
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
