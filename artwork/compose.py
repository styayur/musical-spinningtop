"""Choose a composition from imagery. Seeds never choose the family or subject."""
from __future__ import annotations

import hashlib
import json

from artwork.lexicon import FAMILY_OF, SELECTION_THRESHOLD
from artwork.versions import ART_VERSION, EXTRACTOR_VERSION

_STILL = ("letter", "clock", "crown", "mask", "plant", "mirror", "ring")
_ROUTE_SUBJECT = ("ship", "train", "travel", "map", "island")
_TERRAIN = ("forest", "ocean", "garden", "mountain", "river", "desert")
_CITY = ("palace", "station", "street", "bridge", "prison", "school", "city")


def derived_int(identity, purpose, art_version=ART_VERSION):
    # Version 5 changes ink and canvas only; preserve the reviewed v4 geometry.
    if str(art_version) == "5":
        art_version = "4"
    digest = hashlib.sha256(f"{art_version}|{purpose}|{identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _ranked(scores, names):
    found = [name for name in names if scores.get(name, 0) >= 0.8]
    found.sort(key=lambda name: (-scores[name], name))
    return found


def _arrangement(scores):
    order = (
        ("separation", "apart"),
        ("reunion", "reunion"),
        ("conflict", "conflict"),
        ("power", "power"),
        ("ghost", "ghost"),
        ("death", "absence"),
        ("family", "family"),
        ("child", "family"),
        ("love", "together"),
        ("friendship", "together"),
    )
    for motif, name in order:
        if scores.get(motif, 0) >= 0.8:
            return name
    return "together"


def _count_for(family, arrangement, explicit, scores, subjects=()):
    """Count figures drawn by the selected subject, not all mentioned people."""
    if family not in {"stage", "portal", "relation"} and not (family == "route" and subjects[:1] == ["travel"]):
        return 0
    if explicit:
        return max(1, min(8, explicit))
    if family == "route":
        return 1
    if family == "stage":
        return 3 if scores.get("perform", 0) >= 1.6 or scores.get("dance", 0) >= 1.6 else 0
    if family == "portal":
        return 1 if scores.get("search", 0) >= 1.6 or scores.get("escape", 0) >= 1.6 else 0
    if family != "relation":
        return 0
    if arrangement == "conflict":
        return 4
    if arrangement == "family":
        return 3
    if arrangement == "power":
        return 3
    if arrangement == "absence":
        return 1
    if arrangement == "ghost":
        return 2
    return 2


def compose(normalized, extraction, art_version=ART_VERSION, extractor_version=EXTRACTOR_VERSION):
    scores = extraction["synopsis_scores"]
    totals = {}
    for motif, score in scores.items():
        family = FAMILY_OF.get(motif)
        if not family or score < 0.8:
            continue
        totals[family] = totals.get(family, 0) + score
    ranked = sorted(totals, key=lambda name: (-totals[name], name))
    reason = None
    kind = "generated"
    if extraction["empty"]:
        family = "abstract"
        kind = "abstract"
        reason = "empty"
    elif not ranked or totals[ranked[0]] < SELECTION_THRESHOLD:
        family = "abstract"
        kind = "abstract"
        reason = "insufficient"
    else:
        family = ranked[0]
    subjects = _ranked(scores, {
        "portal": ("door", "search", "escape"),
        "city": _CITY,
        "relation": ("separation", "reunion", "conflict", "power", "ghost", "death", "family", "child", "love", "friendship"),
        "still": _STILL,
        "route": _ROUTE_SUBJECT,
        "stage": ("stage", "perform", "dance", "heaven"),
        "terrain": _TERRAIN,
        "abstract": (),
    }[family])
    if family == "still" and subjects:
        subjects = subjects[:1]
    arrangement = _arrangement(scores) if family == "relation" else ""
    modifiers = tuple(
        name for name in ("heaven", "death", "separation", "reunion", "ship", "ocean", "station", "palace", "child", "ghost", "conflict", "dream")
        if scores.get(name, 0) >= 0.8
    )
    count = _count_for(family, arrangement, extraction["count"], scores, subjects)
    identity = normalized["id"] or "missing"
    recipe = {
        "family": family,
        "subjects": list(subjects),
        "arrangement": arrangement,
        "count": count,
        "modifiers": list(modifiers),
        "palette": derived_int(identity, "palette", art_version) % 3,
        "mirror": bool(derived_int(identity, "mirror", art_version) % 2),
        "detail": derived_int(identity, "detail", art_version) % 3,
        "abstract_layout": derived_int(identity, "abstract-layout", art_version) % 8,
        "kind": kind,
        "reason": reason,
        "art_version": art_version,
        "extractor_version": extractor_version,
    }
    recipe["recipe_digest"] = hashlib.sha256(
        json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return recipe
