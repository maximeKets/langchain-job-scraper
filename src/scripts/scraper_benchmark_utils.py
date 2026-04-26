from __future__ import annotations

import argparse
import json
import time
from typing import Any

from src.tools.retrieval_utils import DEFAULT_RECRUITMENT_URL, DEFAULT_TIMEOUT_SECONDS


def build_single_url_parser(description: str, tool_name: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--url", default=DEFAULT_RECRUITMENT_URL, help="URL a scraper.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout reseau en secondes.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=500,
        help="Nombre de caracteres affiches dans l'aperçu.",
    )
    parser.add_argument(
        "--tool-name",
        default=tool_name,
        help="Nom affiché dans le rapport final.",
    )
    return parser


def build_recursive_parser(description: str, tool_name: str) -> argparse.ArgumentParser:
    parser = build_single_url_parser(description=description, tool_name=tool_name)
    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="Profondeur maximale de recursion.",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=5,
        help="Nombre maximal de documents affiches dans le resume.",
    )
    parser.add_argument(
        "--link-regex",
        default=None,
        help="Regex optionnelle pour filtrer les liens suivis.",
    )
    return parser


def combine_documents(docs: list[Any], max_docs: int = 5) -> tuple[str, dict[str, Any]]:
    limited_docs = docs[:max_docs]
    combined_text = "\n\n".join(doc.page_content for doc in limited_docs if doc.page_content)
    metadata = {
        "document_count": len(docs),
        "document_count_in_preview": len(limited_docs),
        "sources": [doc.metadata.get("source") for doc in limited_docs],
    }
    return combined_text, metadata


def report_success(
    category: str,
    tool_name: str,
    target: str,
    started_at: float,
    text: str,
    preview_chars: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    duration = time.perf_counter() - started_at
    print(f"Category: {category}")
    print(f"Tool: {tool_name}")
    print(f"Target: {target}")
    print(f"Status: success")
    print(f"DurationSeconds: {duration:.2f}")
    print(f"ExtractedChars: {len(text)}")
    if metadata:
        print("Metadata:")
        print(json.dumps(metadata, ensure_ascii=True, indent=2))
    print("Preview:")
    print(text[:preview_chars])


def report_failure(
    category: str,
    tool_name: str,
    target: str,
    started_at: float,
    error: Exception,
) -> None:
    duration = time.perf_counter() - started_at
    print(f"Category: {category}")
    print(f"Tool: {tool_name}")
    print(f"Target: {target}")
    print(f"Status: failure")
    print(f"DurationSeconds: {duration:.2f}")
    print(f"ErrorType: {type(error).__name__}")
    print(f"Error: {error}")

