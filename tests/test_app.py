import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app import Library, Store, create_app, fetch_details
from catalog import BASE, category_members, discover, load_catalog, read_json
from artwork.generate import plan_artwork
from artwork.normalize import merge_publication


class DrawTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(self.temporary.name)
        self.entries = [{'id': str(i), 'title': f'Show {i}', 'wiki': f'Show {i}', 'wiki_url': f'https://en.wikipedia.org/wiki/Show_{i}'} for i in range(12)]

    def test_all_candidates_reachable_and_no_repeat_before_exhaustion(self):
        candidates = []
        def choose(pool):
            candidates.append({row['id'] for row in pool})
            return pool[-1]
        with patch('app.secrets.choice', side_effect=choose):
            drawn = [self.store.pick(self.entries)['id'] for _ in self.entries]
        self.assertEqual(len(set(drawn)), len(self.entries))
        self.assertEqual(candidates[0], {row['id'] for row in self.entries})
        self.assertEqual([len(pool) for pool in candidates], list(range(12, 0, -1)))
        self.assertNotEqual(self.store.pick(self.entries)['id'], drawn[-1])

    def test_daily_survives_restart_catalog_change_and_random_draws(self):
        first = self.store.pick(self.entries, '2026-09-25')
        for _ in range(20):
            self.store.pick(self.entries)
        restarted = Store(self.temporary.name)
        changed = [{'id': 'new', 'title': 'New'}]
        self.assertEqual(first, restarted.pick(changed, '2026-09-25'))

    def test_concurrent_daily_open_only_consumes_one_draw(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            picked = list(pool.map(lambda _: self.store.pick(self.entries, '2026-09-25'), range(24)))
        self.assertEqual(len({item['id'] for item in picked}), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM seen WHERE kind='daily'").fetchone()[0], 1)

    def test_daily_cycle_and_single_entry(self):
        picked = [self.store.pick(self.entries, (date(2026, 1, 1) + timedelta(days=i)).isoformat()) for i in range(12)]
        self.assertEqual(len({row['id'] for row in picked}), 12)
        self.assertEqual(self.store.pick(self.entries[:1])['id'], '0')
        self.assertEqual(self.store.pick(self.entries[:1])['id'], '0')

    def test_new_catalog_entries_join_pool(self):
        for _ in self.entries:
            self.store.pick(self.entries)
        self.assertEqual(self.store.pick(self.entries + [{'id': 'new'}])['id'], 'new')


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = create_app(self.temporary.name, background=False)
        self.library = self.app.extensions['library']
        self.addCleanup(self.library.pool.shutdown)
        self.client = self.app.test_client()

    def test_cold_start_draw_is_offline_and_stable(self):
        with patch('app.wiki_query', side_effect=AssertionError('Network must not block drawing')):
            a = self.client.get('/api/musical').get_json()
            b = self.client.get('/api/musical').get_json()
            self.assertEqual(a['id'], b['id'])
            self.assertGreater(a['total'], 2000)
            self.assertEqual(a['date'], date.today().isoformat())
            self.assertEqual(self.client.get('/api/catalog').get_json()['today'], a['date'])

    def test_random_does_not_change_today(self):
        today = self.client.get('/api/musical').get_json()
        random = [self.client.post('/api/random').get_json() for _ in range(20)]
        self.assertEqual(len({row['id'] for row in random}), 20)
        self.assertTrue(all(row['mode'] == 'random' and row['date'] is None for row in random))
        self.assertEqual(today['id'], self.client.get('/api/musical').get_json()['id'])
        self.assertEqual(self.client.get('/api/random').status_code, 405)

    def test_invalid_date_and_unknown_details(self):
        for query in ['offset=no', 'offset=99999999999999999', 'date=2026-02-30', 'date=0001-01-01']:
            self.assertEqual(self.client.get('/api/musical?' + query).status_code, 400)
        self.assertEqual(self.client.get('/api/details?id=no-such-show').status_code, 404)

    def test_details_survive_offline(self):
        row = self.library.entries[0]
        self.app.extensions['store'].save_details(row['id'], {'intro_zh': 'Cached introduction', 'detail_status': 'ready'})
        result = self.client.get('/api/details', query_string={'id': row['id']}).get_json()
        self.assertEqual(result['intro_zh'], 'Cached introduction')
        self.assertEqual(result['detail_status'], 'ready')

    def test_old_english_cache_merges_later_bundled_summary_before_artwork(self):
        row = self.library.entries[0]
        cached = {'intro_en': 'A note about the company.', 'intro_zh': '', 'translator': 'none', 'detail_status': 'ready'}
        self.app.extensions['store'].save_details(row['id'], cached)
        summary = '两位姐妹重逢。'
        real = read_json

        def routed(path, default=None):
            if str(path).endswith('summaries_zh.json'):
                return {row['title']: summary}
            return real(path, default)

        with patch('app.read_json', side_effect=routed):
            shown = self.client.get('/api/details', query_string={'id': row['id']}).get_json()
        self.assertEqual(shown['intro_zh'], summary)
        self.assertEqual(shown['translator'], 'bundled')
        planned = plan_artwork(merge_publication(row, cached, summary))
        self.assertEqual(shown['artwork_family'], planned['family'])
        self.assertIn(planned['filename'], shown['artwork_url'])
        before = (Path(self.temporary.name) / 'artwork' / planned['filename']).read_bytes()

        def changed(path, default=None):
            if str(path).endswith('summaries_zh.json'):
                return {row['title']: '一封信件藏在门后。'}
            return real(path, default)

        with patch('app.read_json', side_effect=changed):
            later = self.client.get('/api/details', query_string={'id': row['id']}).get_json()
        self.assertNotEqual(later['artwork_url'].split('?', 1)[0], shown['artwork_url'].split('?', 1)[0])
        self.assertEqual((Path(self.temporary.name) / 'artwork' / planned['filename']).read_bytes(), before)

    def test_empty_library_returns_useful_error(self):
        self.library.entries = []
        self.assertEqual(self.client.get('/api/musical').status_code, 503)
        self.assertEqual(self.client.post('/api/random').status_code, 503)

    def test_failed_refresh_keeps_catalogue(self):
        import threading
        original = self.library.entries
        def fail(progress):
            raise RuntimeError('offline')
        real_thread = threading.Thread
        threads = []
        def thread(*args, **kwargs):
            worker = real_thread(*args, **kwargs)
            threads.append(worker)
            return worker
        with patch('app.discover', side_effect=fail), patch('app.threading.Thread', side_effect=thread), self.assertLogs('app', level='ERROR'):
            self.assertTrue(self.library.refresh())
            threads[0].join(5)
        self.assertIs(self.library.entries, original)
        self.assertFalse(self.library.status()['sync']['running'])
        self.assertTrue(self.library.status()['sync']['error'])
        self.assertFalse((Path(self.temporary.name) / 'catalog.json').exists())

    def test_first_offline_failure_preserves_bundled_abstract(self):
        row = next(row for row in self.library.entries
                   if self.library.bundled_details.get(row['id'], {}).get('intro_en'))
        with patch('app.fetch_details', side_effect=RuntimeError('offline')):
            self.library._detail_job(row)
        result = self.library.detail(row)
        self.assertTrue(result['intro_en'])
        self.assertEqual(result['detail_status'], 'offline')

    def test_removed_catalog_entry_still_has_daily_details(self):
        selected = self.client.get('/api/musical').get_json()
        self.library.entries = [row for row in self.library.entries if row['id'] != selected['id']]
        self.assertEqual(self.client.get('/api/details', query_string={'id': selected['id']}).status_code, 200)

    def test_daily_archive_roundtrip_after_restart_and_removal(self):
        row = {'id': 'archive:1', 'title': 'Archive Show', 'wiki_url': 'https://en.wikipedia.org/wiki/Archive', 'year': 1961}
        self.library.entries = [row]
        self.app.extensions['store'].save_details(row['id'], {
            'intro_en': 'Two sisters reunite.', 'intro_zh': '两位姐妹重逢。',
            'intro_source': row['wiki_url'], 'translator': 'wikipedia_zh', 'detail_status': 'ready',
            'image': 'https://example.test/old.png', 'image_reuse': 'verified',
        })
        original = self.client.get('/api/musical?date=2031-05-05').get_json()
        self.assertTrue(original['intro_en'])
        store = self.app.extensions['store']
        with store.connect() as db:
            seen = db.execute('SELECT * FROM seen').fetchall()
            archived = json.loads(db.execute('SELECT musical FROM daily').fetchone()[0])
            self.assertEqual(archived['intro_en'], original['intro_en'])
        restarted = create_app(self.temporary.name, background=False)
        self.addCleanup(restarted.extensions['library'].pool.shutdown)
        restarted.extensions['library'].entries = [{'id': 'other', 'title': 'Other'}]
        with store.connect() as db:
            db.execute('DELETE FROM details')
        with patch.object(restarted.extensions['library'], 'detail', side_effect=AssertionError('removed detail fetch')):
            client = restarted.test_client()
            for endpoint in ('/api/musical?date=2031-05-05', '/api/details?id=archive:1'):
                removed = client.get(endpoint).get_json()
                for key in ('id', 'title', 'intro_en', 'intro_zh', 'intro_source', 'wiki_url', 'year'):
                    self.assertEqual(removed[key], original[key], key)
                self.assertTrue(removed['removed'])
                self.assertEqual(removed['detail_status'], 'ready')
                self.assertEqual(removed['artwork_reason'], 'removed')
                self.assertEqual(removed['artwork_url'], '/artwork/base.svg')
                self.assertIsNone(removed['display_image'])
                self.assertIsNone(removed['image'])
        with store.connect() as db:
            self.assertEqual(db.execute('SELECT * FROM seen').fetchall(), seen)

    def test_id_only_archive_is_enriched_before_removal(self):
        row = {'id': 'archive:2', 'title': 'Entry Summary', 'intro_en': 'A letter behind a door.',
               'intro_source': 'https://en.wikipedia.org/wiki/Entry', 'wiki_url': 'https://en.wikipedia.org/wiki/Entry'}
        self.library.entries = [row]
        store = self.app.extensions['store']
        with store.connect() as db:
            db.execute('INSERT INTO daily VALUES (?, ?)', ('2031-05-06', json.dumps({'id': row['id'], 'v': 2})))
        shown = self.client.get('/api/musical?date=2031-05-06').get_json()
        self.assertEqual(shown['intro_en'], row['intro_en'])
        self.library.entries = [{'id': 'other', 'title': 'Other'}]
        removed = self.client.get('/api/details?id=archive:2').get_json()
        self.assertEqual(removed['intro_en'], row['intro_en'])
        self.assertEqual(removed['title'], row['title'])
        self.assertEqual(removed['intro_source'], row['intro_source'])
        self.assertTrue(removed['removed'])
        self.assertEqual(removed['artwork_url'], '/artwork/base.svg')



    def test_saved_daily_uses_latest_fields_without_redrawing(self):
        selected = self.client.get("/api/musical?date=2020-01-02").get_json()
        store = self.app.extensions["store"]
        frozen = {**selected, "title": "Frozen Old Title"}
        with store.connect() as db:
            db.execute("UPDATE daily SET musical=? WHERE day=?", (json.dumps(frozen), "2020-01-02"))
        latest = self.client.get("/api/musical?date=2020-01-02").get_json()
        self.assertEqual(latest["id"], selected["id"])
        self.assertNotEqual(latest["title"], "Frozen Old Title")
        self.assertTrue(latest["artwork_url"].startswith("/artwork/"))
        self.assertIsNone(latest["display_image"])
        self.assertNotEqual(latest.get("artwork_kind"), None)
        with store.connect() as db:
            raw = json.loads(db.execute("SELECT musical FROM daily WHERE day=?", ("2020-01-02",)).fetchone()[0])
        self.assertEqual(raw["title"], "Frozen Old Title")
        self.library.entries = [row for row in self.library.entries if row["id"] != selected["id"]]
        removed = self.client.get("/api/musical?date=2020-01-02").get_json()
        self.assertEqual(removed["id"], selected["id"])
        self.assertEqual(removed["title"], "Frozen Old Title")
        name = latest["artwork_url"].split("?", 1)[0].rsplit("/", 1)[-1]
        image = self.client.get("/artwork/" + name)
        self.assertEqual(image.status_code, 200)
        self.assertIn("image/svg+xml", image.content_type)
        image.close()
        self.assertEqual(self.client.get("/artwork/../app.py").status_code, 404)
        self.assertEqual(self.client.get("/artwork/not-safe.svg").status_code, 404)

class SourceTests(unittest.TestCase):
    def test_category_continuation_including_empty_page(self):
        pages = [
            {'query': {'categorymembers': []}, 'continue': {'continue': '-||', 'cmcontinue': 'next'}},
            {'query': {'categorymembers': [{'pageid': 1, 'title': 'A', 'ns': 0}]}},
        ]
        with patch('catalog.wiki_query', side_effect=pages) as query:
            self.assertEqual(len(list(category_members('Category:2026 musicals', 'page'))), 1)
            self.assertEqual(query.call_args.args[0]['cmcontinue'], 'next')

    def test_discovery_excludes_films_and_deduplicates_page_ids(self):
        visited = []
        def members(category, kind):
            visited.append(category)
            if kind == 'subcat':
                return [{'title': 'Category:Musical films by year'}, {'title': 'Category:2025 musicals'}, {'title': 'Category:2026 musicals'}]
            return [{'title': f'Show {i} (musical)', 'pageid': i, 'ns': 0} for i in range(600)]
        with patch('catalog.category_members', side_effect=members):
            snapshot = discover()
        self.assertEqual(len(snapshot['musicals']), 600)
        self.assertTrue(all(row['year'] == 2025 for row in snapshot['musicals']))
        self.assertNotIn('Category:Musical films by year', visited)

    def test_bundled_catalog_has_unique_verified_sources(self):
        rows = read_json(BASE / 'data' / 'catalog.json', {})['musicals']
        self.assertGreater(len(rows), 2000)
        self.assertEqual(len(rows), len({row['id'] for row in rows}))
        self.assertTrue(all(row['wiki_url'].startswith('https://en.wikipedia.org/wiki/') for row in rows))
        excluded = read_json(BASE / 'data' / 'exclusions.json', {})
        self.assertFalse(any(row['wiki'] in excluded for row in rows))

    def test_corrupt_runtime_catalog_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'catalog.json').write_text('{broken', encoding='utf-8')
            entries, _ = load_catalog(directory)
            self.assertGreater(len(entries), 2000)

    def test_native_chinese_and_english_fallback(self):
        en = {'query': {'pages': [{'title': 'A', 'extract': 'English', 'langlinks': [{'lang': 'zh', 'title': '中文'}], 'fullurl': 'https://en.wikipedia.org/wiki/A'}]}}
        zh = {'query': {'pages': [{'title': '中文', 'extract': '中文简介', 'fullurl': 'https://zh.wikipedia.org/wiki/中文'}]}}
        entry = {'title': 'A', 'wiki': 'A', 'wiki_url': 'https://en.wikipedia.org/wiki/A'}
        with patch('app.wiki_query', side_effect=[en, zh]):
            self.assertEqual(fetch_details(entry)['intro_zh'], '中文简介')
        with patch('app.wiki_query', side_effect=[en, RuntimeError('offline')]):
            result = fetch_details(entry)
            self.assertEqual(result['intro_zh'], 'English')
            self.assertEqual(result['translator'], 'none')


if __name__ == '__main__':
    unittest.main()
