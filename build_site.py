"""Build a self-contained static mount without shipping runtime databases."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
import json
import re
import shutil
import time
from pathlib import Path

from artwork.generate import annotate_display, generate_library
from artwork.normalize import merge_publication
from catalog import BASE, load_catalog, read_json
from sharing import ensure_card, public_url, work_html, work_key
from deployment import TARGETS, get_deployment, home_metadata, page_shell
from build_contract import source_identity, validate_output, write_manifest
from artwork.generate import _file_lock


def _build(destination, deployment, source_sha, source_dirty):
    started = time.perf_counter()
    output = Path(destination)
    paths = deployment.frontend()
    validate_output(output)
    (output / "static").mkdir(parents=True, exist_ok=True)
    (output / "data").mkdir(parents=True, exist_ok=True)
    # Explicitly use the checked-in snapshot, never a user's runtime catalogue or daily history.
    entries, updated = load_catalog(BASE / "data" / "_nonexistent_build_runtime")
    articles = read_json(BASE / "data" / "articles.json", {}).get("articles", {})
    summaries = read_json(BASE / "data" / "summaries_zh.json", {})
    merged = [merge_publication(entry, articles.get(entry["id"]), summaries.get(entry["title"], "")) for entry in entries]
    artwork_dir = output / "static" / "artwork"
    manifest = generate_library(merged, artwork_dir, paths['artwork_path'])
    for row in merged:
        item = manifest["items"].get(row["id"], {})
        name = item.get("filename") or "base.svg"
        digest = (item.get("source_digest") or "0")[:8]
        version = item.get("art_version") or "1"
        artwork = {
            "artwork_url": f"{paths['artwork_path']}{name}?v={version}-{digest}",
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
    html = html.replace(">更新片库</button>", ">检查片库更新</button>")
    (output / "index.html").write_text(page_shell(html, deployment, static=True).replace('<!-- SHARE_HEAD -->', home_metadata(deployment)), encoding="utf-8")
    (output / "deployment.json").write_text(json.dumps(deployment.frontend(), indent=2), encoding="utf-8")
    for name in ("app.js", "static-api.js", "style.css", "sharing.js", "deployment.js"):
        shutil.copyfile(BASE / "static" / name, output / "static" / name)
    works = output / 'works'
    works.mkdir(exist_ok=True)
    share_dir = output / 'static' / 'share'
    index = {}
    for row in merged:
        svg_name = manifest['items'][row['id']]['filename']
        name = ensure_card(row, (artwork_dir / svg_name).read_text(encoding='utf-8'), share_dir)
        info = {'url': public_url(row['id'], deployment), 'image': paths['local_card_path'] + name, 'available': True}
        index[row['id']] = info
        page = work_html(html, {**row, 'total': len(merged)}, deployment.public_base + 'static/share/' + name, static=True, deployment=deployment)
        (works / (work_key(row['id']) + '.html')).write_text(page, encoding='utf-8')
    active = {work_key(row['id']) + '.html' for row in merged}
    for stale in works.glob('*.html'):
        if stale.name not in active:
            stale.write_text(work_html(html, static=True, deployment=deployment), encoding='utf-8')
    (output / '404.html').write_text(work_html(html, static=True, deployment=deployment), encoding='utf-8')
    (output / 'data' / 'share-index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    shutil.copyfile(BASE / "LICENSE", output / "LICENSE")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    report = {'seconds': round(time.perf_counter() - started, 3), 'works': len(merged),
              'share_pngs': len(list(share_dir.glob('*.png'))),
              'share_bytes': sum(path.stat().st_size for path in share_dir.glob('*.png')),
              'site_bytes': sum(path.stat().st_size for path in output.rglob('*') if path.is_file())}
    (output / 'build-metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    write_manifest(output, deployment, updated, source_sha, source_dirty)
    return output


def build(destination=None, target='github', source_sha=None):
    deployment = get_deployment(target)
    output = Path(destination or BASE / '_site').absolute()
    validate_output(output)
    observed_sha, dirty = source_identity(BASE)
    if source_sha is not None:
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha):
            raise ValueError('source SHA must be a full lowercase 40-character commit SHA')
        if observed_sha and observed_sha != source_sha:
            raise ValueError('source SHA does not match checkout')
    else:
        source_sha = observed_sha
    if source_sha is None:
        raise ValueError('Source export requires --source-sha from the pinned upstream version')
    # Serialize builds to the same output; the lock is outside the mount artifact.
    with _file_lock(output.parent / ('.' + output.name + '.build.lock')):
        return _build(output, deployment, source_sha, dirty)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=tuple(TARGETS), default='github')
    parser.add_argument('--output', type=Path, help='Output directory; its contents mount at the configured BASE_PATH')
    parser.add_argument('--source-sha', help='Pinned upstream SHA, required for source archives without Git')
    args = parser.parse_args()
    build(args.output, args.target, args.source_sha)
