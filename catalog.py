"""Source-backed musical catalogue. Only year categories, never film categories."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

BASE = Path(__file__).resolve().parent
USER_AGENT = "SpinningTop/2.0 (https://github.com/styayur; musical discovery)"
API = "https://en.wikipedia.org/w/api.php"
_local = threading.local()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def wiki_query(params, language="en"):
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = USER_AGENT
    url = f"https://{language}.wikipedia.org/w/api.php"
    for attempt in range(2):
        try:
            response = _local.session.get(url, params={
                "format": "json", "formatversion": 2, "maxlag": 5, **params,
            }, timeout=(5, 12))
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                raise ValueError(result["error"].get("info", "Wikipedia API error"))
            return result
        except (requests.RequestException, ValueError):
            if attempt:
                raise
            time.sleep(1)


def category_members(category, kind):
    continuation = {}
    while True:
        data = wiki_query({"action": "query", "list": "categorymembers",
                           "cmtitle": category, "cmtype": kind,
                           "cmlimit": 500, **continuation})
        if "categorymembers" not in data.get("query", {}):
            raise ValueError("Wikipedia returned no categorymembers")
        yield from data["query"]["categorymembers"]
        continuation = data.get("continue")
        if not continuation:
            break


def wiki_url(title, language="en"):
    return f"https://{language}.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="")


def discover(progress=lambda done, total: None):
    exclusions = read_json(BASE / 'data' / 'exclusions.json', {})
    categories = [row["title"] for row in category_members("Category:Musicals by year", "subcat")
                  if re.fullmatch(r"Category:\d{4} musicals", row["title"])]
    if not categories:
        raise ValueError("No musical year categories returned")
    entries = {}

    def year_members(category):
        year = int(category[9:13])
        return year, list(category_members(category, "page"))

    # Three connections at most; full continuation on every category.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(year_members, category) for category in categories]
        for done, future in enumerate(as_completed(futures), 1):
            year, members = future.result()
            for row in members:
                if row.get("ns") != 0 or row["title"].startswith("List of ") or row['title'] in exclusions:
                    continue
                identity = f"en:{row['pageid']}"
                if identity in entries:
                    entries[identity]["year"] = min(year, entries[identity]["year"])
                    continue
                title = row["title"]
                entries[identity] = {
                    "id": identity, "pageid": row["pageid"], "wiki": title,
                    "title": re.sub(r" \((?:\d{4} )?musical\)$", "", title),
                    "year": year, "wiki_url": wiki_url(title),
                }
            progress(done, len(categories))
    if len(entries) < 500:
        raise ValueError("Catalogue unexpectedly small; keeping previous catalogue")
    return {"updated_at": datetime.now(timezone.utc).isoformat(),
            "source": wiki_url("Category:Musicals by year"),
            "license": "Wikipedia metadata; article text CC BY-SA 4.0; images have individual licenses",
            "musicals": sorted(entries.values(), key=lambda item: item["wiki"].casefold())}


def load_catalog(runtime_dir):
    snapshot = read_json(Path(runtime_dir) / "catalog.json", {})
    if not isinstance(snapshot, dict) or not snapshot.get("musicals"):
        snapshot = read_json(BASE / "data" / "catalog.json", {})
    curated = read_json(BASE / "data" / "musicals.json", [])
    entries = snapshot.get("musicals", [])
    if not entries:
        entries = [{**item, "id": "wiki:" + item["wiki"], "wiki_url": wiki_url(item["wiki"])}
                   for item in curated]
    extras = {item["wiki"]: item for item in curated}
    merged = []
    exclusions = read_json(BASE / 'data' / 'exclusions.json', {})
    for item in entries:
        if item['wiki'] in exclusions:
            continue
        # The harvested year remains authoritative; annotations add Chinese names/sites.
        extra = extras.get(item["wiki"], {})
        merged.append({**extra, **item, **{key: extra[key] for key in
                       ("title_zh", "composer", "official_url", "fever_query") if key in extra}})
    return merged, snapshot.get("updated_at")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch the complete musical year catalogue")
    parser.add_argument("--output", type=Path, default=BASE / "data" / "catalog.json")
    args = parser.parse_args()
    result = discover(lambda done, total: print(f"Categories {done}/{total}", flush=True))
    write_json(args.output, result)
    print(f"Saved {len(result['musicals'])} musicals to {args.output}")
