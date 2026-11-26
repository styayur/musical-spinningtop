"""Repeatable artwork evidence measured from emitted SVGs, not recipe parameters."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from artwork.generate import plan_artwork
from artwork.normalize import merge_publication
from catalog import BASE, read_json

SEED = "spinningtop-artwork-sample-2026-11-25"
INDEPENDENT_SEED = "spinningtop-artwork-independent-2026-11-26"
OUT = BASE / "docs" / "artwork-review"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
NUMERIC = {"x", "y", "width", "height", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "d", "points", "viewBox", "stroke-width", "stroke-dasharray", "stroke-dashoffset", "opacity", "fill-opacity", "stroke-opacity"}
METRIC_VERSION = "emitted-svg-v1-occlusion-barriers"
METRIC_NOTES = {
    "actual_svg_exact": "SHA-256 of emitted UTF-8 SVG bytes, including palette and serialization order; never a recipe hash.",
    "decolored_svg_ordered": "Emitted SVG parsed and normalized: painted fills become white, painted strokes one dark ink; none, wash shapes, width, opacity, and paint order retained. Attribute order, whitespace and numeric spelling normalized.",
    "canonical_geometry": "Same decolored emitted primitives, sorted only within contiguous opaque stroke-only runs. Filled shapes (including white washes) and other order-sensitive primitives remain ordered barriers. Primitive multiplicity retained; recipe parameters are not geometry.",
    "max_duplicate_ratio": "Largest equivalence class / population size. Also reports duplicate excess / population; these are distinct measures.",
    "limitations": "Not perceptual similarity or semantic correctness. Equivalent path commands, reversed lines, and mirrored geometry are not collapsed. Raster antialiasing may differ. Unsupported SVG constructs fail explicitly.",
}


def sha256(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def write_text(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git_bytes(*args):
    return subprocess.run(["git", *args], cwd=BASE, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def preserve_baseline():
    """Preserve git blobs without passing PNG bytes through shell text redirection."""
    folder = OUT / "baseline"
    manifest_path = folder / "provenance.json"
    if manifest_path.exists():
        provenance = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in provenance["files"].items():
            if sha256((folder / name).read_bytes()) != expected:
                raise RuntimeError(f"Preserved baseline changed: {name}")
        return provenance
    revision = git_bytes("rev-parse", "HEAD").decode().strip()
    names = git_bytes("ls-tree", "-r", "--name-only", revision, "docs/artwork-review").decode().splitlines()
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in names:
        relative = Path(name).relative_to("docs/artwork-review")
        if len(relative.parts) != 1 or relative.suffix not in {".svg", ".png", ".json"}:
            continue
        data = git_bytes("show", f"{revision}:{name}")
        target = folder / relative
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"Refusing to replace baseline evidence: {target}")
        target.write_bytes(data)
        files[relative.as_posix()] = sha256(data)
    if "sample-ids.json" not in files:
        raise RuntimeError("HEAD has no sample-ids.json; cannot silently select a new comparison sample")
    provenance = {"commit": revision, "method": "git show <commit>:<path> via subprocess bytes + Path.write_bytes; original PNG/SVG/JSON only", "files": files}
    write_json(manifest_path, provenance)
    return provenance


def _number(match):
    number = Decimal(match.group())
    return "0" if not number else format(number.normalize(), "f")


def _normalized_value(name, value):
    if name in NUMERIC:
        value = NUMBER.sub(_number, value)
        return " ".join(re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)", value))
    return " ".join(value.split())


def decolored_tree(svg):
    root = ET.fromstring(svg)
    allowed = {"svg", "rect", "line", "circle", "ellipse", "path", "polyline", "polygon"}
    allowed_attrs = NUMERIC | {"fill", "stroke", "stroke-linecap", "stroke-linejoin", "fill-rule", "stroke-miterlimit"}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in allowed or (element is not root and len(element)):
            raise ValueError(f"Unsupported SVG structure in geometry review: {tag}")
        if element is not root and tag == "svg":
            raise ValueError("Nested SVG is not supported by the primitive metric")
        attributes = {}
        for name, value in element.attrib.items():
            if name not in allowed_attrs:
                raise ValueError(f"Unsupported SVG attribute in geometry review: {name}")
            if name in {"fill", "stroke"} and value.lower() != "none":
                value = "#ffffff" if name == "fill" else "#243044"
            attributes[name] = _normalized_value(name, value)
        element.attrib.clear()
        element.attrib.update(sorted(attributes.items()))
        element.text = None
        element.tail = None
    return root


def decolored_svg(svg):
    return ET.tostring(decolored_tree(svg), encoding="unicode")


def canonical_geometry(svg):
    """Sort monochrome line work, never across an occluding filled primitive."""
    root = decolored_tree(svg)
    inherited = {key: value for key, value in root.attrib.items() if key not in {"viewBox", "width", "height"}}
    blocks, run = [], []

    def flush():
        if run:
            blocks.append(["opaque-strokes", sorted(run)])
            run.clear()

    for element in root:
        attrs = {**inherited, **element.attrib}
        primitive = json.dumps([element.tag.rsplit("}", 1)[-1], sorted(attrs.items())], separators=(",", ":"))
        opaque_stroke_only = attrs.get("fill", "#ffffff") == "none" and all(attrs.get(key, "1") == "1" for key in ("opacity", "stroke-opacity", "fill-opacity"))
        if opaque_stroke_only:
            run.append(primitive)
        else:
            flush()
            blocks.append(["ordered-paint", primitive])
    flush()
    return json.dumps([sorted(root.attrib.items()), blocks], separators=(",", ":"))


def drawing_digests(planned):
    svg = planned["svg"]
    return {"actual_svg_exact": sha256(svg), "decolored_svg_ordered": sha256(decolored_svg(svg)), "canonical_geometry": sha256(canonical_geometry(svg))}


def distribution(items, digests, metric):
    groups = defaultdict(list)
    for item, digest in zip(items, digests):
        groups[digest[metric]].append(item["id"])
    ordered = sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    total = len(items)
    largest = len(ordered[0][1]) if ordered else 0
    return {
        "total": total, "unique": len(groups), "largest_duplicate_count": largest,
        "max_duplicate_ratio": round(largest / total, 8) if total else 0,
        "duplicate_excess_ratio": round((total - len(groups)) / total, 8) if total else 0,
        "largest_groups": [{"sha256": digest, "count": len(ids), "example_ids": ids[:8]} for digest, ids in ordered[:5]],
    }


def measure(plans):
    digests = [drawing_digests(item) for item in plans]
    abstract = [(item, digest) for item, digest in zip(plans, digests) if item["kind"] == "abstract"]
    templates = defaultdict(list)
    for item, digest in abstract:
        templates[str(item.get("recipe", {}).get("abstract_layout", "unspecified"))].append((item, digest))
    sizes = sorted(len(item["svg"].encode("utf-8")) for item in plans)
    signatures = Counter((item["family"], tuple(item["subjects"]), item["count"], item.get("recipe", {}).get("arrangement", "")) for item in plans)
    kinds = Counter(item["kind"] for item in plans)
    reasons = Counter(str(item["reason"]) for item in plans)
    for reason in ("error", "insufficient", "empty"):
        reasons.setdefault(reason, 0)
    parameter_fields = ("family", "subjects", "arrangement", "count", "modifiers", "palette", "mirror", "detail", "abstract_layout")
    parameter_keys = [json.dumps({key: item.get("recipe", {}).get(key) for key in parameter_fields}, sort_keys=True, separators=(",", ":")) for item in plans]
    stats = {
        "metric_version": METRIC_VERSION, "metric_definitions": METRIC_NOTES,
        "total": len(plans), "generated": kinds.get("generated", 0), "abstract": kinds.get("abstract", 0),
        "fallback": kinds.get("fallback", 0), "failed": sum(item["reason"] == "error" for item in plans),
        "reasons": dict(reasons), "families": dict(Counter(item["family"] for item in plans)),
        "unique_structural_signatures": len(signatures),
        "unique_parameter_combinations": len(set(parameter_keys)),
        "abstract_parameter_combinations": len({key for key, item in zip(parameter_keys, plans) if item["kind"] == "abstract"}),
        "parameter_fields": list(parameter_fields),
        "parameter_note": "Recipe metadata combinations, including possibly unused modifiers/detail/mirror. These counts are not emitted drawing diversity.",
        "signature_note": "Legacy family/subjects/count/arrangement metadata only; NOT drawing or geometry diversity.",
        "drawings": {metric: distribution(plans, digests, metric) for metric in digests[0]},
        "abstract_drawings": {metric: distribution([item for item, _ in abstract], [digest for _, digest in abstract], metric) for metric in digests[0]},
        "abstract_templates": {key: {
            "count": len(group), "ratio_of_abstract": round(len(group) / len(abstract), 8),
            "unique_actual_svg": len({digest["actual_svg_exact"] for _, digest in group}),
            "unique_canonical_geometry": len({digest["canonical_geometry"] for _, digest in group}),
        } for key, group in sorted(templates.items())},
        "abstract_template_note": "Selected recipe template distribution; actual emitted diversity measured separately. Historical recipes without a template field are unspecified.",
        "bytes": {"min": sizes[0], "p50": sizes[len(sizes) // 2], "p90": sizes[int(len(sizes) * .9)], "max": sizes[-1], "total": sum(sizes)},
    }
    return stats, digests


def measure_baseline(revision):
    """Execute original HEAD generator in an isolated directory, with no cache writes."""
    runner = """
import json, sys
from artwork.generate import plan_artwork
from artwork.normalize import merge_publication
catalog, articles, summaries = json.load(sys.stdin)
rows = [merge_publication(row, articles.get(row['id']), summaries.get(row['title'], '')) for row in catalog['musicals']]
json.dump([plan_artwork(row) for row in rows], sys.stdout, ensure_ascii=True)
"""
    source_paths = git_bytes("ls-tree", "-r", "--name-only", revision, "artwork").decode().splitlines()
    data_paths = ["data/catalog.json", "data/articles.json", "data/summaries_zh.json"]
    data_bytes = [git_bytes("show", f"{revision}:{path}") for path in data_paths]
    catalog, articles, summaries = [json.loads(data) for data in data_bytes]
    sources = {}
    with tempfile.TemporaryDirectory(prefix="spinningtop-artwork-baseline-") as directory:
        for path in source_paths:
            if path.endswith(".py"):
                data = git_bytes("show", f"{revision}:{path}")
                target = Path(directory) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                sources[path] = sha256(data)
        completed = subprocess.run([sys.executable, "-c", runner], cwd=directory,
            input=json.dumps([catalog, articles.get("articles", {}), summaries]).encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        plans = json.loads(completed.stdout)
    stats, _ = measure(plans)
    stats.update({"commit": revision,
        "method": "Original git-show artwork Python and committed data executed in an isolated temporary directory; measured with this script. Original stats.json remains unchanged.",
        "source_sha256": sources, "data_sha256": {name: sha256(data) for name, data in zip(data_paths, data_bytes)}})
    return stats


def independent_samples(rows, original_ids, count=36):
    excluded = set(original_ids)
    pool = [row for row in rows if row["id"] not in excluded]
    return sorted(pool, key=lambda row: (sha256(f"{INDEPENDENT_SEED}|{row['id']}"), row["id"]))[:count]


def sheet(plans, structure=False):
    cols, cell_w, cell_h, gap = 6, 180, 240, 16
    width = cols * cell_w + (cols + 1) * gap
    rows = (len(plans) + cols - 1) // cols
    height = rows * cell_h + (rows + 1) * gap
    parts = [f'<svg xmlns="{SVG_NS}" viewBox="0 0 {width} {height}" width="{width}" height="{height}">', f'<rect width="{width}" height="{height}" fill="#ffffff"/>']
    for index, planned in enumerate(plans):
        svg = decolored_svg(planned["svg"]) if structure else planned["svg"]
        root = ET.fromstring(svg)
        attrs = {key: value for key, value in root.attrib.items() if key not in {"width", "height", "viewBox"}}
        cell = ET.Element(f"{{{SVG_NS}}}svg", {**attrs, "x": str(gap + index % cols * (cell_w + gap)),
            "y": str(gap + index // cols * (cell_h + gap)), "width": str(cell_w), "height": str(cell_h),
            "viewBox": root.attrib.get("viewBox", "0 0 360 480")})
        cell.extend(list(root))
        parts.append(ET.tostring(cell, encoding="unicode"))
    parts.append("</svg>\n")
    return "\n".join(parts)


def render_png(svg_path, png_path):
    from playwright.sync_api import sync_playwright
    html = "<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:#fff}</style>" + svg_path.read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1800}, device_scale_factor=1)
        page.set_content(html)
        page.locator("svg").first.screenshot(path=str(png_path))
        browser.close()
    return True


def _cjk(value):
    return any("\u4e00" <= char <= "\u9fff" for char in (value or ""))


def write_sample(folder, samples, plans_by_id, digest_by_id, seed, original=False, selection_rule=None):
    folder.mkdir(parents=True, exist_ok=True)
    trace = []
    for index, row in enumerate(samples):
        planned = plans_by_id[row["id"]]
        synopsis = (row.get("intro_zh") or row.get("intro_en") or "").strip()
        trace.append({
            "position": index + 1, "sheet_row": index // 6 + 1, "sheet_column": index % 6 + 1,
            "id": row["id"], "title": row.get("title"), "title_zh": row.get("title_zh") or "", "year": row.get("year"),
            "has_remote_image": bool(row.get("image")), "has_chinese": _cjk((row.get("title_zh") or "") + (row.get("intro_zh") or "")),
            "text_length": len(synopsis), "family": planned["family"], "kind": planned["kind"], "reason": planned["reason"],
            "subjects": planned["subjects"], "count": planned["count"], "basis": planned["basis"],
            "abstract_template": planned.get("recipe", {}).get("abstract_layout") if planned["kind"] == "abstract" else None,
            "source_digest": planned["source_digest"], "selection_seed": seed, "selection_sha256": sha256(f"{seed}|{row['id']}"),
            "selection_rule": selection_rule or ("Original HEAD ID and position preserved" if original else "Ascending SHA-256(seed|id), original sample excluded; no outcome-based replacement"),
            **digest_by_id[row["id"]],
        })
    if original:
        (folder / "sample-ids.json").write_bytes((OUT / "baseline" / "sample-ids.json").read_bytes())
    else:
        write_json(folder / "sample-ids.json", [row["id"] for row in samples])
    write_json(folder / "sample-trace.json", trace)
    selected = [plans_by_id[row["id"]] for row in samples]
    pngs = {}
    for name, structure in (("contact", False), ("structure", True)):
        svg_path, png_path = folder / f"{name}-sheet.svg", folder / f"{name}-sheet.png"
        write_text(svg_path, sheet(selected, structure))
        pngs[name] = render_png(svg_path, png_path)
    return {"count": len(samples), "families": dict(Counter(item["family"] for item in trace)),
        "chinese": sum(item["has_chinese"] for item in trace), "remote_image": sum(item["has_remote_image"] for item in trace),
        "empty": sum(item["text_length"] == 0 for item in trace), "png": pngs}


def input_hashes():
    paths = sorted((BASE / "artwork").glob("*.py")) + [BASE / "data" / name for name in ("catalog.json", "articles.json", "summaries_zh.json")]
    return {path.relative_to(BASE).as_posix(): sha256(path.read_bytes()) for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preserve-baseline-only", action="store_true", help="Preserve original HEAD artifacts and recompute baseline metrics without after images")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = preserve_baseline()
    write_json(OUT / "baseline" / "metrics.json", measure_baseline(baseline["commit"]))
    if args.preserve_baseline_only:
        return
    inputs_before = input_hashes()
    catalog = read_json(BASE / "data" / "catalog.json", {})
    articles = read_json(BASE / "data" / "articles.json", {}).get("articles", {})
    summaries = read_json(BASE / "data" / "summaries_zh.json", {})
    rows = [merge_publication(row, articles.get(row["id"]), summaries.get(row["title"], "")) for row in catalog["musicals"]]
    rows_by_id = {row["id"]: row for row in rows}
    if len(rows_by_id) != len(rows):
        raise RuntimeError("Duplicate catalogue IDs")
    original_ids = json.loads((OUT / "baseline" / "sample-ids.json").read_bytes())
    if len(set(original_ids)) != len(original_ids):
        raise RuntimeError("Duplicate original sample IDs")
    samples = [rows_by_id[identity] for identity in original_ids]
    independent = independent_samples(rows, original_ids)
    pre_fix = OUT / "pre-fix-v3"
    regression_note = None
    if (pre_fix / "independent" / "sample-ids.json").exists():
        archived = json.loads((pre_fix / "provenance.json").read_text(encoding="utf-8"))
        for name, expected in archived["files"].items():
            if sha256((pre_fix / name).read_bytes()) != expected:
                raise RuntimeError(f"Preserved pre-fix v3 evidence changed: {name}")
        previous_ids = json.loads((pre_fix / "independent" / "sample-ids.json").read_bytes())
        if [row["id"] for row in independent] != previous_ids:
            raise RuntimeError("Independent sample changed from the observed v3 sample; preserve IDs and order")
        regression_note = "Originally independent seeded sample; its three observed v3 creator/song-title/production-place failures drove generic v4 fixes. Reused unchanged as regression evidence, no longer blind or held-out accuracy evidence."
    started = time.perf_counter()
    plans = [plan_artwork(row) for row in rows]
    elapsed = time.perf_counter() - started
    stats, digests = measure(plans)
    if input_hashes() != inputs_before:
        raise RuntimeError("Artwork code or data changed during review; rerun after agents finish")
    plans_by_id = {item["id"]: item for item in plans}
    digest_by_id = {item["id"]: digest for item, digest in zip(plans, digests)}
    template_seed = "spinningtop-artwork-all-templates-2026-11-26"
    template_samples = []
    for template in range(8):
        candidates = [item for item in plans if item["kind"] == "abstract" and item.get("recipe", {}).get("abstract_layout") == template]
        if not candidates:
            raise RuntimeError(f"No emitted abstract sample for template {template}")
        selected = min(candidates, key=lambda item: (sha256(f"{template_seed}|{item['id']}"), item["id"]))
        template_samples.append(rows_by_id[selected["id"]])
    stats.update({
        "seed": SEED, "sample_rule": "Original HEAD sample-ids.json preserved byte-for-byte, same IDs and positions; no family replacement",
        "baseline_commit": baseline["commit"], "catalog_updated_at": catalog.get("updated_at"),
        "source_sha256": inputs_before, "review_script_sha256": sha256(Path(__file__).read_bytes()),
        "art_versions": sorted({item["art_version"] for item in plans}), "extractor_versions": sorted({item["extractor_version"] for item in plans}),
        "elapsed_seconds": round(elapsed, 2), "per_item_ms": round(elapsed / len(plans) * 1000, 2),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "sample": write_sample(OUT, samples, plans_by_id, digest_by_id, SEED, original=True),
        "independent_sample": write_sample(OUT / "independent", independent, plans_by_id, digest_by_id, INDEPENDENT_SEED,
            selection_rule=regression_note),
        "independent_sample_evidence_status": regression_note or "Independent seeded catalogue sample; not a semantic accuracy benchmark",
        "all_templates_sample": write_sample(OUT / "abstract-templates", template_samples, plans_by_id, digest_by_id, template_seed,
            selection_rule="One actual catalogue abstract per template 0..7 in template order; smallest SHA-256(seed|id) within each template; coverage illustration, not an independent sample"),
    })
    write_json(OUT / "independent" / "sampling.json", {
        "seed": INDEPENDENT_SEED, "rule": "First 36 ascending (SHA-256(seed|id), id) among catalogue rows excluding original HEAD sample; no strata or semantic replacement",
        "eligible_count": len(rows) - len(original_ids), "excluded_ids": original_ids,
        "catalog_sha256": inputs_before["data/catalog.json"], "sample_overlap": len(set(original_ids) & {row["id"] for row in independent}),
        "sample": stats["independent_sample"],
        "evidence_status": stats["independent_sample_evidence_status"],
    })
    if regression_note:
        before = json.loads((pre_fix / "independent" / "sample-trace.json").read_text(encoding="utf-8"))
        after = json.loads((OUT / "independent" / "sample-trace.json").read_text(encoding="utf-8"))
        if [item["id"] for item in before] != [item["id"] for item in after]:
            raise RuntimeError("Regression trace changed original independent sample order")
        fields = ("family", "kind", "reason", "subjects", "count", "basis", "source_digest", "actual_svg_exact", "canonical_geometry")
        write_json(OUT / "independent" / "v3-comparison.json", {
            "evidence_status": regression_note,
            "before": "../pre-fix-v3/independent/sample-trace.json", "after": "sample-trace.json",
            "same_ids_and_order": True,
            "items": [{"position": old["position"], "id": old["id"], "title": old["title"],
                "before": {key: old[key] for key in fields}, "after": {key: new[key] for key in fields}}
                for old, new in zip(before, after)],
        })
    if input_hashes() != inputs_before:
        raise RuntimeError("Artwork code or data changed during PNG rendering; pack incomplete, must rerun")
    write_json(OUT / "stats.json", stats)


if __name__ == "__main__":
    main()
