"""
Spinning Top - 每日音乐剧 (A Musical a Day)
===========================================

一个每天为你"推送"一部音乐剧的小应用：

* 打开 `python app.py`（或双击 `run.bat`），浏览器会自动打开页面；
* 卡片正面是一张经典剧照 + 可向下滚动的官方简介（Wikipedia 实时抓取，
  并通过 deep-translator 免费翻译成中文）；
* 左键单击卡片会 3D 翻转，露出"官网"与"Fever 演出信息"链接。

用法：
    python app.py [端口]            # 默认 5000
    python app.py 5000 --no-browser # 不自动打开浏览器

环境变量：
    PORT        监听的端口
    NO_BROWSER  设为 1 时不自动打开浏览器
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MUSICALS_FILE = DATA_DIR / "musicals.json"
SUMMARIES_ZH_FILE = DATA_DIR / "summaries_zh.json"
TRANSLATIONS_FILE = DATA_DIR / "translations.json"

USER_AGENT = "DailyMusical/1.0 (https://github.com/styayur)"
WIKI_API = "https://en.wikipedia.org/w/api.php"

app = Flask(__name__)


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_musicals():
    return load_json(MUSICALS_FILE, [])


def today_musical(offset: int = 0):
    """按日期（日序数）从片单里选一部，offset 可用来预览其它天。"""
    musicals = load_musicals()
    if not musicals:
        return None, None, None
    d = date.today() + timedelta(days=int(offset or 0))
    idx = d.toordinal() % len(musicals)
    return musicals[idx], d, idx


# --------------------------------------------------------------------------- #
# Wikipedia 动态抓取
# --------------------------------------------------------------------------- #
def fetch_wikipedia(title: str):
    """抓取条目首段简介、题图（剧照/海报）与条目链接。"""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|pageimages|info",
        "exintro": "1",
        "explaintext": "1",
        "piprop": "thumbnail|name",
        "pithumbsize": "1200",
        "inprop": "url",
        "redirects": "1",
        "format": "json",
    }
    try:
        r = requests.get(WIKI_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
    except Exception:
        return None
    if "missing" in page:
        return None
    return {
        "title": page.get("title", title),
        "extract": (page.get("extract") or "").strip(),
        "image": (page.get("thumbnail") or {}).get("source"),
        "page_image": page.get("pageimage"),
        "wiki_url": page.get("fullurl"),
    }


def fetch_gallery(title: str, exclude_file=None, limit: int = 6):
    """抓取条目里的若干张剧照/海报，用于正面图集。"""
    try:
        r = requests.get(WIKI_API, params={
            "action": "query", "titles": title, "prop": "images",
            "imlimit": "60", "redirects": "1", "format": "json",
        }, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})

        files = []
        for img in page.get("images", []):
            name = img["title"]
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            if exclude_file and name == f"File:{exclude_file}":
                continue
            files.append(name)
        files = files[:limit]
        if not files:
            return []

        r2 = requests.get(WIKI_API, params={
            "action": "query", "titles": "|".join(files), "prop": "imageinfo",
            "iiprop": "url", "iiurlwidth": "640", "format": "json",
        }, headers={"User-Agent": USER_AGENT}, timeout=30)
        r2.raise_for_status()

        urls = []
        for p in r2.json().get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("thumburl") or ii.get("url")
            if url:
                urls.append(url)
        return urls
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# 免费翻译（deep-translator）
# --------------------------------------------------------------------------- #
def translate_via_deep(text: str, target: str = "zh-CN"):
    """依次尝试 Google、MyMemory 两个免费后端，失败则返回 (None, None)。"""
    if not text:
        return None, None
    try:
        from deep_translator import GoogleTranslator, MyMemoryTranslator
    except Exception:
        return None, None

    # 1) Google 翻译（免费、无需 API key）
    try:
        out = GoogleTranslator(source="en", target=target).translate(text)
        if out and out.strip() and out.strip() != text.strip():
            return out.strip(), "google"
    except Exception:
        pass

    # 2) MyMemory 翻译（免费备用）
    try:
        out = MyMemoryTranslator(source="en-US", target=target).translate(text)
        if out and out.strip() and out.strip() != text.strip():
            return out.strip(), "mymemory"
    except Exception:
        pass

    return None, None


def build_fever_url(query: str) -> str:
    """Fever 没有稳定的公开搜索 URL，这里用 Google 站内搜索直达 Fever 演出页。"""
    return "https://www.google.com/search?q=" + quote_plus(f"{query} site:feverup.com")


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/musical")
def api_musical():
    offset = request.args.get("offset", default=0, type=int)
    force = request.args.get("refresh") in ("1", "true", "yes")
    musical, d, idx = today_musical(offset)
    if musical is None:
        return jsonify({"error": "片单为空，请检查 data/musicals.json"}), 500

    wiki_title = musical.get("wiki") or musical["title"]
    data = fetch_wikipedia(wiki_title) or {}

    extract = data.get("extract", "")
    image = data.get("image")
    wiki_url = data.get("wiki_url")

    # --- 简介：优先缓存，其次实时翻译，最后用内置中文摘要兜底 ---
    cache = load_json(TRANSLATIONS_FILE, {})
    cached = cache.get(wiki_title)

    zh = None
    translator = None
    if cached and cached.get("zh") and not force:
        zh = cached["zh"]
        translator = cached.get("translator", "cache")

    if not zh:
        bundled_zh = load_json(SUMMARIES_ZH_FILE, {}).get(musical["title"])
        if extract:
            zh, translator = translate_via_deep(extract)
        if zh:
            cache[wiki_title] = {"zh": zh, "translator": translator, "ts": int(time.time())}
            save_json(TRANSLATIONS_FILE, cache)
        else:
            zh = bundled_zh or extract
            translator = "bundled" if bundled_zh else "none"

    gallery = fetch_gallery(wiki_title, exclude_file=data.get("page_image")) if data else []

    # 若条目没有题图（如海报是拼图/未被标记），用图集第一张作为封面
    if not image and gallery:
        image = gallery.pop(0)

    payload = {
        "title": musical["title"],
        "title_zh": musical.get("title_zh", ""),
        "year": musical.get("year"),
        "composer": musical.get("composer", ""),
        "image": image,
        "gallery": gallery,
        "intro_zh": zh,
        "intro_en": extract,
        "translator": translator or "none",
        "official_url": musical.get("official_url"),
        "fever_url": build_fever_url(musical.get("fever_query") or musical["title"]),
        "wiki_url": wiki_url,
        "date": d.isoformat(),
        "index": idx,
        "total": len(load_musicals()),
    }
    return jsonify(payload)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def _open_browser(port: int) -> None:
    time.sleep(1.4)
    try:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    except Exception:
        pass


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(args[0]) if args else int(os.environ.get("PORT", "5000"))
    no_browser = "--no-browser" in sys.argv or os.environ.get("NO_BROWSER") in ("1", "true")

    if not no_browser:
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    print(f"* Spinning Top 每日音乐剧：http://127.0.0.1:{port}/")
    print("  按 Ctrl+C 退出。")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()