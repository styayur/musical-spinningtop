"""Cache, manifest, and publication records for generated artwork."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from artwork.compose import compose
from artwork.draw import drawn_motifs, render_base, render_svg
from artwork.extract import extract_imagery
from artwork.lexicon import LABELS
from artwork.normalize import normalize_entry
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION

SAFE_NAME = re.compile(
    r"^(?:[a-f0-9]{20}|base|[0-9A-Za-z]+-[0-9A-Za-z]+-[a-f0-9]{16}-[a-f0-9]{12})\.svg$"
)
MAX_BYTES = 60 * 1024
MAX_NODES = 220
_NODE = re.compile(r"<(?:rect|line|circle|path|polyline|polygon|g|svg)\b")
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _token(value):
    """Encode punctuation and the reserved prefix without aliasing versions."""
    value = str(value)
    if re.fullmatch(r"[0-9a-z]+", value) and not value.startswith("v0"):
        return value
    return "v0" + value.encode("utf-8").hex()


def safe_filename(identity, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION, source_digest=""):
    digest = re.sub(r"[^a-f0-9]", "", str(source_digest or "").lower())[:16].ljust(16, "0")
    token = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:12]
    return f"{_token(art_version)}-{_token(extractor_version)}-{digest}-{token}.svg"


@contextmanager
def _file_lock(path):
    """Serialize threads/processes on a permanent file, locking byte zero.

    Windows permits locking beyond EOF: the empty file needs no racy
    initialization write. Never unlink it while another process may use it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
    with lock, path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(0.02)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _directory_lock(directory):
    """Lock every writer, then remove only our abandoned publication files."""
    directory = Path(directory)
    with _file_lock(directory / ".artwork.lock"):
        for temporary in directory.glob(".artwork-*.tmp"):
            temporary.unlink(missing_ok=True)
        yield


def _atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".artwork-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if path.exists() and path.read_bytes() == data:
                    return
                time.sleep(0.02 * (attempt + 1))
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


def _basis_for(hits, recipe):
    if not recipe or recipe.get("kind") in {"abstract", "fallback"} or recipe.get("family") == "abstract":
        return []
    allowed = drawn_motifs(recipe)
    by_motif = {}
    for hit in hits:
        motif = hit["motif"]
        if motif not in allowed or motif in by_motif:
            continue
        if hit["source_field"] not in {"intro_en", "intro_zh"}:
            continue
        if "title" in hit["penalties"] or "title-echo" in hit["penalties"]:
            continue
        by_motif[motif] = {
            "motif": motif,
            "label": hit["label"],
            "phrase": hit["phrase"],
            "source_field": hit["source_field"],
            "rule_id": hit["rule_id"],
            "score": hit["score"],
        }
    return [by_motif[motif] for motif in allowed if motif in by_motif]


def _public(record, url_prefix):
    name = record["filename"]
    prefix = url_prefix if url_prefix.endswith("/") else url_prefix + "/"
    version = record.get("source_digest", "0")[:8]
    return {
        "artwork_url": f"{prefix}{name}?v={_token(record['art_version'])}-{version}",
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


def _manifest_item(planned):
    return {
        "filename": planned["filename"],
        "source_digest": planned["source_digest"],
        "recipe_digest": planned["recipe_digest"],
        "art_version": planned["art_version"],
        "extractor_version": planned["extractor_version"],
        "kind": planned["kind"],
        "family": planned["family"],
        "reason": planned["reason"],
        "basis": planned["basis"],
        "subjects": planned.get("subjects", []),
        "count": planned.get("count", 0),
    }


def _fresh(current, source_digest, art_version, extractor_version, path):
    return (
        isinstance(current, dict)
        and current.get("source_digest") == source_digest
        and current.get("art_version") == art_version
        and current.get("extractor_version") == extractor_version
        and current.get("reason") != "error"
        and all(key in current for key in ("kind", "family", "basis", "reason", "recipe_digest"))
        and isinstance(current.get("filename"), str)
        and SAFE_NAME.fullmatch(current["filename"]) is not None
        and Path(path).is_file()
    )


def _error_plan(identity, source_digest, art_version, extractor_version):
    return {
        "id": identity,
        "filename": "base.svg",
        "svg": render_base(),
        "kind": "fallback",
        "family": "abstract",
        "reason": "error",
        "basis": [],
        "hits": [],
        "source_digest": source_digest,
        "recipe_digest": "",
        "art_version": art_version,
        "extractor_version": extractor_version,
        "count": 0,
        "subjects": [],
        "recipe": {"family": "abstract", "kind": "fallback", "reason": "error", "subjects": [], "modifiers": []},
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
    try:
        svg = render_svg(recipe)
    except Exception:
        failed = _error_plan(identity, normalized["source_digest"], art_version, extractor_version)
        failed["hits"] = extraction["hits"]
        return failed
    nodes = len(_NODE.findall(svg))
    if len(svg.encode("utf-8")) > MAX_BYTES or nodes > MAX_NODES:
        svg = render_base()
        recipe = {**recipe, "family": "abstract", "kind": "abstract", "reason": "budget", "subjects": [], "modifiers": []}
    basis = [] if recipe.get("kind") != "generated" else _basis_for(extraction["hits"], recipe)
    return {
        "id": identity,
        "filename": safe_filename(identity, art_version, extractor_version, normalized["source_digest"]),
        "svg": svg,
        "kind": recipe["kind"],
        "family": recipe["family"],
        "reason": recipe["reason"],
        "basis": basis,
        "hits": extraction["hits"],
        "source_digest": normalized["source_digest"],
        "recipe_digest": recipe["recipe_digest"],
        "art_version": art_version,
        "extractor_version": extractor_version,
        "count": recipe["count"],
        "subjects": recipe["subjects"],
        "recipe": recipe,
    }


def _ensure_base_locked(directory):
    path = directory / "base.svg"
    if not path.is_file():
        _atomic_text(path, render_base())
    return path


def ensure_base(directory):
    directory = Path(directory)
    with _directory_lock(directory):
        return _ensure_base_locked(directory)


def _cached(current, normalized, art_version, extractor_version, directory):
    name = current.get("filename") if isinstance(current, dict) else None
    return isinstance(name, str) and _fresh(
        current, normalized.get("source_digest"), art_version, extractor_version, directory / name
    )


def _superseded(current, observed, planned, directory):
    """A different publication for this id won while we were planning."""
    return (
        current != observed
        and isinstance(current, dict)
        and _cached(current, current, current.get("art_version"), current.get("extractor_version"), directory)
        and any(current.get(key) != planned.get(key) for key in
                ("source_digest", "art_version", "extractor_version"))
    )


def _publish_svg(directory, planned):
    """Keep existing URL bytes immutable, even if a version was not bumped."""
    if planned["filename"] == "base.svg":
        return
    path = directory / planned["filename"]
    if path.exists():
        if path.read_bytes() != planned["svg"].encode("utf-8"):
            raise ValueError("Artwork bytes changed at an existing URL; bump the generator version")
        return
    _atomic_text(path, planned["svg"])


def ensure_artwork(entry, directory, url_prefix, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    directory = Path(directory)
    normalized = normalize_entry(entry)
    identity = normalized["id"]
    manifest_path = directory / "manifest.json"
    with _directory_lock(directory):
        _ensure_base_locked(directory)
        manifest = _load_manifest(manifest_path)
        observed = manifest["items"].get(identity)
        if _cached(observed, normalized, art_version, extractor_version, directory):
            return _public(observed, url_prefix)
    request = json.dumps([identity, normalized["source_digest"], art_version, extractor_version])
    request_key = hashlib.sha256(request.encode("utf-8")).hexdigest()
    with _file_lock(directory / f".artwork-{request_key}.lock"):
        with _directory_lock(directory):
            current = _load_manifest(manifest_path)["items"].get(identity)
            if _cached(current, normalized, art_version, extractor_version, directory):
                return _public(current, url_prefix)
        try:
            planned = plan_artwork(entry, art_version, extractor_version)
        except Exception:
            planned = _error_plan(identity, normalized["source_digest"], art_version, extractor_version)
        with _directory_lock(directory):
            manifest = _load_manifest(manifest_path)
            current = manifest["items"].get(identity)
            if _superseded(current, observed, planned, directory):
                return _public(current, url_prefix)
            if _cached(current, normalized, art_version, extractor_version, directory):
                return _public(current, url_prefix)
            _publish_svg(directory, planned)
            if identity:
                manifest["items"][identity] = _manifest_item(planned)
                manifest["seq"] = int(manifest.get("seq") or 0) + 1
                manifest["art_version"] = art_version
                manifest["extractor_version"] = extractor_version
                _atomic_json(manifest_path, manifest)
        return _public(planned, url_prefix)


def generate_library(entries, directory, url_prefix, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    with _directory_lock(directory):
        _ensure_base_locked(directory)
        observed = _load_manifest(manifest_path)["items"]
    plans = []
    stats = {"total": 0, "generated": 0, "abstract": 0, "fallback": 0, "failed": 0, "bytes": 0}
    families = {}
    for entry in entries:
        stats["total"] += 1
        try:
            planned = plan_artwork(entry, art_version, extractor_version)
        except Exception:
            normalized = normalize_entry(entry)
            planned = _error_plan(normalized["id"], normalized["source_digest"], art_version, extractor_version)
        if planned["reason"] == "error":
            stats["failed"] += 1
        plans.append(planned)
    with _directory_lock(directory):
        latest = _load_manifest(manifest_path)
        items = {key: value for key, value in latest["items"].items() if value != observed.get(key)}
        for planned in plans:
            identity = planned["id"]
            current = latest["items"].get(identity)
            if _superseded(current, observed.get(identity), planned, directory) or (
                current != observed.get(identity)
                and _cached(current, planned, art_version, extractor_version, directory)
            ):
                item = current
            else:
                _publish_svg(directory, planned)
                item = _manifest_item(planned)
            items[identity] = item
            stats["bytes"] += (directory / item["filename"]).stat().st_size
            stats[item["kind"]] = stats.get(item["kind"], 0) + 1
            families[item["family"]] = families.get(item["family"], 0) + 1
        manifest = {
            "art_version": art_version,
            "extractor_version": extractor_version,
            "seq": int(latest.get("seq") or 0) + 1,
            "items": items,
            "stats": {**stats, "families": families},
        }
        _atomic_json(manifest_path, manifest)
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
