"""Repeatable artwork review pack. Not part of the page runtime."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artwork.draw import render_svg
from artwork.generate import plan_artwork
from artwork.normalize import merge_publication
from catalog import BASE, read_json

SEED = "spinningtop-artwork-sample-2026-11-25"
OUT = BASE / "docs" / "artwork-review"
FAMILIES = ("relation", "city", "stage", "route", "terrain", "portal", "still")


def sample_key(row):
    return hashlib.sha256(f"{SEED}|{row['id']}".encode("utf-8")).hexdigest()


def _cjk(value):
    return any("\u4e00" <= char <= "\u9fff" for char in (value or ""))


def select_samples(rows, family_of):
    used = set()
    chosen = []

    def text_of(row):
        return (row.get("intro_zh") or row.get("intro_en") or "").strip()

    def chinese(row):
        return _cjk(row.get("title_zh")) or _cjk(row.get("intro_zh")) or _cjk(text_of(row))

    def take(pred, count):
        pool = [row for row in rows if row["id"] not in used and pred(row)]
        pool.sort(key=sample_key)
        for row in pool[:count]:
            chosen.append(row)
            used.add(row["id"])

    take(lambda row: not text_of(row), 3)
    take(lambda row: bool(row.get("image")), 4)
    take(lambda row: not row.get("image"), 4)
    take(lambda row: 0 < len(text_of(row)) <= 180, 3)
    take(lambda row: len(text_of(row)) > 1000, 3)
    take(lambda row: isinstance(row.get("year"), int) and row["year"] < 1950, 3)
    take(lambda row: isinstance(row.get("year"), int) and 1950 <= row["year"] <= 1979, 3)
    take(lambda row: isinstance(row.get("year"), int) and 1980 <= row["year"] <= 1999, 3)
    take(lambda row: isinstance(row.get("year"), int) and 2000 <= row["year"] <= 2014, 3)
    take(lambda row: isinstance(row.get("year"), int) and row["year"] >= 2015, 3)
    take(chinese, 3)
    rest = [row for row in rows if row["id"] not in used]
    rest.sort(key=sample_key)
    for row in rest:
        if len(chosen) >= 36:
            break
        chosen.append(row)
    chosen = chosen[:36]
    protected = set()

    def protect(pred):
        for row in chosen:
            if row["id"] not in protected and pred(row):
                protected.add(row["id"])
                return

    protect(lambda row: not text_of(row))
    protect(lambda row: bool(row.get("image")))
    protect(lambda row: not row.get("image") and bool(text_of(row)))
    protect(lambda row: 0 < len(text_of(row)) <= 180)
    protect(lambda row: len(text_of(row)) > 1000)
    protect(chinese)
    protect(lambda row: isinstance(row.get("year"), int) and row["year"] < 1950)
    protect(lambda row: isinstance(row.get("year"), int) and 1950 <= row["year"] <= 1979)
    protect(lambda row: isinstance(row.get("year"), int) and 1980 <= row["year"] <= 1999)
    protect(lambda row: isinstance(row.get("year"), int) and 2000 <= row["year"] <= 2014)
    protect(lambda row: isinstance(row.get("year"), int) and row["year"] >= 2015)
    present = {family_of(row["id"]) for row in chosen}
    occupied = {row["id"] for row in chosen}
    for family in FAMILIES:
        if family in present:
            continue
        pool = [row for row in rows if family_of(row["id"]) == family and row["id"] not in occupied]
        pool.sort(key=sample_key)
        if not pool:
            continue
        for index in range(len(chosen) - 1, -1, -1):
            current = chosen[index]
            if current["id"] in protected or family_of(current["id"]) != "abstract":
                continue
            occupied.discard(current["id"])
            chosen[index] = pool[0]
            occupied.add(pool[0]["id"])
            present.add(family)
            break
    return chosen


def sheet(plans, structure=False):
    cols, cell_w, cell_h, gap = 6, 180, 240, 16
    width = cols * cell_w + (cols + 1) * gap
    rows = (len(plans) + cols - 1) // cols
    height = rows * cell_h + (rows + 1) * gap
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    for index, planned in enumerate(plans):
        svg = render_svg(planned["recipe"], structure=structure)
        inner = svg[svg.index(">") + 1:svg.rindex("</svg>")]
        x = gap + (index % cols) * (cell_w + gap)
        y = gap + (index // cols) * (cell_h + gap)
        parts.append(f'<svg x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" viewBox="0 0 360 480">{inner}</svg>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def render_png(svg_path, png_path):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    markup = svg_path.read_text(encoding="utf-8")
    html = "<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:#fff}</style>" + markup
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1800}, device_scale_factor=1)
        page.set_content(html)
        page.locator("svg").first.screenshot(path=str(png_path))
        browser.close()
    return True


def main():
    catalog = read_json(BASE / "data" / "catalog.json", {})
    articles = read_json(BASE / "data" / "articles.json", {}).get("articles", {})
    summaries = read_json(BASE / "data" / "summaries_zh.json", {})
    rows = [merge_publication(row, articles.get(row["id"]), summaries.get(row["title"], "")) for row in catalog["musicals"]]
    started = time.perf_counter()
    plans = [plan_artwork(row) for row in rows]
    elapsed = time.perf_counter() - started
    family_of = {item["id"]: item["family"] for item in plans}
    families = Counter(item["family"] for item in plans)
    kinds = Counter(item["kind"] for item in plans)
    reasons = Counter(item["reason"] for item in plans)
    sizes = sorted(len(item["svg"].encode("utf-8")) for item in plans)
    signatures = Counter((item["family"], tuple(item["subjects"]), item["count"], item["recipe"]["arrangement"]) for item in plans)
    samples = select_samples(rows, family_of.get)
    sample_plans = []
    trace = []
    for row in samples:
        planned = next(item for item in plans if item["id"] == row["id"])
        sample_plans.append(planned)
        text = (row.get("intro_zh") or row.get("intro_en") or "").strip()
        trace.append({
            "id": row["id"],
            "title": row.get("title"),
            "title_zh": row.get("title_zh") or "",
            "year": row.get("year"),
            "has_remote_image": bool(row.get("image")),
            "has_chinese": _cjk((row.get("title_zh") or "") + (row.get("intro_zh") or "")),
            "text_length": len(text),
            "family": planned["family"],
            "kind": planned["kind"],
            "reason": planned["reason"],
            "subjects": planned["subjects"],
            "count": planned["count"],
            "basis": planned["basis"],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "contact-sheet.svg").write_text(sheet(sample_plans), encoding="utf-8", newline="\n")
    (OUT / "structure-sheet.svg").write_text(sheet(sample_plans, structure=True), encoding="utf-8", newline="\n")
    (OUT / "sample-ids.json").write_text(json.dumps([row["id"] for row in samples], indent=2) + "\n", encoding="utf-8", newline="\n")
    (OUT / "sample-trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    stats = {
        "seed": SEED,
        "sample_rule": "Fixed SHA-256 strata for empty text, remote image, length, year, and Chinese text, then abstract fillers replaced until each generated family is represented.",
        "catalog_updated_at": catalog.get("updated_at"),
        "total": len(plans),
        "generated": kinds.get("generated", 0),
        "abstract": kinds.get("abstract", 0),
        "fallback": kinds.get("fallback", 0),
        "failed": 0,
        "reasons": {str(key): value for key, value in reasons.items()},
        "families": dict(families),
        "unique_structural_signatures": len(signatures),
        "largest_signature": {
            "count": signatures.most_common(1)[0][1],
            "family": signatures.most_common(1)[0][0][0],
            "subjects": list(signatures.most_common(1)[0][0][1]),
        },
        "sample_families": dict(Counter(item["family"] for item in trace)),
        "sample_chinese": sum(1 for item in trace if item["has_chinese"]),
        "sample_remote_image": sum(1 for item in trace if item["has_remote_image"]),
        "sample_empty": sum(1 for item in trace if item["text_length"] == 0),
        "bytes": {
            "min": sizes[0],
            "p50": sizes[len(sizes) // 2],
            "p90": sizes[int(len(sizes) * 0.9)],
            "max": sizes[-1],
            "total": sum(sizes),
        },
        "elapsed_seconds": round(elapsed, 2),
        "per_item_ms": round(elapsed / len(plans) * 1000, 2),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "budget_note": "Initial 5-25KB target was revised: these line plates are about 0.7-3KB. Padding to 5KB would add noise. The 60KB cap is enforced.",
    }
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    stats["png"] = {
        "contact": render_png(OUT / "contact-sheet.svg", OUT / "contact-sheet.png"),
        "structure": render_png(OUT / "structure-sheet.svg", OUT / "structure-sheet.png"),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
