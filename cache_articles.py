"""Build an optional, source-attributed offline introduction snapshot in batches."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from catalog import BASE, read_json, wiki_query, wiki_url, write_json


def batch_articles(entries):
    data = wiki_query({'action': 'query', 'pageids': '|'.join(str(row['pageid']) for row in entries),
                       'prop': 'extracts|pageimages|info|langlinks', 'exintro': 1, 'explaintext': 1,
                       'exchars': 1200, 'exlimit': 20, 'piprop': 'thumbnail|name',
                       'pithumbsize': 1000, 'inprop': 'url', 'lllang': 'zh', 'lllimit': 500})
    result = {}
    for page in data.get('query', {}).get('pages', []):
        if page.get('missing') or page.get('ns') != 0:
            continue
        extract = page.get('extract', '').strip()
        result[f"en:{page['pageid']}"] = {
            'intro_en': extract, 'intro_zh': extract, 'translator': 'none',
            'title_zh': next(iter(page.get('langlinks', [])), {}).get('title', ''),
            'wiki_url': page['fullurl'], 'intro_source': page['fullurl'],
            'image': page.get('thumbnail', {}).get('source'),
            'image_source': wiki_url('File:' + page['pageimage']) if page.get('pageimage') else None,
            'detail_status': 'ready',
        }
    return result


def main():
    entries = read_json(BASE / 'data' / 'catalog.json', {})['musicals']
    batches = [entries[start:start + 20] for start in range(0, len(entries), 20)]
    articles = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for done, future in enumerate(as_completed([pool.submit(batch_articles, batch) for batch in batches]), 1):
            articles.update(future.result())
            print(f'Articles {done}/{len(batches)}', flush=True)
    write_json(BASE / 'data' / 'articles.json', {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'license': 'Text: CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/ ; shortened Wikipedia introductions. Images retain their individual licenses; see image_source.',
        'articles': articles,
    })
    print(f'Saved {len(articles)} article summaries')


if __name__ == '__main__':
    main()
