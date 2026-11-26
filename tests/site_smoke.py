"""Test the actual static site, including IndexedDB transactions and offline catalogue fallback."""
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get('SPINNINGTOP_SITE_DIR', BASE / '_site'))
ARTIFACTS = BASE / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(SITE)))
worker = threading.Thread(target=server.serve_forever, daemon=True)
worker.start()
url = f'http://127.0.0.1:{server.server_port}/'
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        # Covers are optional external media, and are not needed for functional verification.
        context.route('https://upload.wikimedia.org/**', lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_load_state('networkidle')
        expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
        assert page.locator('#title').inner_text() != '即将开场'
        page.locator('#infoBtn').click()
        page.locator('#tabAbout').click()
        expect(page.locator('#catalogCount')).to_contain_text('部可探索')
        page.locator('#tabAbout').focus()
        page.keyboard.press('ArrowLeft')
        expect(page.locator('#tabUse')).to_be_focused()
        expect(page.locator('#panelUse')).to_be_visible()
        page.keyboard.press('Home')
        expect(page.locator('#tabWork')).to_be_focused()
        expect(page.locator('#panelWork')).to_be_visible()
        page.keyboard.press('End')
        expect(page.locator('#tabAbout')).to_be_focused()
        assert 'AGPL-3.0' in page.locator('#licenseNote').inner_text()
        assert '下载本地版' not in page.content()
        page.screenshot(path=str(ARTIFACTS / 'static-info.png'), full_page=True)
        page.keyboard.press('Escape')
        expect(page.locator('#infoBtn')).to_be_focused()
        page.screenshot(path=str(ARTIFACTS / 'static-daily.png'), full_page=True)
        daily = page.evaluate("spinningTopStatic.request('/api/musical')")
        assert daily['total'] > 2000
        random = page.evaluate("async () => Promise.all(Array.from({length: 24}, () => spinningTopStatic.request('/api/random', {method: 'POST'})))")
        assert len({row['id'] for row in random}) == 24
        assert page.evaluate("spinningTopStatic.request('/api/musical')")['id'] == daily['id']
        page.reload()
        page.wait_for_load_state('networkidle')
        assert page.evaluate("spinningTopStatic.request('/api/musical')")['id'] == daily['id']
        second = context.new_page()
        second.goto(url)
        second.wait_for_load_state('networkidle')
        assert second.evaluate("spinningTopStatic.request('/api/musical')")['id'] == daily['id']
        simultaneous = page.evaluate("async () => Promise.all(Array.from({length: 12}, () => spinningTopStatic.request('/api/musical?date=2027-01-01')))")
        assert len({row['id'] for row in simultaneous}) == 1
        # Block the data URL only; a saved IndexedDB catalogue must still work on reload.
        context.route('**/data/site-catalog.json', lambda route: route.abort())
        page.reload()
        page.wait_for_load_state('networkidle')
        expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
        assert page.evaluate("spinningTopStatic.request('/api/musical')")['id'] == daily['id']
        page.locator('#flipBtn').click()
        expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'true')
        assert page.locator('#wikiBtn').get_attribute('href').startswith('https://en.wikipedia.org/')
        page.keyboard.press('Escape')
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth') == width
        page.set_viewport_size({'width': 768, 'height': 1024})
        assert page.evaluate('document.documentElement.scrollWidth') <= 768
        page.evaluate("document.documentElement.style.zoom = '1.5'")
        assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
        page.evaluate("document.documentElement.style.zoom = '1'")
        assert page.locator('#repoLink').get_attribute('href') == 'https://github.com/styayur/musical-spinningtop'
        src = page.locator('#artwork').get_attribute('src')
        assert '/static/artwork/' in src and '.svg' in src
        assert not errors, errors
        context.close()
        # A small real-shaped catalogue lets us exhaust and restart a whole cycle.
        small = json.loads((SITE / 'data/site-catalog.json').read_text(encoding='utf-8'))
        small['musicals'] = small['musicals'][:7]
        for row in small['musicals']:
            row.update(intro_en='Archived synopsis for ' + row['id'], intro_zh='保存的简介。',
                       translator='bundled', intro_source=row['wiki_url'])
        context = browser.new_context()
        context.route('**/data/site-catalog.json', lambda route: route.fulfill(content_type='application/json', body=json.dumps(small)))
        context.route('https://upload.wikimedia.org/**', lambda route: route.abort())
        page = context.new_page()
        page.goto(url)
        page.wait_for_load_state('networkidle')
        drawn = page.evaluate("async () => { const a=[]; for(let i=0;i<14;i++) a.push(await spinningTopStatic.request('/api/random',{method:'POST'})); return a; }")
        assert len({row['id'] for row in drawn[:7]}) == 7
        assert len({row['id'] for row in drawn[7:]}) == 7
        assert drawn[6]['id'] != drawn[7]['id']
        invalid = page.evaluate("async () => { try { await spinningTopStatic.request('/api/musical?date=2026-02-30'); return false; } catch (_) { return true; } }")
        assert invalid
        native = page.evaluate("spinningTopStatic.request('/api/musical?date=2031-05-07')")
        legacy_page = context.new_page()
        legacy_page.goto(url)
        legacy_page.wait_for_load_state('networkidle')
        legacy_id = legacy_page.evaluate("""async () => {
          const current = await spinningTopStatic.request('/api/musical?date=2031-05-05');
          const db = await new Promise((resolve, reject) => {
            const open = indexedDB.open('musical-spinningtop-v2', 1);
            open.onsuccess = () => resolve(open.result);
            open.onerror = () => reject(open.error);
          });
          await new Promise((resolve, reject) => {
            const tx = db.transaction(['daily', 'cycles'], 'readwrite');
            tx.objectStore('daily').put({id: current.id, title: 'OLD TITLE', intro_en: 'old text', intro_source: 'https://en.wikipedia.org/wiki/Old_Show', wiki_url: 'https://en.wikipedia.org/wiki/Old_Show', year: 1950, image: 'https://upload.wikimedia.org/old.jpg'}, '2031-05-05');
            tx.objectStore('daily').put({id: 'missing:removed', title: 'Gone Show', intro_en: 'kept', intro_source: 'https://en.wikipedia.org/wiki/Gone', wiki_url: 'https://en.wikipedia.org/wiki/Gone', year: 1961}, '2031-05-06');
            tx.oncomplete = resolve;
            tx.onabort = () => reject(tx.error);
          });
          return current.id;
        }""")
        id_only = small['musicals'][0]['id']
        legacy_page.evaluate("""async id => {
          const db = await new Promise(resolve => { const open = indexedDB.open('musical-spinningtop-v2', 1); open.onsuccess = () => resolve(open.result); });
          await new Promise((resolve, reject) => {
            const tx = db.transaction('daily', 'readwrite');
            tx.objectStore('daily').put({id, v: 2}, '2031-05-08');
            tx.oncomplete = resolve; tx.onabort = () => reject(tx.error);
          });
          db.close();
        }""", id_only)
        upgraded = legacy_page.evaluate("spinningTopStatic.request('/api/musical?date=2031-05-08')")
        assert upgraded['intro_en']
        legacy_page.reload()
        legacy_page.wait_for_load_state('networkidle')
        migrated = legacy_page.evaluate("spinningTopStatic.request('/api/musical?date=2031-05-05')")
        assert migrated['id'] == legacy_id
        assert migrated['title'] != 'OLD TITLE'
        assert not migrated.get('display_image')
        archived = legacy_page.evaluate("""async () => {
          const db = await new Promise(resolve => { const open = indexedDB.open('musical-spinningtop-v2', 1); open.onsuccess = () => resolve(open.result); });
          return await new Promise(resolve => { const req = db.transaction('daily').objectStore('daily').get('2031-05-05'); req.onsuccess = () => resolve(req.result); });
        }""")
        assert archived['v'] == 2 and archived['title'] == 'OLD TITLE' and archived['intro_en'] == 'old text'
        assert archived['intro_source'].startswith('https://en.wikipedia.org/')
        assert set(archived) != {'id', 'v'}
        removed = legacy_page.evaluate("spinningTopStatic.request('/api/musical?date=2031-05-06')")
        assert removed['title'] == 'Gone Show'
        assert removed['intro_en'] == 'kept'
        assert removed['wiki_url'] == 'https://en.wikipedia.org/wiki/Gone'
        assert 'base.svg' in removed['artwork_url']
        cycle_before = legacy_page.evaluate("""async () => {
          const db = await new Promise(resolve => { const open = indexedDB.open('musical-spinningtop-v2', 1); open.onsuccess = () => resolve(open.result); });
          const cycle = await new Promise(resolve => { const req = db.transaction('cycles').objectStore('cycles').get('daily'); req.onsuccess = () => resolve(req.result); });
          db.close(); return cycle;
        }""")
        filtered = json.loads(json.dumps(small))
        filtered['musicals'] = [row for row in small['musicals'] if row['id'] not in (legacy_id, native['id'], id_only)]
        context.unroute('**/data/site-catalog.json')
        context.route('**/data/site-catalog.json', lambda route: route.fulfill(content_type='application/json', body=json.dumps(filtered)))
        legacy_page.reload()
        legacy_page.wait_for_load_state('networkidle')
        lookback = legacy_page.evaluate("spinningTopStatic.request('/api/musical?date=2031-05-05')")
        assert lookback['id'] == legacy_id
        assert lookback['title'] == 'OLD TITLE'
        assert lookback['intro_en'] == 'old text'
        assert lookback['intro_source'] == 'https://en.wikipedia.org/wiki/Old_Show'
        assert 'base.svg' in lookback['artwork_url']
        for day, saved in (('2031-05-07', native), ('2031-05-08', upgraded)):
            restored = legacy_page.evaluate("day => spinningTopStatic.request('/api/musical?date=' + day)", day)
            for key in ('id', 'title', 'intro_en', 'intro_zh', 'intro_source', 'wiki_url', 'year'):
                assert restored.get(key) == saved.get(key), (day, key)
            assert restored['removed'] is True
            assert restored['artwork_url'].endswith('/base.svg')
            assert restored['display_image'] is None and restored['image'] is None
        used = legacy_page.evaluate("""async () => {
          const db = await new Promise(resolve => { const open = indexedDB.open('musical-spinningtop-v2', 1); open.onsuccess = () => resolve(open.result); });
          return await new Promise(resolve => { const req = db.transaction('cycles').objectStore('cycles').get('daily'); req.onsuccess = () => resolve(req.result); });
        }""")
        assert used == cycle_before

        browser.close()
finally:
    server.shutdown()
    server.server_close()
