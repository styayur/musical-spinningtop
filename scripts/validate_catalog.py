#!/usr/bin/env python3
"""Validate bundled catalogue and article snapshots without network access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name: str) -> dict:
    path = DATA / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"{name}: unable to read valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{name}: root must be an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    catalog = load("catalog.json")
    articles = load("articles.json")
    musicals = catalog.get("musicals")
    article_rows = articles.get("articles")

    require(isinstance(musicals, list), "catalog.json: musicals must be an array")
    require(len(musicals) >= 2_000, f"catalog.json: expected at least 2000 rows, got {len(musicals)}")
    require(isinstance(article_rows, dict), "articles.json: articles must be an object keyed by catalogue id")
    require(len(article_rows) >= 2_000, f"articles.json: expected at least 2000 entries, got {len(article_rows)}")

    ids: set[str] = set()
    page_ids: set[int] = set()
    titles: set[str] = set()
    required = {"id", "pageid", "wiki", "title", "year", "wiki_url"}
    for index, row in enumerate(musicals):
        require(isinstance(row, dict), f"catalog.json: row {index} is not an object")
        missing = required.difference(row)
        require(not missing, f"catalog.json: row {index} missing {sorted(missing)}")
        identity = row["id"]
        require(isinstance(identity, str) and identity.startswith("en:"), f"catalog.json: invalid id at row {index}")
        require(identity not in ids, f"catalog.json: duplicate id {identity}")
        ids.add(identity)
        page_id = row["pageid"]
        require(isinstance(page_id, int), f"catalog.json: invalid pageid for {identity}")
        require(page_id not in page_ids, f"catalog.json: duplicate pageid {page_id}")
        page_ids.add(page_id)
        title = row["wiki"]
        require(isinstance(title, str) and title.strip(), f"catalog.json: empty title for {identity}")
        require(title.casefold() not in titles, f"catalog.json: duplicate wiki title {title}")
        titles.add(title.casefold())
        require(isinstance(row["year"], int) and 1800 <= row["year"] <= 2100, f"catalog.json: invalid year for {identity}")
        require(str(row["wiki_url"]).startswith("https://en.wikipedia.org/wiki/"), f"catalog.json: invalid wiki_url for {identity}")

    missing_articles = ids.difference(article_rows)
    orphan_articles = set(article_rows).difference(ids)
    require(not missing_articles, f"articles.json: missing {len(missing_articles)} catalogue ids")
    require(len(orphan_articles) <= max(50, len(article_rows) // 20), f"articles.json: too many ids are absent from the catalogue ({len(orphan_articles)})")

    for identity, row in article_rows.items():
        require(isinstance(row, dict), f"articles.json: {identity} is not an object")
        require(isinstance(row.get("intro_en"), str), f"articles.json: {identity} has no intro_en")
        source = row.get("intro_source")
        require(isinstance(source, str) and source.startswith("https://en.wikipedia.org/wiki/"), f"articles.json: invalid intro_source for {identity}")

    print(
        f"Validated {len(musicals)} catalogue rows and {len(article_rows)} source-backed article summaries "
        f"(catalog {catalog.get('updated_at')}, articles {articles.get('updated_at')}; "
        f"{len(orphan_articles)} historical article summaries retained)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


