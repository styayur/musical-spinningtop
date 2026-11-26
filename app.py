"""Spinning Top: persistent daily discovery from a source-backed musical catalogue."""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask, abort, jsonify, render_template, request, send_file

from artwork.generate import annotate_display, ensure_artwork, ensure_base, resolve_artwork_path
from artwork.normalize import merge_publication
from catalog import BASE, discover, load_catalog, read_json, wiki_query, wiki_url, write_json

LOG = logging.getLogger(__name__)
ARCHIVE_FIELDS = ('title', 'title_zh', 'intro_en', 'intro_zh', 'intro_source', 'wiki_url', 'year', 'translator')


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'spinningtop.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS daily(day TEXT PRIMARY KEY, musical TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS seen(kind TEXT, id TEXT, PRIMARY KEY(kind, id));
                CREATE TABLE IF NOT EXISTS last_pick(kind TEXT PRIMARY KEY, id TEXT);
                CREATE TABLE IF NOT EXISTS details(id TEXT PRIMARY KEY, payload TEXT, fetched REAL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def pick(self, entries, day=None):
        kind = 'daily' if day else 'random'
        with self.connect() as db:
            # Serialize read + choose + write across threads AND processes.
            db.execute('BEGIN IMMEDIATE')
            if day:
                row = db.execute('SELECT musical FROM daily WHERE day=?', (day,)).fetchone()
                if row:
                    return json.loads(row[0])
            used = {row[0] for row in db.execute('SELECT id FROM seen WHERE kind=?', (kind,))}
            pool = [entry for entry in entries if entry['id'] not in used]
            if not pool:
                db.execute('DELETE FROM seen WHERE kind=?', (kind,))
                last = db.execute('SELECT id FROM last_pick WHERE kind=?', (kind,)).fetchone()
                pool = [entry for entry in entries if not last or entry['id'] != last[0]] or entries
            chosen = secrets.choice(pool)
            db.execute('INSERT INTO seen VALUES (?, ?)', (kind, chosen['id']))
            db.execute('INSERT OR REPLACE INTO last_pick VALUES (?, ?)', (kind, chosen['id']))
            if day:
                db.execute('INSERT INTO daily VALUES (?, ?)', (day, json.dumps(chosen, ensure_ascii=False)))
            return chosen

    def cached_details(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT payload, fetched FROM details WHERE id=?', (identity,)).fetchone()
        return (json.loads(row[0]), row[1]) if row else ({}, 0)

    def archive_daily(self, payload, day=None):
        """Fill missing saved text without replacing the original archive or draw."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT day, musical FROM daily WHERE day=?', (day,)).fetchall() if day else db.execute('SELECT day, musical FROM daily').fetchall()
            for saved_day, encoded in rows:
                saved = json.loads(encoded)
                if saved.get('id') != payload.get('id'):
                    continue
                for key in ARCHIVE_FIELDS:
                    if not saved.get(key) and payload.get(key):
                        saved[key] = payload[key]
                updated = json.dumps(saved, ensure_ascii=False)
                if updated != encoded:
                    db.execute('UPDATE daily SET musical=? WHERE day=?', (updated, saved_day))

    def save_details(self, identity, payload):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO details VALUES (?, ?, ?)',
                       (identity, json.dumps(payload, ensure_ascii=False), time.time()))



def resolve_saved(stored, entries):
    """Keep the saved id, but show the current catalogue row when it still exists."""
    if not isinstance(stored, dict):
        return stored
    identity = stored.get("id")
    current = next((row for row in entries if row.get("id") == identity), None)
    if current:
        return current
    return {**stored, "removed": True}


def artwork_fields(entry, directory):
    if entry.get("removed"):
        artwork = {
            "artwork_url": "/artwork/base.svg",
            "artwork_kind": "fallback",
            "artwork_family": "abstract",
            "artwork_basis": [],
            "artwork_reason": "removed",
        }
        row = annotate_display(entry, artwork)
        row["display_image"] = None
        return row
    try:
        artwork = ensure_artwork(entry, directory, "/artwork/")
    except Exception:
        LOG.exception("Artwork generation failed for %s", entry.get("id"))
        artwork = {
            "artwork_url": "/artwork/base.svg",
            "artwork_kind": "fallback",
            "artwork_family": "abstract",
            "artwork_basis": [],
            "artwork_reason": "error",
        }
    return annotate_display(entry, artwork)


def fetch_details(entry):
    data = wiki_query({'action': 'query', 'titles': entry['wiki'], 'redirects': 1,
                       'prop': 'extracts|pageimages|info|langlinks', 'exintro': 1,
                       'explaintext': 1, 'exchars': 1200, 'piprop': 'thumbnail|name',
                       'pithumbsize': 1000, 'inprop': 'url', 'lllang': 'zh'})
    page = next(iter(data.get('query', {}).get('pages', [])), {})
    if not page or page.get('missing'):
        raise ValueError('Wikipedia article is unavailable')
    extract = (page.get('extract') or '').strip()
    result = {'intro_en': extract, 'wiki_url': page.get('fullurl') or entry['wiki_url'],
              'image': (page.get('thumbnail') or {}).get('source'),
              'image_source': wiki_url('File:' + page['pageimage']) if page.get('pageimage') else None,
              'intro_zh': '', 'translator': 'none', 'detail_status': 'ready'}
    chinese = next(iter(page.get('langlinks', [])), {}).get('title')
    if chinese:
        try:
            zh_data = wiki_query({'action': 'query', 'titles': chinese, 'redirects': 1,
                                  'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1,
                                  'exchars': 1200, 'inprop': 'url'}, language='zh')
            zh_page = next(iter(zh_data.get('query', {}).get('pages', [])), {})
            if zh_page.get('extract'):
                result.update(intro_zh=zh_page['extract'], title_zh=zh_page.get('title', chinese),
                              translator='wikipedia_zh', intro_source=zh_page.get('fullurl') or wiki_url(chinese, 'zh'))
        except Exception:
            LOG.info('Chinese article unavailable for %s', entry['wiki'])
    if not result['intro_zh']:
        bundled = read_json(BASE / 'data' / 'summaries_zh.json', {}).get(entry['title'])
        result.update(intro_zh=bundled or extract, translator='bundled' if bundled else 'none',
                      intro_source=result['wiki_url'])
    return result


class Library:
    def __init__(self, store, background=True):
        self.store = store
        self.entries, self.updated_at = load_catalog(store.directory)
        self.bundled_details = read_json(BASE / 'data' / 'articles.json', {}).get('articles', {})
        self.lock = threading.RLock()
        self.jobs = set()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='musical-details')
        self.background = background
        self.sync = {'running': False, 'done': 0, 'total': 0, 'error': None}
        self.last_sync_attempt = None

    def snapshot(self):
        with self.lock:
            return list(self.entries)

    def status(self):
        with self.lock:
            return {'total': len(self.entries), 'updated_at': self.updated_at,
                    'source': wiki_url('Category:Musicals by year'), 'sync': dict(self.sync)}

    def refresh(self):
        with self.lock:
            if self.sync['running'] or (self.last_sync_attempt is not None and time.monotonic() - self.last_sync_attempt < 60):
                return False
            self.last_sync_attempt = time.monotonic()
            self.sync = {'running': True, 'done': 0, 'total': 0, 'error': None}

        def progress(done, total):
            with self.lock:
                self.sync.update(done=done, total=total)

        def run():
            try:
                result = discover(progress)
                # Publish only a complete crawl. Partial updates never replace the library.
                write_json(self.store.directory / 'catalog.json', result)
                entries, updated = load_catalog(self.store.directory)
                with self.lock:
                    self.entries, self.updated_at = entries, updated
            except Exception:
                LOG.exception('Catalogue update failed')
                with self.lock:
                    self.sync['error'] = '更新未完成，已保留原有片库。请检查网络后重试。'
            finally:
                with self.lock:
                    self.sync['running'] = False

        threading.Thread(target=run, daemon=True, name='catalog-sync').start()
        return True

    def detail(self, entry):
        cached, timestamp = self.store.cached_details(entry['id'])
        if not cached:
            cached = self.bundled_details.get(entry['id'], {})
        ttl = 7 * 86400 if cached.get('detail_status') == 'ready' else 300
        if time.time() - timestamp < ttl:
            return cached
        with self.lock:
            if self.background and entry['id'] not in self.jobs and len(self.jobs) < 12:
                self.jobs.add(entry['id'])
                self.pool.submit(self._detail_job, entry)
        return {**cached, 'detail_status': 'loading', 'stale': bool(cached)}

    def _detail_job(self, entry):
        try:
            result = fetch_details(entry)
            self.store.save_details(entry['id'], result)
        except Exception:
            LOG.info('Details unavailable for %s', entry['wiki'], exc_info=True)
            previous, _ = self.store.cached_details(entry['id'])
            if not previous:
                previous = self.bundled_details.get(entry['id'], {})
            self.store.save_details(entry['id'], {**previous, 'detail_status': 'offline', 'stale': bool(previous)})
        finally:
            with self.lock:
                self.jobs.discard(entry['id'])


def create_app(runtime_dir=None, background=True):
    application = Flask(__name__)
    store = Store(runtime_dir or os.environ.get('SPINNINGTOP_DATA_DIR', BASE / 'data' / 'runtime'))
    library = Library(store, background)
    application.extensions.update(store=store, library=library)

    def payload(entry, selected_date=None, mode='daily'):
        title = entry.get('title', '')
        bundled = '' if entry.get('removed') else read_json(BASE / 'data' / 'summaries_zh.json', {}).get(title, '')
        result = {'intro_zh': '', 'intro_en': '', 'image': None,
                  'translator': 'none', **entry, 'gallery': [],
                  'fever_url': 'https://www.google.com/search?q=' + quote_plus(title + ' musical site:feverup.com'),
                  'search_url': 'https://www.google.com/search?q=' + quote_plus(title + ' musical official'),
                  'date': selected_date, 'mode': mode, 'total': len(library.snapshot())}
        if entry.get('removed'):
            cached, _ = store.cached_details(entry['id'])
            cached = cached or library.bundled_details.get(entry['id'], {})
            article = {key: cached[key] for key in ARCHIVE_FIELDS
                       if not result.get(key) and cached.get(key)}
            result.update(image=None, image_source=None, image_reuse='unverified', detail_status='ready')
        else:
            article = library.detail(entry) if entry.get('id') else {}
        result = merge_publication(result, article, bundled)
        result.update(date=selected_date, mode=mode, total=len(library.snapshot()), gallery=[])
        result.update(artwork_fields(result, store.directory / 'artwork'))
        if not result.get('title_zh'):
            result['title_zh'] = entry.get('title_zh', '')
        return result

    @application.get('/')
    def index():
        return render_template('index.html')

    @application.get('/api/musical')
    def musical():
        try:
            offset = int(request.args.get('offset', '0'))
            if not -36500 <= offset <= 36500:
                raise ValueError()
            raw = request.args.get('date')
            selected = date.fromisoformat(raw) if raw else date.today() + timedelta(days=offset)
            if not date(1900, 1, 1) <= selected <= date(2200, 12, 31):
                raise ValueError()
        except (ValueError, OverflowError):
            return jsonify(error='日期无效，请选择 1900 至 2200 年的日期。'), 400
        entries = library.snapshot()
        if not entries:
            return jsonify(error='片库为空，请恢复 data/catalog.json 或更新片库。'), 503
        entry = resolve_saved(store.pick(entries, selected.isoformat()), entries)
        result = payload(entry, selected.isoformat())
        store.archive_daily(result, selected.isoformat())
        return jsonify(result)

    @application.post('/api/random')
    def random_musical():
        entries = library.snapshot()
        if not entries:
            return jsonify(error='片库为空，请更新片库。'), 503
        return jsonify(payload(store.pick(entries), mode='random'))

    @application.get('/api/details')
    def details():
        identity = request.args.get('id', '')
        entry = next((row for row in library.snapshot() if row['id'] == identity), None)
        if not entry:
            # Saved days remain usable after catalogue removals.
            with store.connect() as db:
                entry = next((row for (encoded,) in db.execute('SELECT musical FROM daily')
                              if (row := json.loads(encoded))['id'] == identity), None)
            if entry:
                entry = {**entry, 'removed': True}
        if not entry:
            return jsonify(error='剧目不存在。'), 404
        result = payload(entry)
        store.archive_daily(result)
        return jsonify(result)

    @application.get('/artwork/<name>')
    def artwork_file(name):
        path = resolve_artwork_path(store.directory / 'artwork', name)
        if path is None:
            abort(404)
        response = send_file(path, mimetype='image/svg+xml')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    ensure_base(store.directory / 'artwork')

    @application.get('/api/catalog')
    def catalog_status():
        return jsonify(today=date.today().isoformat(), **library.status())

    @application.post('/api/catalog/refresh')
    def refresh_catalog():
        started = library.refresh()
        return jsonify(started=started, **library.status()), 202

    @application.after_request
    def no_cache(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    return application


app = create_app()


def main():
    parser = argparse.ArgumentParser(description='Spinning Top · 每日音乐剧')
    parser.add_argument('port', nargs='?', type=int, default=int(os.environ.get('PORT', '5000')))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    library = app.extensions['library']
    try:
        stale = datetime.now(timezone.utc) - datetime.fromisoformat(library.updated_at) > timedelta(days=7)
    except (TypeError, ValueError):
        stale = True
    if stale:
        library.refresh()
    if not args.no_browser and os.environ.get('NO_BROWSER') not in ('1', 'true'):
        timer = threading.Timer(1.4, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}/'))
        timer.daemon = True
        timer.start()
    print(f'* Spinning Top 每日音乐剧：http://127.0.0.1:{args.port}/')
    app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
