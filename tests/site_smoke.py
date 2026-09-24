"""Test the actual static site, including IndexedDB transactions and offline catalogue fallback."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(BASE / '_site')))
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
        expect(page.locator('#catalogCount')).to_contain_text('部可探索')
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
        assert page.locator('.source-code').inner_text().find('AGPL-3.0') >= 0
        assert not errors, errors
        context.close()
        # A small real-shaped catalogue lets us exhaust and restart a whole cycle.
        small = json.loads((BASE / '_site/data/site-catalog.json').read_text(encoding='utf-8'))
        small['musicals'] = small['musicals'][:7]
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
        browser.close()
        print('Static website passed: random cycles, concurrent draws, daily persistence, cross-tab consistency, cached-data fallback, mobile and license/source links.')
finally:
    server.shutdown()
    server.server_close()
