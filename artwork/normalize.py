"""Normalize catalogue rows into the generator input.

The digest covers only fields that can change an illustration. Year is display
data and is not an imagery input. Identical Chinese and English text is scored
once.
"""
from __future__ import annotations

import hashlib
import json
import re

_SPACE = re.compile(r"\s+")


def clean_text(value):
    if not isinstance(value, str):
        return ""
    return _SPACE.sub(" ", value.replace("\u00a0", " ")).strip()


def normalize_entry(entry):
    """Return a plain dict. Missing or unsafe ids are preserved for the caller to reject."""
    if not isinstance(entry, dict):
        entry = {}
    identity = entry.get("id")
    identity = identity.strip() if isinstance(identity, str) else ""
    title = clean_text(entry.get("title"))
    title_zh = clean_text(entry.get("title_zh"))
    intro_en = clean_text(entry.get("intro_en"))
    intro_zh = clean_text(entry.get("intro_zh"))
    translator = entry.get("translator") if isinstance(entry.get("translator"), str) else ""
    fields = []
    seen = set()
    collapsed = []
    for name, text in (("intro_zh", intro_zh), ("intro_en", intro_en), ("title_zh", title_zh), ("title", title)):
        key = text.casefold()
        if not key:
            continue
        if key in seen:
            collapsed.append(name)
            continue
        seen.add(key)
        fields.append({"name": name, "text": text})
    payload = {
        "id": identity,
        "title": title,
        "title_zh": title_zh,
        "intro_en": intro_en,
        "intro_zh": intro_zh,
        "collapsed": collapsed,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "id": identity,
        "title": title,
        "title_zh": title_zh,
        "intro_en": intro_en,
        "intro_zh": intro_zh,
        "translator": translator,
        "fields": fields,
        "collapsed": collapsed,
        "source_digest": digest,
        "image": entry.get("image") if isinstance(entry.get("image"), str) else None,
        "image_source": entry.get("image_source") if isinstance(entry.get("image_source"), str) else None,
        "image_reuse": entry.get("image_reuse") if isinstance(entry.get("image_reuse"), str) else "",
        "year": entry.get("year") if isinstance(entry.get("year"), int) else None,
    }


def merge_publication(entry, article=None, summary=""):
    """Match the static site's catalogue/article/summary merge."""
    article = article or {}
    row = {**entry, **article}
    row["title_zh"] = article.get("title_zh") or entry.get("title_zh") or ""
    if summary:
        row["intro_zh"] = summary
        row["translator"] = "bundled"
    if row.get("intro_zh") and row.get("intro_zh") == row.get("intro_en"):
        row.pop("intro_zh", None)
    return row
