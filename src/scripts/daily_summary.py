from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.db.operations import init_db
from src.logging_config import setup_logging
from src.pipeline.graph import get_job_search_graph

LOG_PATH = setup_logging()
logger = logging.getLogger(__name__)


def summarize_update(update: Any) -> str:
    if not isinstance(update, dict):
        return type(update).__name__

    parts: list[str] = []
    for key, value in update.items():
        if isinstance(value, list):
            parts.append(f"{key}={len(value)}")
        elif value is None:
            parts.append(f"{key}=None")
        else:
            parts.append(f"{key}={type(value).__name__}")
    return ", ".join(parts) or "no state update"


def main() -> None:
    logger.info("Daily job search summary started")
    logger.info("Writing logs to %s", LOG_PATH)
    logger.info("Job search config path: %s", settings.JOB_SEARCH_CONFIG_PATH)

    logger.info("Initializing database")
    init_db()

    logger.info("Building LangGraph workflow")
    graph = get_job_search_graph()
    config = {
        "configurable": {"thread_id": "daily_cron_job"},
        "run_name": "daily_job_search_summary",
        "tags": ["daily-summary", "job-search"],
        "metadata": {"config_path": settings.JOB_SEARCH_CONFIG_PATH},
    }

    logger.info("Executing job watch pipeline")
    result: dict[str, Any] = {}
    try:
        for chunk in graph.stream(
            {"config_path": settings.JOB_SEARCH_CONFIG_PATH},
            config=config,
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                logger.info(
                    "LangGraph node completed: %s | %s",
                    node_name,
                    summarize_update(update),
                )
                if isinstance(update, dict):
                    result.update(update)
    except Exception:
        logger.exception("Daily job search workflow failed")
        raise

    logger.info("Workflow completed: %s", result.get("run_summary", "Pipeline completed."))
    if result.get("digest_subject"):
        logger.info("Digest subject: %s", result["digest_subject"])


if __name__ == "__main__":
    main()
