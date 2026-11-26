"""Build a self-contained GitHub Pages site without shipping runtime databases."""
# SPDX-License-Identifier: AGPL-3.0-only
import json
import shutil
import time
from pathlib import Path

from artwork.generate import annotate_display, generate_library
from artwork.normalize import merge_publication
from catalog import BASE, load_catalog, read_json
from sharing import PUBLIC_BASE, ensure_card, public_url, work_html, work_key


def build(destination=None):
    started = time.perf_counter()
    output = Path(destination or BASE / "_site")
    (output / "static").mkdir(parents=True, exist_ok=True)
    (output / "data").mkdir(parents=True, exist_ok=True)
    # Explicitly use the checked-in snapshot, never a user's runtime catalogue or daily history.
    entries, updated = load_catalog(BASE / "data" / "_nonexistent_build_runtime")
    articles = read_json(BASE / "data" / "articles.json", {}).get("articles", {})
    summaries = read_json(BASE / "data" / "summaries_zh.json", {})
    merged = [merge_publication(entry, articles.get(entry["id"]), summaries.get(entry["title"], "")) for entry in entries]
    artwork_dir = output / "static" / "artwork"
    manifest = generate_library(merged, artwork_dir, "./static/artwork/")
    for row in merged:
        item = manifest["items"].get(row["id"], {})
        name = item.get("filename") or "base.svg"
        digest = (item.get("source_digest") or "0")[:8]
        version = item.get("art_version") or "1"
        artwork = {
            "artwork_url": f"./static/artwork/{name}?v={version}-{digest}",
            "artwork_kind": item.get("kind") or "fallback",
            "artwork_family": item.get("family") or "abstract",
            "artwork_basis": item.get("basis") or [],
            "artwork_reason": item.get("reason"),
        }
        row.update(annotate_display(row, artwork))
    data = {
        "updated_at": updated,
        "art_version": manifest.get("art_version"),
        "license": "Wikipedia text: CC BY-SA 4.0. Remote images: see image_source. Original plates: program output, AGPL-3.0-only. Code: AGPL-3.0-only.",
        "musicals": merged,
    }
    (output / "data" / "site-catalog.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    html = (BASE / "templates" / "index.html").read_text(encoding="utf-8-sig")
    html = html.replace('href="/static/', 'href="./static/').replace('src="/static/', 'src="./static/')
    html = html.replace(
        '<script src="./static/app.js">',
        '<script src="./static/static-api.js"></script>\n  <script src="./static/app.js">',
    )
    html = html.replace(">更新片库</button>", ">检查片库更新</button>")
    (output / "index.html").write_text(html, encoding="utf-8")
    for name in ("app.js", "static-api.js", "style.css", "sharing.js"):
        shutil.copyfile(BASE / "static" / name, output / "static" / name)
    works = output / 'works'
    works.mkdir(exist_ok=True)
    share_dir = output / 'static' / 'share'
    index = {}
    for row in merged:
        svg_name = manifest['items'][row['id']]['filename']
        name = ensure_card(row, (artwork_dir / svg_name).read_text(encoding='utf-8'), share_dir)
        info = {'url': public_url(row['id']), 'image': './static/share/' + name, 'available': True}
        index[row['id']] = info
        page = work_html(html, {**row, 'total': len(merged)}, PUBLIC_BASE + 'static/share/' + name, static=True)
        (works / (work_key(row['id']) + '.html')).write_text(page, encoding='utf-8')
    active = {work_key(row['id']) + '.html' for row in merged}
    for stale in works.glob('*.html'):
        if stale.name not in active:
            stale.write_text(work_html(html, static=True), encoding='utf-8')
    (output / '404.html').write_text(work_html(html, static=True, home='/musical-spinningtop/'), encoding='utf-8')
    (output / 'data' / 'share-index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    shutil.copyfile(BASE / "LICENSE", output / "LICENSE")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    report = {'seconds': round(time.perf_counter() - started, 3), 'works': len(merged),
              'share_pngs': len(list(share_dir.glob('*.png'))),
              'share_bytes': sum(path.stat().st_size for path in share_dir.glob('*.png')),
              'site_bytes': sum(path.stat().st_size for path in output.rglob('*') if path.is_file())}
    (output / 'build-metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return output


if __name__ == "__main__":
    build()
