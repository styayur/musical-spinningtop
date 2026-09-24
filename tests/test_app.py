import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app import Library, Store, create_app, fetch_details
from catalog import BASE, category_members, discover, load_catalog, read_json


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
