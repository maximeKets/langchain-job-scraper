from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.models import SearchIntent
from src.pipeline.sources import parse_greenhouse_jobs, parse_lever_jobs, parse_wttj_hits


def build_search_intent(source: str, title: str) -> SearchIntent:
    return SearchIntent(
        source=source,
        title=title,
        query=f"{title} Python SQL",
        locations=["Paris", "Remote France"],
        remote_policy="flexible",
        contract_types=["full_time"],
        required_keywords=["python", "sql"],
        bonus_keywords=["langchain"],
        excluded_keywords=["internship"],
    )


def test_parse_wttj_hits_fixture() -> None:
    payload = json.loads(Path("tests/fixtures/wttj_algolia.json").read_text(encoding="utf-8"))
    hits = payload["results"][0]["hits"]
    offers = parse_wttj_hits(hits, "fr", build_search_intent("wttj", "Data Engineer"))

    assert len(offers) == 1
    assert offers[0].company == "Example WTTJ Company"
    assert offers[0].canonical_url.endswith("/jobs/senior-data-engineer_paris")


def test_parse_greenhouse_jobs_fixture() -> None:
    payload = json.loads(
        Path("tests/fixtures/greenhouse_jobs.json").read_text(encoding="utf-8")
    )
    offers = parse_greenhouse_jobs(
        "stripe",
        payload["jobs"],
        [build_search_intent("greenhouse", "Machine Learning Engineer")],
    )

    assert len(offers) == 1
    assert offers[0].employment_type == "full_time"
    assert offers[0].canonical_url == "https://boards.greenhouse.io/example/jobs/101"


def test_parse_lever_jobs_fixture() -> None:
    payload = json.loads(Path("tests/fixtures/lever_jobs.json").read_text(encoding="utf-8"))
    offers = parse_lever_jobs(
        "dnb",
        payload,
        [build_search_intent("lever", "AI Engineer")],
    )

    assert len(offers) == 1
    assert offers[0].remote_policy == "remote"
    assert offers[0].canonical_url == "https://jobs.lever.co/example/lever-202"
