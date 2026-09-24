"""Build a self-contained GitHub Pages site without shipping runtime databases."""
# SPDX-License-Identifier: AGPL-3.0-only
import json
import shutil
from pathlib import Path

from catalog import BASE, load_catalog, read_json


def build(destination=None):
    output = Path(destination or BASE / '_site')
    (output / 'static').mkdir(parents=True, exist_ok=True)
    (output / 'data').mkdir(parents=True, exist_ok=True)
    # Explicitly use the checked-in snapshot, never a user's runtime catalogue or daily history.
    entries, updated = load_catalog(BASE / 'data' / '_nonexistent_build_runtime')
    articles = read_json(BASE / 'data' / 'articles.json', {}).get('articles', {})
    summaries = read_json(BASE / 'data' / 'summaries_zh.json', {})
    merged = []
    for entry in entries:
        article = articles.get(entry['id'], {})
        row = {**entry, **article}
        row['title_zh'] = article.get('title_zh') or entry.get('title_zh', '')
        if summaries.get(entry['title']):
            row.update(intro_zh=summaries[entry['title']], translator='bundled')
        if row.get('intro_zh') == row.get('intro_en'):
            row.pop('intro_zh', None)
        merged.append(row)
    data = {'updated_at': updated, 'license': 'Wikipedia text: CC BY-SA 4.0. Images: see image_source. Code: AGPL-3.0-only.', 'musicals': merged}
    (output / 'data' / 'site-catalog.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    html = (BASE / 'templates' / 'index.html').read_text(encoding='utf-8-sig')
    html = html.replace('href="/static/', 'href="./static/').replace('src="/static/', 'src="./static/')
    html = html.replace('<script src="./static/app.js">', '<script src="./static/static-api.js"></script>\n  <script src="./static/app.js">')
    html = html.replace('今日结果为你保留。再抽一部，自由探索。', '今日结果保存在此浏览器。再抽一部，自由探索。')
    html = html.replace('两种抽取各自不放回，抽完整个片库后重新开始。', '两种抽取各自不放回。清除网站数据会重置记录。')
    html = html.replace('>更新片库</button>', '>检查片库更新</button>')
    html = html.replace('片库可离线抽取；首次查看的简介和图片需要联网。', '首次访问下载片库；再次打开使用浏览器缓存。图片需要联网。')
    (output / 'index.html').write_text(html, encoding='utf-8')
    for name in ('app.js', 'static-api.js', 'style.css'):
        shutil.copyfile(BASE / 'static' / name, output / 'static' / name)
    shutil.copyfile(BASE / 'LICENSE', output / 'LICENSE')
    (output / '.nojekyll').write_text('', encoding='utf-8')
    print(f'Built {len(merged)} musicals into {output}')
    return output


if __name__ == '__main__':
    build()
