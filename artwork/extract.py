"""Evidence-backed imagery extraction. No network and no per-show branches."""
from __future__ import annotations

import re

from artwork.lexicon import (
    COUNT_PATTERN,
    COUNT_WORDS,
    GENRE_FACTOR,
    GENRE_PATTERNS,
    LABELS,
    META_FACTOR,
    META_PATTERNS,
    RULES,
    TITLE_FACTOR,
    UNCERTAIN_FACTOR,
    ZH_COUNT_PATTERN,
    ZH_COUNT_WORDS,
)

_EN_RULES = tuple(rule for rule in RULES if rule[2] == "en")
_ZH_RULES = tuple(sorted((rule for rule in RULES if rule[2] == "zh"), key=lambda rule: len(rule[3]), reverse=True))
_EN_PATTERNS = tuple(
    (rule, re.compile(r"\b" + r"\s+".join(re.escape(part) for part in rule[3].split()) + r"\b", re.IGNORECASE))
    for rule in sorted(_EN_RULES, key=lambda rule: len(rule[3]), reverse=True)
)
_META = tuple(re.compile(pattern, re.IGNORECASE) for pattern in META_PATTERNS)
_GENRE = tuple(re.compile(pattern, re.IGNORECASE) for pattern in GENRE_PATTERNS)
_COUNT = re.compile(COUNT_PATTERN, re.IGNORECASE)
_ZH_COUNT = re.compile(ZH_COUNT_PATTERN)
_CLEAR_NEGATION = re.compile(
    r"\b(?:not|no|never|without|isn['’]t|isnt|aren['’]t|arent)\b(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_LOVE = re.compile(r"\b(?:without|no)\s+$", re.IGNORECASE)
_NOT_ONLY = re.compile(r"\bnot only\b", re.IGNORECASE)
_ZH_CLEAR = ("不涉及", "并非", "无关", "不是", "并不")
_UNCERTAIN_RULES = {"zh:without-love"}
_SYNOPSIS = {"intro_en", "intro_zh"}


def _spans(patterns, text):
    found = []
    for pattern in patterns:
        found.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return found


def _overlaps(spans, start, end):
    return any(start < stop and end > begin for begin, stop in spans)


def _window(text, start):
    chunk = text[max(0, start - 48):start]
    for separator in ".!?;。！？；":
        if separator in chunk:
            chunk = chunk.rsplit(separator, 1)[-1]
    return chunk.lstrip()


def _negation(text, start, motif, rule_id):
    if rule_id in _UNCERTAIN_RULES:
        return "uncertain"
    window = _window(text, start)
    if _NOT_ONLY.search(window):
        return None
    tail = text[max(0, start - 8):start]
    if any(mark in tail for mark in _ZH_CLEAR):
        return "clear"
    if "没有爱" in text[max(0, start - 2):start + 3] and motif == "love":
        return "uncertain"
    if motif in {"love", "romance"} and _AMBIGUOUS_LOVE.search(window):
        return "uncertain"
    if _CLEAR_NEGATION.search(window):
        return "clear"
    return None


def _hit(rule, field, text, start, end, meta, genre):
    motif, category, _language, phrase, weight, rule_id = rule
    penalties = []
    score = float(weight)
    if field in {"title", "title_zh"}:
        score *= TITLE_FACTOR
        penalties.append("title")
    if _overlaps(meta, start, end):
        score *= META_FACTOR
        penalties.append("meta")
    if _overlaps(genre, start, end):
        score *= GENRE_FACTOR
        penalties.append("genre")
    negation = _negation(text, start, motif, rule_id)
    if negation == "clear":
        return None
    if negation == "uncertain":
        score *= UNCERTAIN_FACTOR
        penalties.append("uncertain-negation")
    return {
        "motif": motif,
        "label": LABELS.get(motif, motif),
        "category": category,
        "source_field": field,
        "phrase": text[start:end],
        "start": start,
        "end": end,
        "rule_id": rule_id,
        "score": round(score, 3),
        "penalties": penalties,
    }


def _english_hits(field, text, meta, genre):
    occupied = []
    hits = []
    for rule, pattern in _EN_PATTERNS:
        for match in pattern.finditer(text):
            if _overlaps(occupied, match.start(), match.end()):
                continue
            hit = _hit(rule, field, text, match.start(), match.end(), meta, genre)
            occupied.append((match.start(), match.end()))
            if hit:
                hits.append(hit)
    return hits


def _chinese_hits(field, text, meta, genre):
    occupied = []
    hits = []
    for rule in _ZH_RULES:
        phrase = rule[3]
        start = 0
        while True:
            found = text.find(phrase, start)
            if found < 0:
                break
            end = found + len(phrase)
            if not _overlaps(occupied, found, end):
                hit = _hit(rule, field, text, found, end, meta, genre)
                occupied.append((found, end))
                if hit:
                    hits.append(hit)
            start = found + 1
    return hits


def _count(fields):
    best = None
    for field in fields:
        if field["name"] not in _SYNOPSIS:
            continue
        text = field["text"]
        for match in _COUNT.finditer(text):
            raw = match.group(1).lower()
            value = COUNT_WORDS.get(raw, int(raw) if raw.isdigit() else 0)
            if 1 <= value <= 8 and (best is None or value > best):
                best = value
        for match in _ZH_COUNT.finditer(text):
            value = ZH_COUNT_WORDS.get(match.group(1), 0)
            if 1 <= value <= 8 and (best is None or value > best):
                best = value
    return best


def extract_imagery(normalized):
    hits = []
    for field in normalized["fields"]:
        text = field["text"]
        meta = _spans(_META, text)
        genre = _spans(_GENRE, text)
        if re.search(r"[\u4e00-\u9fff]", text):
            hits.extend(_chinese_hits(field["name"], text, meta, genre))
        hits.extend(_english_hits(field["name"], text, meta, genre))
    hits.sort(key=lambda item: (-item["score"], item["source_field"], item["start"], item["rule_id"]))
    synopsis_scores = {}
    for hit in hits:
        if hit["source_field"] in _SYNOPSIS and "title" not in hit["penalties"]:
            synopsis_scores[hit["motif"]] = synopsis_scores.get(hit["motif"], 0) + hit["score"]
    empty = not any(field["name"] in _SYNOPSIS for field in normalized["fields"])
    return {
        "hits": hits,
        "synopsis_scores": synopsis_scores,
        "count": _count(normalized["fields"]),
        "empty": empty,
        "collapsed": list(normalized["collapsed"]),
    }
