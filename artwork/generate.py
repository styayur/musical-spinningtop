"""Cache, manifest, and publication records for generated artwork."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from artwork.compose import compose
from artwork.draw import render_base, render_svg
from artwork.extract import extract_imagery
from artwork.lexicon import LABELS
from artwork.normalize import normalize_entry
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION

SAFE_NAME = re.compile(r"^(?:[a-f0-9]{20}|base)\.svg$")
MAX_BYTES = 60 * 1024
MAX_NODES = 220
_NODE = re.compile(r"<(?:rect|line|circle|path|polyline|polygon|g|svg)\b")


def safe_filename(identity):
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20] + ".svg"


def _atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _load_manifest(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"art_version": ART_VERSION, "extractor_version": EXTRACTOR_VERSION, "items": {}}
    if not isinstance(value, dict) or not isinstance(value.get("items"), dict):
        return {"art_version": ART_VERSION, "extractor_version": EXTRACTOR_VERSION, "items": {}}
    return value


def _basis(hits):
    rows = []
    seen = set()
    for hit in hits:
        if hit["source_field"] not in {"intro_en", "intro_zh"}:
            continue
        if hit["motif"] in seen or hit["score"] < 0.8:
            continue
        seen.add(hit["motif"])
        rows.append({
            "motif": hit["motif"],
            "label": hit["label"],
            "phrase": hit["phrase"],
            "source_field": hit["source_field"],
            "rule_id": hit["rule_id"],
            "score": hit["score"],
        })
        if len(rows) == 4:
            break
    return rows


def _public(record, url_prefix):
    name = record["filename"]
    prefix = url_prefix if url_prefix.endswith("/") else url_prefix + "/"
    version = record.get("source_digest", "0")[:8]
    return {
        "artwork_url": f"{prefix}{name}?v={record['art_version']}-{version}",
        "artwork_kind": record["kind"],
        "artwork_family": record["family"],
        "artwork_basis": record["basis"],
        "artwork_reason": record["reason"],
        "artwork_file": name,
        "source_digest": record["source_digest"],
        "art_version": record["art_version"],
        "extractor_version": record["extractor_version"],
        "recipe_digest": record["recipe_digest"],
    }


def plan_artwork(entry, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    normalized = normalize_entry(entry)
    identity = normalized["id"]
    if not identity or len(identity) > 200 or any(char in identity for char in "/\\"):
        svg = render_base()
        return {
            "id": identity,
            "filename": "base.svg",
            "svg": svg,
            "kind": "fallback",
            "family": "abstract",
            "reason": "no-id",
            "basis": [],
            "hits": [],
            "source_digest": normalized["source_digest"],
            "recipe_digest": "",
            "art_version": art_version,
            "extractor_version": extractor_version,
            "count": 0,
            "subjects": [],
        }
    extraction = extract_imagery(normalized)
    recipe = compose(normalized, extraction, art_version, extractor_version)
    svg = render_svg(recipe)
    nodes = len(_NODE.findall(svg))
    if len(svg.encode("utf-8")) > MAX_BYTES or nodes > MAX_NODES:
        svg = render_base()
        recipe = {**recipe, "family": "abstract", "kind": "abstract", "reason": "budget"}
    return {
        "id": identity,
        "filename": safe_filename(identity),
        "svg": svg,
        "kind": recipe["kind"],
        "family": recipe["family"],
        "reason": recipe["reason"],
        "basis": _basis(extraction["hits"]),
        "hits": extraction["hits"],
        "source_digest": normalized["source_digest"],
        "recipe_digest": recipe["recipe_digest"],
        "art_version": art_version,
        "extractor_version": extractor_version,
        "count": recipe["count"],
        "subjects": recipe["subjects"],
        "recipe": recipe,
    }


def ensure_base(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_text(directory / "base.svg", render_base())
    return directory / "base.svg"


def ensure_artwork(entry, directory, url_prefix, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ensure_base(directory)
    planned = plan_artwork(entry, art_version, extractor_version)
    manifest_path = directory / "manifest.json"
    manifest = _load_manifest(manifest_path)
    items = manifest["items"]
    current = items.get(planned["id"])
    path = directory / planned["filename"]
    fresh = (
        isinstance(current, dict)
        and current.get("source_digest") == planned["source_digest"]
        and current.get("art_version") == art_version
        and current.get("extractor_version") == extractor_version
        and path.exists()
    )
    if not fresh and planned["filename"] != "base.svg":
        _atomic_text(path, planned["svg"])
        items[planned["id"]] = {
            "filename": planned["filename"],
            "source_digest": planned["source_digest"],
            "recipe_digest": planned["recipe_digest"],
            "art_version": art_version,
            "extractor_version": extractor_version,
            "kind": planned["kind"],
            "family": planned["family"],
            "reason": planned["reason"],
            "basis": planned["basis"],
        }
        manifest["art_version"] = art_version
        manifest["extractor_version"] = extractor_version
        _atomic_json(manifest_path, manifest)
    elif not path.exists() and planned["filename"] == "base.svg":
        ensure_base(directory)
    return _public(planned, url_prefix)


def generate_library(entries, directory, url_prefix, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    directory = Path(directory)
    if directory.exists():
        for child in directory.glob("*.svg"):
            if child.name != "base.svg" and SAFE_NAME.match(child.name):
                pass
    directory.mkdir(parents=True, exist_ok=True)
    ensure_base(directory)
    items = {}
    stats = {"total": 0, "generated": 0, "abstract": 0, "fallback": 0, "failed": 0, "bytes": 0}
    families = {}
    for entry in entries:
        stats["total"] += 1
        try:
            planned = plan_artwork(entry, art_version, extractor_version)
            if planned["filename"] != "base.svg":
                _atomic_text(directory / planned["filename"], planned["svg"])
            items[planned["id"]] = {
                "filename": planned["filename"],
                "source_digest": planned["source_digest"],
                "recipe_digest": planned["recipe_digest"],
                "art_version": art_version,
                "extractor_version": extractor_version,
                "kind": planned["kind"],
                "family": planned["family"],
                "reason": planned["reason"],
                "basis": planned["basis"],
                "subjects": planned["subjects"],
                "count": planned["count"],
            }
            size = len(planned["svg"].encode("utf-8"))
            stats["bytes"] += size
            stats[planned["kind"]] = stats.get(planned["kind"], 0) + 1
            families[planned["family"]] = families.get(planned["family"], 0) + 1
        except Exception:
            stats["failed"] += 1
    manifest = {
        "art_version": art_version,
        "extractor_version": extractor_version,
        "items": items,
        "stats": {**stats, "families": families},
    }
    _atomic_json(directory / "manifest.json", manifest)
    expected = {row["filename"] for row in items.values()} | {"base.svg"}
    for child in directory.glob("*.svg"):
        if child.name not in expected and SAFE_NAME.match(child.name):
            child.unlink()
    return manifest


def annotate_display(entry, artwork):
    image = entry.get("image") if isinstance(entry.get("image"), str) else None
    source = entry.get("image_source") if isinstance(entry.get("image_source"), str) else None
    verified = entry.get("image_reuse") == "verified" and isinstance(image, str) and image.startswith("https://")
    row = {
        "artwork_url": artwork["artwork_url"],
        "artwork_kind": artwork["artwork_kind"],
        "artwork_family": artwork["artwork_family"],
        "artwork_basis": artwork["artwork_basis"],
        "artwork_reason": artwork["artwork_reason"],
        "image": image,
        "image_source": source,
        "image_reuse": "verified" if verified else "unverified",
        "display_image": image if verified else None,
    }
    return row


def resolve_artwork_path(directory, name):
    if not isinstance(name, str) or not SAFE_NAME.match(name):
        return None
    directory = Path(directory).resolve()
    path = (directory / name).resolve()
    if path.parent != directory or not path.is_file():
        return None
    return path


def label_for(motif):
    return LABELS.get(motif, motif)
