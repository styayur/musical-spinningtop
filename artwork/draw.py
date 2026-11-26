"""Draw a recipe as original line-engraving SVG. No catalogue text enters the markup."""
from __future__ import annotations

import math

PALETTES = (
    {"bg": "#f4efe6", "ink": "#243044", "gold": "#a78462", "wash": "#e4d9c8"},
    {"bg": "#f7f1e8", "ink": "#2c3140", "gold": "#b08968", "wash": "#e8dece"},
    {"bg": "#f3eee4", "ink": "#1e2a36", "gold": "#9c7d5c", "wash": "#e6dccb"},
)
STRUCTURE = {"bg": "#ffffff", "ink": "#243044", "gold": "#243044", "wash": "#ffffff"}
FAMILIES = {"portal", "city", "relation", "still", "route", "stage", "terrain", "abstract"}
SUBJECTS = {
    "door", "search", "escape", "city", "street", "palace", "station", "bridge", "prison", "school",
    "love", "family", "friendship", "separation", "reunion", "power", "conflict", "death", "child",
    "ghost", "letter", "clock", "crown", "mask", "plant", "mirror", "ring", "train", "ship", "travel",
    "map", "island", "stage", "perform", "dance", "heaven", "forest", "ocean", "garden", "mountain",
    "river", "desert", "dream",
}
ARRANGEMENTS = {"", "together", "family", "apart", "reunion", "conflict", "power", "absence", "ghost"}
_FAMILY_SUBJECTS = {
    "portal": {"door", "search", "escape"},
    "city": {"city", "street", "palace", "station", "bridge", "prison", "school"},
    "relation": {"love", "family", "friendship", "separation", "reunion", "power", "conflict", "death", "child", "ghost"},
    "still": {"letter", "clock", "crown", "mask", "plant", "mirror", "ring"},
    "route": {"ship", "train", "island", "map", "travel"},
    "stage": {"stage", "perform", "dance", "heaven"},
    "terrain": {"forest", "ocean", "garden", "mountain", "river", "desert"},
    "abstract": set(),
}


def _esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _bounded(value, limit):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(limit, number))


def _safe_recipe(recipe):
    family = recipe.get("family") if recipe.get("family") in FAMILIES else "abstract"
    subjects = [item for item in recipe.get("subjects") or [] if item in _FAMILY_SUBJECTS[family]][:6]
    modifiers = [item for item in recipe.get("modifiers") or [] if item in SUBJECTS][:8]
    arrangement = recipe.get("arrangement") if recipe.get("arrangement") in ARRANGEMENTS else ""
    return {
        "family": family,
        "subjects": subjects,
        "modifiers": modifiers,
        "arrangement": arrangement,
        "count": _bounded(recipe.get("count"), 8),
        "palette": _bounded(recipe.get("palette"), 2),
        "mirror": bool(recipe.get("mirror")),
        "detail": _bounded(recipe.get("detail"), 2),
        "abstract_layout": _bounded(recipe.get("abstract_layout"), 7),
    }


def drawn_motifs(recipe):
    """Motifs this plate actually paints. Abstract plates paint none of them."""
    safe = _safe_recipe(recipe or {})
    family = safe["family"]
    if family == "abstract":
        return []
    motifs = []

    def add(name):
        if name and name not in motifs:
            motifs.append(name)

    if family == "portal":
        add("door")
        if safe["count"]:
            add("search" if "search" in safe["subjects"] else ("escape" if "escape" in safe["subjects"] else None))
        if "heaven" in safe["modifiers"]:
            add("heaven")
    elif family == "city":
        add(safe["subjects"][0] if safe["subjects"] else "city")
    elif family == "still":
        add(safe["subjects"][0] if safe["subjects"] else "letter")
    elif family == "route":
        add(safe["subjects"][0] if safe["subjects"] else "travel")
    elif family == "terrain":
        add(safe["subjects"][0] if safe["subjects"] else "forest")
    elif family == "stage":
        add("stage")
        if "heaven" in safe["modifiers"]:
            add("heaven")
        if "death" in safe["modifiers"]:
            add("death")
        if safe["count"] and "dance" in safe["subjects"]:
            add("dance")
        if safe["count"] and "perform" in safe["subjects"]:
            add("perform")
    elif family == "relation":
        arrangement = safe["arrangement"] or "together"
        mapped = {
            "apart": "separation",
            "reunion": "reunion",
            "conflict": "conflict",
            "power": "power",
            "absence": "death",
            "ghost": "ghost",
            "family": "family",
            "together": next((item for item in safe["subjects"] if item in {"love", "friendship"}), ""),
        }[arrangement]
        if safe["count"] or arrangement == "absence":
            add(mapped)
        if safe["count"] and arrangement == "family" and "child" in safe["modifiers"]:
            add("child")
    return motifs


class Plate:
    def __init__(self):
        self.marks = []

    def add(self, role, tag, attrs):
        ordered = " ".join(f'{key}="{_esc(attrs[key])}"' for key in attrs)
        self.marks.append((role, f"<{tag} {ordered}/>"))

    def rect(self, x, y, w, h, role="ink", width="2"):
        if role == "wash":
            fill, stroke = "@wash", "none"
        elif role == "bg":
            fill, stroke = "@bg", "none"
        else:
            fill, stroke = "none", ("@gold" if role == "gold" else "@ink")
        self.add(role, "rect", {
            "x": x, "y": y, "width": w, "height": h, "fill": fill, "stroke": stroke, "stroke-width": width,
        })

    def line(self, x1, y1, x2, y2, role="ink", width="2"):
        stroke = "@gold" if role == "gold" else "@ink"
        self.add(role, "line", {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": stroke, "stroke-width": width,
        })

    def circle(self, cx, cy, r, role="ink", width="2"):
        stroke = "@gold" if role == "gold" else "@ink"
        self.add(role, "circle", {
            "cx": cx, "cy": cy, "r": r, "fill": "none", "stroke": stroke, "stroke-width": width,
        })

    def path(self, d, role="ink", width="2"):
        if role == "wash":
            self.add(role, "path", {"d": d, "fill": "@wash", "stroke": "none", "stroke-width": "0"})
            return
        stroke = "@gold" if role == "gold" else "@ink"
        self.add(role, "path", {"d": d, "fill": "none", "stroke": stroke, "stroke-width": width})

    def poly(self, points, role="ink", width="2"):
        stroke = "@gold" if role == "gold" else "@ink"
        self.add(role, "polyline", {
            "points": points, "fill": "none", "stroke": stroke, "stroke-width": width,
        })


def _spread(count, left, right):
    if count <= 0:
        return []
    if count == 1:
        return [(left + right) // 2]
    return [left + (right - left) * index // (count - 1) for index in range(count)]


def _figure(plate, x, y, short=False, role="ink", dancing=False):
    height = 58 if short else 78
    radius = 6 if short else 8
    head = y - height
    plate.circle(x, head, radius, role=role)
    plate.path(f"M {x} {head + radius} L {x - 14} {y} L {x + 14} {y} Z", role=role)
    if dancing:
        plate.path(f"M {x - 20} {head + 12} L {x} {head + 28} L {x + 20} {head + 8}", role=role)
        plate.path(f"M {x - 6} {y} L {x - 18} {y + 10} M {x + 6} {y} L {x + 18} {y - 8}", role=role)


def _frame(plate):
    plate.rect(18, 18, 324, 444, width="1.25")
    plate.rect(26, 26, 308, 428, width="1")


def _portal(plate, recipe):
    x = 54 if recipe["mirror"] else 182
    plate.rect(x + 16, 132, 92, 188, role="wash", width="0")
    plate.path(f"M {x} 148 Q {x + 62} 78 {x + 124} 148")
    plate.rect(x, 148, 124, 210)
    plate.line(x + 62, 164, x + 62, 344)
    plate.rect(x + 16, 176, 34, 64)
    plate.rect(x + 74, 176, 34, 64)
    plate.line(x + 28, 268, x + 38, 268, width="1")
    plate.line(x + 86, 268, x + 96, 268, width="1")
    plate.line(x, 358, x + 124, 358)
    plate.line(40, 430, x + 10, 358)
    plate.line(320, 430, x + 114, 358)
    if "heaven" in recipe["modifiers"]:
        plate.rect(x + 44, 188, 36, 52, role="gold", width="1.25")
    if recipe["count"]:
        for x in _spread(recipe["count"], 54, 306):
            _figure(plate, x, 424, short=True)


def _windows(plate, x, y, w, h):
    cols = 2 if w < 56 else 3
    rows = max(2, min(4, h // 36))
    for col in range(cols):
        for row in range(rows):
            plate.rect(x + 8 + col * ((w - 16) // cols), y + 12 + row * 28, 8, 12, width="1")


def _city(plate, recipe):
    plate.rect(36, 52, 288, 132, role="wash", width="0")
    plate.line(36, 392, 324, 392, width="1.25")
    subject = recipe["subjects"][0] if recipe["subjects"] else "city"
    if subject == "palace":
        plate.path("M 118 246 L 118 156 Q 180 92 242 156 L 242 246")
        plate.rect(78, 246, 204, 146)
        plate.rect(42, 286, 36, 106)
        plate.rect(282, 286, 36, 106)
        plate.line(180, 176, 180, 392)
        plate.rect(162, 300, 36, 56)
    elif subject == "station":
        plate.path("M 40 196 Q 180 148 320 196")
        plate.line(52, 196, 52, 236)
        plate.line(308, 196, 308, 236)
        plate.line(40, 236, 320, 236, width="1.75")
        for index, x in enumerate((48, 116, 184, 252)):
            plate.rect(x, 248, 60, 144)
            _windows(plate, x, 260, 60, 90)
    elif subject == "bridge":
        plate.path("M 40 292 Q 180 188 320 292")
        plate.line(40, 292, 320, 292, width="1.75")
        plate.line(40, 310, 320, 310)
        plate.line(108, 292, 108, 340)
        plate.line(252, 292, 252, 340)
        plate.rect(78, 164, 40, 108)
        plate.rect(160, 136, 44, 136)
        plate.rect(242, 172, 40, 100)
    elif subject == "street":
        specs = ((46, 168), (104, 214), (162, 132), (220, 188), (278, 150))
        for x, height in specs:
            plate.rect(x, 392 - height, 50, height)
            _windows(plate, x, 392 - height + 8, 50, height - 20)
    else:
        specs = ((42, 176), (118, 214), (194, 156), (262, 196))
        for x, height in specs:
            plate.rect(x, 392 - height, 64, height)
            _windows(plate, x, 392 - height + 10, 64, height - 24)
        if subject == "prison":
            plate.line(42, 236, 318, 236)
            plate.line(42, 258, 318, 258)
        if subject == "school":
            plate.path("M 150 150 L 180 122 L 210 150")


def _relation(plate, recipe):
    arrangement = recipe["arrangement"] or "together"
    count = recipe["count"]
    if arrangement == "apart":
        plate.line(40, 372, 150, 372)
        plate.line(210, 372, 320, 372)
        left = (count + 1) // 2
        right = count - left
        for x in _spread(left, 64, 136):
            _figure(plate, x, 372, short=left > 2)
        for x in _spread(right, 224, 300):
            _figure(plate, x, 372, short=right > 2)
    elif arrangement == "reunion":
        plate.line(48, 372, 312, 372, width="1")
        for x in _spread(count, 86, 274):
            _figure(plate, x, 372, short=count > 4)
        plate.circle(180, 250, 14, role="gold")
    elif arrangement == "conflict":
        plate.path("M 40 372 L 150 372 L 168 332 L 40 332 Z")
        plate.path("M 210 332 L 192 372 L 320 372 L 320 332 Z")
        left = (count + 1) // 2
        right = max(0, count - left)
        for x in _spread(left, 54, 144):
            _figure(plate, x, 332, short=True)
        for x in _spread(right, 216, 306):
            _figure(plate, x, 332, short=True)
        plate.path("M 156 250 L 180 214 L 204 250")
        plate.path("M 162 286 L 180 314 L 198 286")
    elif arrangement == "power":
        plate.rect(124, 300, 112, 92)
        plate.line(108, 392, 252, 392)
        if count:
            _figure(plate, 180, 300)
        rest = max(0, count - 1)
        for x in _spread(rest, 54, 306):
            _figure(plate, x, 392, short=True)
    elif arrangement == "absence":
        plate.line(48, 372, 312, 372, width="1")
        for x in _spread(count, 54, 306):
            _figure(plate, x, 420, short=True)
        plate.rect(214, 286, 52, 86)
        plate.line(214, 286, 266, 266)
        plate.line(266, 266, 266, 372)
        plate.line(228, 318, 250, 318, width="1")
    elif arrangement == "ghost":
        plate.line(48, 372, 312, 372, width="1")
        xs = _spread(count, 54, 306)
        for index, x in enumerate(xs):
            _figure(plate, x, 372 if index else 356, role="gold" if index == len(xs) - 1 else "ink")
    elif arrangement == "family":
        plate.line(64, 378, 296, 378, width="1.25")
        xs = _spread(count, 54, 306)
        for index, x in enumerate(xs):
            _figure(plate, x, 378, short=(index == len(xs) // 2 and "child" in recipe["modifiers"]))
    else:
        plate.line(108, 378, 252, 378, width="1.25")
        xs = _spread(count, 54, 306) if count > 3 else _spread(count, 138, 222)
        for x in xs:
            _figure(plate, x, 378)


def _still(plate, recipe):
    subject = recipe["subjects"][0] if recipe["subjects"] else "letter"
    if subject == "clock":
        plate.circle(180, 214, 86)
        for x1, y1, x2, y2 in (
            (180, 134, 180, 150), (241, 155, 230, 166), (260, 214, 244, 214), (241, 273, 230, 262),
            (180, 294, 180, 278), (119, 273, 130, 262), (100, 214, 116, 214), (119, 155, 130, 166),
        ):
            plate.line(x1, y1, x2, y2, width="1.1")
        hands = (
            ((180, 214, 180, 156), (180, 214, 232, 214)),
            ((180, 214, 146, 178), (180, 214, 220, 258)),
            ((180, 214, 210, 154), (180, 214, 142, 246)),
        )[recipe["detail"]]
        plate.line(*hands[0], role="gold", width="1.5")
        plate.line(*hands[1], width="1.25")
        plate.circle(180, 214, 3)
    elif subject == "crown":
        plate.path("M 92 292 L 116 168 L 148 226 L 180 142 L 212 226 L 244 168 L 268 292 Z")
        plate.line(92, 292, 268, 292, width="1.75")
        plate.line(104, 312, 256, 312)
        plate.circle(180, 168, 4, role="gold")
    elif subject == "mask":
        plate.path("M 108 132 Q 180 96 252 132 Q 274 220 180 300 Q 86 220 108 132 Z")
        plate.circle(150, 186, 14)
        plate.circle(210, 186, 14)
        plate.path("M 152 242 Q 180 262 208 242")
    elif subject == "plant":
        plate.line(180, 168, 180, 332, width="1.75")
        plate.path("M 180 250 Q 112 214 104 164")
        plate.path("M 180 220 Q 248 186 258 136")
        plate.path("M 180 188 Q 140 132 164 96")
        plate.rect(142, 332, 76, 30)
    elif subject == "mirror":
        plate.path("M 112 108 Q 180 72 248 108 L 248 252 Q 180 300 112 252 Z")
        plate.line(180, 300, 180, 356)
        plate.line(142, 356, 218, 356, width="1.75")
    elif subject == "ring":
        plate.circle(180, 196, 62)
        plate.circle(180, 196, 40)
        plate.path("M 160 250 L 180 196 L 200 250 Z", role="gold")
    else:
        plate.rect(96, 132, 168, 196)
        plate.path("M 96 132 L 180 214 L 264 132")
        plate.line(122, 248, 238, 248, width="1.1")
        plate.line(122, 270, 214, 270, width="1.1")
    plate.line(84, 396, 276, 396, width="1")


def _route(plate, recipe):
    subject = recipe["subjects"][0] if recipe["subjects"] else "travel"
    if subject == "ship":
        plate.poly("32,214 78,198 124,214 170,198 216,214 262,198 308,214 332,202")
        plate.poly("28,268 92,250 156,268 220,250 284,268 336,252")
        plate.poly("36,322 120,304 204,322 288,304 332,318")
        plate.path("M 92 268 L 128 214 L 246 214 L 286 268 Z")
        plate.line(164, 214, 164, 112)
        plate.path("M 164 124 L 220 168 L 164 184")
        plate.line(128, 268, 246, 268, role="gold", width="1.1")
    elif subject == "train":
        plate.line(32, 318, 328, 318, width="1.75")
        plate.line(32, 336, 328, 336)
        plate.rect(86, 236, 156, 82)
        plate.rect(242, 262, 48, 56)
        plate.rect(98, 250, 36, 24)
        plate.rect(146, 250, 36, 24)
        plate.circle(118, 326, 14)
        plate.circle(176, 326, 14)
        plate.circle(220, 326, 14)
        plate.poly("40,168 108,132 176,168 244,124 320,160", role="gold", width="1.25")
    elif subject == "island":
        plate.poly("28,236 96,220 164,236 232,218 300,236 332,224")
        plate.poly("24,292 108,274 192,292 276,274 336,292")
        plate.path("M 112 246 Q 180 176 252 252 Q 180 304 112 246 Z")
        plate.line(180, 210, 180, 146)
        plate.path("M 180 146 L 214 176 L 180 182")
    else:
        plate.poly("44,400 108,292 164,328 226,196 312,96", width="1.75")
        for x, y in ((44, 400), (108, 292), (164, 328), (226, 196), (312, 96)):
            plate.rect(x - 6, y - 6, 12, 12)
        if subject == "map":
            plate.path("M 30 104 L 130 76 L 230 104 L 330 76 L 330 404 L 230 432 L 130 404 L 30 432 Z")
            plate.line(130, 76, 130, 404, width="1")
            plate.line(230, 104, 230, 432, width="1")
        else:
            for x in _spread(recipe["count"], 54, 306):
                _figure(plate, x, 424, short=True)
        plate.circle(312, 96, 10, role="gold")


def _stage(plate, recipe):
    plate.path("M 72 292 L 288 292 L 318 400 L 42 400 Z", role="wash", width="0")
    plate.path("M 58 156 Q 180 96 302 156")
    plate.line(58, 156, 58, 292)
    plate.line(302, 156, 302, 292)
    plate.path("M 78 292 L 282 292 L 312 396 L 48 396 Z")
    plate.line(74, 176, 74, 292, width="1.1")
    plate.line(286, 176, 286, 292, width="1.1")
    if "heaven" in recipe["modifiers"]:
        plate.line(146, 246, 214, 246)
        plate.line(136, 268, 224, 268)
        plate.line(126, 290, 234, 290)
    if "heaven" in recipe["modifiers"]:
        plate.rect(152, 58, 56, 52, role="gold", width="1.25")
        plate.line(166, 110, 166, 156, role="gold", width="1.1")
        plate.line(194, 110, 194, 156, role="gold", width="1.1")
    if "death" in recipe["modifiers"]:
        plate.path("M 88 274 L 88 226 Q 106 204 124 226 L 124 274 Z")
        plate.line(106, 228, 106, 258)
        plate.line(96, 240, 116, 240)
    count = recipe["count"]
    for x in _spread(count, 72, 288):
        _figure(plate, x, 388, short=count >= 5, dancing="dance" in recipe["subjects"])


def _terrain(plate, recipe):
    subject = recipe["subjects"][0] if recipe["subjects"] else "forest"
    if subject == "ocean":
        plate.line(32, 150, 328, 150)
        for row in (
            "28,214 74,196 120,214 166,196 212,214 258,196 304,214 332,202",
            "24,268 84,248 144,268 204,248 264,268 332,250",
            "32,322 104,302 176,322 248,302 328,318",
            "40,376 124,356 208,376 292,356 332,372",
        ):
            plate.poly(row)
    elif subject == "garden":
        plate.line(36, 318, 324, 318, width="1.25")
        for x in (72, 128, 184, 240, 296):
            plate.line(x, 318, x, 262)
            plate.circle(x, 246, 16)
        plate.rect(146, 332, 68, 26)
    elif subject == "mountain":
        plate.path("M 32 368 L 108 156 L 164 268 L 228 124 L 328 368")
        plate.line(32, 368, 328, 368, width="1.25")
        plate.path("M 208 156 L 228 124 L 250 168", role="gold")
    elif subject == "river":
        plate.path("M 180 48 C 108 132 246 196 154 286 C 92 348 236 392 180 436", width="1.75")
        plate.path("M 48 132 C 132 164 86 226 156 246", width="1.1")
        plate.path("M 312 156 C 228 198 286 262 204 304", width="1.1")
    elif subject == "desert":
        plate.path("M 24 286 Q 110 228 190 286 T 336 274")
        plate.path("M 24 344 Q 130 298 220 344 T 336 332")
        plate.circle(246, 118, 18, role="gold")
    else:
        plate.line(36, 372, 324, 372, width="1.25")
        trees = ((68, 168), (118, 204), (168, 148), (218, 196), (268, 160), (312, 184))
        shift = recipe["detail"]
        ordered = trees[shift:] + trees[:shift]
        for x, height in ordered:
            plate.line(x, 372, x, 372 - height + 46)
            plate.path(f"M {x - 22} {372 - height + 58} L {x} {372 - height} L {x + 22} {372 - height + 58}")


def _shift(recipe, value):
    return 360 - value if recipe["mirror"] else value


def _abs_threshold(plate, recipe):
    plate.path("M 64 300 Q 180 248 296 300")
    plate.line(48, 338, 312, 338)
    plate.line(78, 358, 282, 358, width="1")
    x = _shift(recipe, 154)
    plate.path(f"M {x} 246 L {_shift(recipe, 180)} 108 L {_shift(recipe, 206)} 246 Z", role="gold", width="1.5")


def _abs_occlude(plate, recipe):
    plate.circle(_shift(recipe, 150), 214, 86)
    plate.rect(_shift(recipe, 196) - (28 if recipe["mirror"] else 0), 118, 28, 214, width="1.75")
    plate.rect(_shift(recipe, 214) - (70 if recipe["mirror"] else 0), 246, 70, 70, role="gold", width="1.5")


def _abs_density(plate, recipe):
    origin = 48 if not recipe["mirror"] else 188
    for index in range(10):
        plate.line(origin + index * 12, 92, origin + index * 12, 372, width="1")
    plate.circle(_shift(recipe, 268), 214, 46)
    plate.circle(_shift(recipe, 268), 214, 16, role="gold", width="1.25")


def _abs_frames(plate, recipe):
    plate.rect(62, 86, 168, 250)
    plate.rect(98, 128, 150, 196)
    plate.rect(132, 168, 132, 148)
    plate.circle(_shift(recipe, 262), 292, 30, role="gold", width="1.5")


def _abs_diagonal(plate, recipe):
    plate.path(f"M {_shift(recipe, 72)} 340 L {_shift(recipe, 118)} 292 L {_shift(recipe, 86)} 236 Z")
    plate.rect(_shift(recipe, 148) - (48 if recipe["mirror"] else 0), 188, 48, 48)
    plate.circle(_shift(recipe, 258), 122, 34, role="gold")


def _abs_bridge(plate, recipe):
    plate.circle(_shift(recipe, 86), 312, 30)
    plate.circle(_shift(recipe, 86), 252, 10, role="gold", width="1.25")
    plate.rect(_shift(recipe, 246) - (72 if recipe["mirror"] else 0), 112, 72, 92)
    plate.line(_shift(recipe, 116), 300, _shift(recipe, 246), 168, width="1.25")
    plate.line(_shift(recipe, 116), 324, _shift(recipe, 270), 196, width="1")


def _abs_radial(plate, recipe):
    cx, cy = _shift(recipe, 214), 196
    plate.circle(cx, cy, 20, role="gold", width="1.5")
    plate.circle(cx, cy, 72)
    for angle in (18, 58, 98, 138, 178, 218, 258, 298, 338):
        rad = math.radians(angle)
        plate.line(cx, cy, round(cx + math.cos(rad) * 112), round(cy + math.sin(rad) * 112), width="1.1")


def _abs_terrace(plate, recipe):
    plate.line(44, 132, 316, 132)
    plate.line(64, 196, 296, 196, width="1.5")
    plate.line(84, 260, 276, 260)
    plate.line(104, 324, 256, 324, width="1")
    plate.line(48, 388, 312, 388, width="1.25")
    x = _shift(recipe, 156)
    plate.path(f"M {x} 96 L {_shift(recipe, 180)} 220 L {_shift(recipe, 204)} 96 Z", role="gold", width="1.5")


def _abstract(plate, recipe):
    (
        _abs_threshold,
        _abs_occlude,
        _abs_density,
        _abs_frames,
        _abs_diagonal,
        _abs_bridge,
        _abs_radial,
        _abs_terrace,
    )[recipe["abstract_layout"]](plate, recipe)



def render_svg(recipe, structure=False):
    safe = _safe_recipe(recipe or {})
    plate = Plate()
    plate.rect(0, 0, 360, 480, role="bg", width="0")
    {
        "portal": _portal,
        "city": _city,
        "relation": _relation,
        "still": _still,
        "route": _route,
        "stage": _stage,
        "terrain": _terrain,
        "abstract": _abstract,
    }[safe["family"]](plate, safe)
    _frame(plate)
    palette = STRUCTURE if structure else PALETTES[safe["palette"]]
    body = []
    for role, markup in plate.marks:
        if structure and role == "wash":
            continue
        colored = markup.replace("@ink", palette["ink"]).replace("@gold", palette["gold"]).replace("@wash", palette["wash"]).replace("@bg", palette["bg"])
        body.append(colored)
    if structure:
        body.insert(0, '<rect x="0" y="0" width="360" height="480" fill="#ffffff" stroke="none"/>')
    inner = "\n  ".join(body)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="360" height="480" '
        'fill="none" stroke-linecap="round" stroke-linejoin="round">\n  '
        f"{inner}\n</svg>\n"
    )


def render_base():
    return render_svg({
        "family": "abstract",
        "subjects": [],
        "modifiers": [],
        "arrangement": "",
        "count": 0,
        "palette": 0,
        "mirror": False,
        "detail": 0,
        "abstract_layout": 1,
    })
