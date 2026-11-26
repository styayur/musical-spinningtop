"""Evidence-backed imagery extraction. No network and no per-show branches."""
from __future__ import annotations

import re

from artwork.lexicon import (
    COUNT_WORDS,
    GENRE_FACTOR,
    GENRE_PATTERNS,
    LABELS,
    META_FACTOR,
    META_PATTERNS,
    RULES,
    TITLE_FACTOR,
    UNCERTAIN_FACTOR,
    ZH_COUNT_WORDS,
)

_EN_RULES = tuple(rule for rule in RULES if rule[2] == "en")
_ZH_RULES = tuple(sorted((rule for rule in RULES if rule[2] == "zh"), key=lambda rule: len(rule[3]), reverse=True))
_EN_PATTERNS = tuple(
    (rule, re.compile(r"\b" + r"\s+".join(re.escape(part) for part in rule[3].split()) + r"\b", re.IGNORECASE))
    for rule in sorted(_EN_RULES, key=lambda rule: len(rule[3]), reverse=True)
)
_META = tuple(re.compile(pattern, re.IGNORECASE) for pattern in META_PATTERNS)
_CREATOR_CREDIT = re.compile(
    r"(?i:\b(?:created|illustrated|drawn)\s+by\s+|"
    r"\b(?:creator|illustrator|composer|lyricist|playwright|director|author)\s+)"
    r"[A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*){1,4}"
)
_SONG_CONTEXT = re.compile(
    r"(?:\b(?:songs?|hits?|tracks?|numbers?)\s*(?:(?:such as|including|called|titled|named|"
    r"include[sd]?|are|is)\s*)?|(?:歌曲|曲目|单曲)(?:包括|包含|有|如|名为|叫做)?\s*)[:：]?\s*$",
    re.IGNORECASE,
)
_QUOTED_TITLE = re.compile(r'"[^"\n]{1,120}"|“[^”\n]{1,120}”|《[^》\n]{1,120}》|(?<!\w)\x27[^\x27\n]{1,120}\x27(?!\w)')
_TITLE_LIST_SEPARATOR = re.compile(r"\s*(?:(?:,|、|and\b|or\b|&|和|及|以及)\s*)*", re.IGNORECASE)
_PRODUCTION_CONTEXT = re.compile(
    r"\b(?:tour|touring production|production|revival|tryouts?|previews?)\s+"
    r"(?:(?:was|has|had|will|first|officially)\s+){0,2}"
    r"(?:started|began|opened|launched|visited|played|closed|ended)\b[^.!?;。！？；]{0,180}"
    r"|(?:巡演|巡回演出|复排|预演)(?:在|于|从|开始)[^.!?;。！？；]{0,100}",
    re.IGNORECASE,
)
_PLOT_RESUMES = re.compile(r"\b(?:but|while|whereas|the story|the plot)\b|但是|但|故事|剧情", re.IGNORECASE)
_GENRE = tuple(re.compile(pattern, re.IGNORECASE) for pattern in GENRE_PATTERNS)
_COUNT = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|\d{1,2})\s+"
    r"(?:(?:dead|young|old|elderly|stage|professional|retired|female|male|"
    r"lost|estranged|orphaned|teenage|adult|child|local)\s+){0,3}"
    r"(actors?|actresses|performers?|characters?|brothers?|sisters?|friends?|"
    r"dancers?|singers?|women|men|boys|girls|children|orphans|soldiers|sailors|ghosts)\b",
    re.IGNORECASE,
)
_ZH_COUNT = re.compile(
    r"(?<![\d零〇一二三四五六七八九十百千万两])([一二三四五六七八两1-8])"
    r"(?:位|个|名)(?:(?:年轻|年老|死去|失散|舞台|职业|退休)的?){0,2}"
    r"(演员|人|兄弟|姐妹|朋友|舞者|孩子|孤儿)"
)
_CLEAR_NEGATION = re.compile(
    r"\b(?:not|no|never|without|isn['’]t|isnt|aren['’]t|arent)\b"
    r"(?:\s+(?:a|an|the|any|about|of|involving|involve|involves|depict|depicts|"
    r"feature|features|include|includes|story|tale|really)){0,4}\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_LOVE = re.compile(r"\b(?:without|no)\s+$", re.IGNORECASE)
_NOT_ONLY = re.compile(r"\bnot only\b", re.IGNORECASE)
_ZH_IMMEDIATE = re.compile(r"(?:不涉及|并非|无关|不是|并不|没有|不含)(?:任何|一场|一个|一段|有关)?\s*$")
_VENUE_TAIL = re.compile(r"\s+(?:theatre|theater|hall|playhouse)\b", re.IGNORECASE)
_TRAIN_SUBJECT = re.compile(
    r"\b(?:I|you|we|they|he|she|people|actors|actresses|performers|dancers|singers|"
    r"soldiers|students|children|men|women|boys|girls|recruits|athletes|brothers|sisters|friends)\s+$",
    re.IGNORECASE,
)
_TRAIN_VERB_TAIL = re.compile(r"\s+(?:daily|to|for|as)\b", re.IGNORECASE)
_BIO = (
    re.compile(
        r"(?i:\b(?:composer|lyricist|librettist|author|writer|creator|playwright|director|choreographer)\b)"
        r"(?:\s+[A-Z][\w’'-]*){0,4}\s+(?i:(?:who\s+)?(?:died|was born)\b)",
    ),
)
_UNCERTAIN_RULES = {"zh:without-love"}
_SYNOPSIS = {"intro_en", "intro_zh"}
_ZH_VENUE = ("剧院", "剧场", "大厅")


def _spans(patterns, text):
    found = []
    for pattern in patterns:
        found.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return found


def _overlaps(spans, start, end):
    return any(start < stop and end > begin for begin, stop in spans)


def _window(text, start):
    chunk = text[max(0, start - 48):start]
    chunk = re.split(r"[.!?;,:。！？；，：]|\b(?:but|yet|however)\b", chunk, flags=re.IGNORECASE)[-1]
    return _NOT_ONLY.sub("", chunk).lstrip()


def _echo_spans(text, titles):
    """Recognize quoted references and sentence-opening, bounded title echoes."""
    spans = []
    for title in titles:
        title = title.strip()
        if not title:
            continue
        escaped = re.escape(title)
        if title[0].isascii() and title[0].isalnum():
            escaped = r"(?<!\w)" + escaped
        if title[-1].isascii() and title[-1].isalnum():
            escaped += r"(?!\w)"
        for match in re.finditer(escaped, text, re.IGNORECASE):
            before = text[:match.start()].rstrip()
            after = text[match.end():]
            quoted = bool(before and before[-1] in '\"“‘《「' and after and after[0] in '\"”’》」')
            opening = not before or before[-1] in ".!?。！？"
            if quoted or opening:
                spans.append(match.span())
    return spans


def _meta_spans(text):
    """Limit broad credit patterns to sentences, including Chinese full stops."""
    spans = _spans((_CREATOR_CREDIT,), text)
    last_song_end = None
    for title in _QUOTED_TITLE.finditer(text):
        continuation = (last_song_end is not None
                        and _TITLE_LIST_SEPARATOR.fullmatch(text[last_song_end:title.start()]))
        if continuation or _SONG_CONTEXT.search(text[max(0, title.start() - 80):title.start()]):
            spans.append(title.span())
            last_song_end = title.end()
        else:
            last_song_end = None
    for production in _PRODUCTION_CONTEXT.finditer(text):
        boundary = _PLOT_RESUMES.search(production.group())
        spans.append((production.start(), production.start() + boundary.start() if boundary else production.end()))
    for sentence in re.finditer(r"[^.!?;。！？；]+", text):
        spans.extend((sentence.start() + start, sentence.start() + end)
                     for start, end in _spans(_META, sentence.group()))
    return spans


def _venue_name(text, start, end, motif):
    if motif != "garden":
        return False
    if _VENUE_TAIL.match(text[end:end + 24]):
        return True
    return text[end:end + 2] in _ZH_VENUE


def _biographical(text, start, end, motif):
    if motif != "death":
        return False
    return _overlaps(_spans(_BIO, text), start, end)


def _negation(text, start, motif, rule_id):
    if rule_id in _UNCERTAIN_RULES:
        return "uncertain"
    window = _window(text, start)
    if _ZH_IMMEDIATE.search(window):
        return "clear"
    if "没有爱" in text[max(0, start - 2):start + 3] and motif == "love":
        return "uncertain"
    if motif in {"love", "romance"} and _AMBIGUOUS_LOVE.search(window):
        return "uncertain"
    if _CLEAR_NEGATION.search(window):
        return "clear"
    return None


def _hit(rule, field, text, start, end, meta, genre):
    return _hit_with_echo(rule, field, text, start, end, meta, genre, ())


def _hit_with_echo(rule, field, text, start, end, meta, genre, echo):
    motif, category, _language, phrase, weight, rule_id = rule
    if _venue_name(text, start, end, motif) or _biographical(text, start, end, motif):
        return None
    if (rule_id == "en:train" and _TRAIN_SUBJECT.search(text[max(0, start - 32):start])
            and _TRAIN_VERB_TAIL.match(text[end:])):
        return None
    penalties = []
    score = float(weight)
    if field in {"title", "title_zh"}:
        score *= TITLE_FACTOR
        penalties.append("title")
    if _overlaps(echo, start, end):
        score *= TITLE_FACTOR
        penalties.append("title-echo")
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


def _english_hits(field, text, meta, genre, echo=()):
    occupied = []
    hits = []
    for rule, pattern in _EN_PATTERNS:
        for match in pattern.finditer(text):
            if _overlaps(occupied, match.start(), match.end()):
                continue
            hit = _hit_with_echo(rule, field, text, match.start(), match.end(), meta, genre, echo)
            occupied.append((match.start(), match.end()))
            if hit:
                hits.append(hit)
    return hits


def _chinese_hits(field, text, meta, genre, echo=()):
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
                hit = _hit_with_echo(rule, field, text, found, end, meta, genre, echo)
                occupied.append((found, end))
                if hit:
                    hits.append(hit)
            start = found + 1
    return hits


def _count_negated(text, start):
    window = _window(text, start)
    return bool(_CLEAR_NEGATION.search(window) or _ZH_IMMEDIATE.search(window))


def _count(fields, titles=()):
    found = []
    for field in fields:
        if field["name"] not in _SYNOPSIS:
            continue
        text = field["text"]
        excluded = _meta_spans(text) + _echo_spans(text, titles)
        for match in _COUNT.finditer(text):
            if not _overlaps(excluded, match.start(), match.end()):
                found.append((field["name"], match.start(), match))
        for match in _ZH_COUNT.finditer(text):
            if not _overlaps(excluded, match.start(), match.end()):
                found.append((field["name"], match.start(), match))
    order = {"intro_zh": 0, "intro_en": 1}
    found.sort(key=lambda item: (order.get(item[0], 9), item[1]))
    for field_name, _start, match in found:
        field = next(item for item in fields if item["name"] == field_name)
        text = field["text"]
        if _count_negated(text, match.start()):
            continue
        if match.re is _ZH_COUNT:
            raw = match.group(1)
            value = ZH_COUNT_WORDS.get(raw, 1 if raw == "一" else int(raw) if raw.isdigit() else 0)
        else:
            raw = match.group(1).lower()
            value = COUNT_WORDS.get(raw, int(raw) if raw.isdigit() else 0)
        if 1 <= value <= 8:
            return value
    return None


def extract_imagery(normalized):
    hits = []
    titles = (normalized.get("title") or "", normalized.get("title_zh") or "")
    for field in normalized["fields"]:
        text = field["text"]
        meta = _meta_spans(text)
        genre = _spans(_GENRE, text)
        echo = _echo_spans(text, titles) if field["name"] in _SYNOPSIS else ()
        if re.search(r"[\u4e00-\u9fff]", text):
            hits.extend(_chinese_hits(field["name"], text, meta, genre, echo))
        hits.extend(_english_hits(field["name"], text, meta, genre, echo))
    hits.sort(key=lambda item: (-item["score"], item["source_field"], item["start"], item["rule_id"]))
    synopsis_scores = {}
    for hit in hits:
        if hit["source_field"] not in _SYNOPSIS:
            continue
        if hit["penalties"]:
            continue
        synopsis_scores[hit["motif"]] = synopsis_scores.get(hit["motif"], 0) + hit["score"]
    empty = not any(field["name"] in _SYNOPSIS for field in normalized["fields"])
    return {
        "hits": hits,
        "synopsis_scores": synopsis_scores,
        "count": _count(normalized["fields"], titles),
        "empty": empty,
        "collapsed": list(normalized["collapsed"]),
    }
