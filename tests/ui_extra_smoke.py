"""Image-state and subpath checks for the built static site."""
import json
import os
import threading
import time
from urllib.parse import urlparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get('SPINNINGTOP_SITE_DIR', BASE / '_site'))
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082")
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'


def image_callback_order(browser, url, catalog, kind, old_result, new_result, update):
    context = browser.new_context()
    try:
        page = context.new_page()
        if update == 'timeout':
            page.clock.install()
        page.add_init_script(r"""(() => {
          window.imageEvents = [];
          window.pendingImages = [];
          const source = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
          Object.defineProperty(HTMLImageElement.prototype, 'src', {
            ...source, set(value) {
              if (/race-[ab]\.png|[ab]{20}\.svg/.test(value)) {
                window.pendingImages.push(this);
                for (const type of ['load', 'error']) this.addEventListener(type, () => {
                  if (this.src === new URL(value, location.href).href) window.imageEvents.push({url: value, type});
                }, {once: true, capture: true});
              }
              source.set.call(this, value);
            }
          });
        })();""")
        html = (SITE / 'index.html').read_text(encoding='utf-8').replace('<script src="./static/static-api.js"></script>', '')
        page.route(url, lambda route: route.fulfill(content_type='text/html', body=html))
        page.route('**/artwork/base.svg', lambda route: route.fulfill(content_type='image/svg+xml', body=SVG))
        old = {**catalog['musicals'][0], 'id': 'race:a', 'title': 'Old selection',
               'date': '2031-05-05', 'mode': 'daily', 'detail_status': 'loading' if update == 'details' else 'ready',
               'display_image': None, 'artwork_url': './static/artwork/base.svg'}
        new = {**old, 'id': old['id'] if update == 'details' else 'race:b',
               'title': 'New selection', 'detail_status': 'ready'}
        if kind == 'plate':
            old_url, new_url = './static/artwork/' + 'a' * 20 + '.svg', './static/artwork/' + 'b' * 20 + '.svg'
            old['artwork_url'], new['artwork_url'] = old_url, new_url
        else:
            old_url, new_url = url + 'race-a.png', url + 'race-b.png'
            old['display_image'], new['display_image'] = old_url, new_url
        pending = {}
        page.route('**/' + old_url.rsplit('/', 1)[-1], lambda route: pending.update(old=route))
        page.route('**/' + new_url.rsplit('/', 1)[-1], lambda route: pending.update(new=route))
        page.route('**/api/catalog', lambda route: route.fulfill(json={'total': 2, 'sync': {'running': False}}))
        page.route('**/api/musical**', lambda route: route.fulfill(json=old))
        page.route('**/api/random', lambda route: route.fulfill(json=new))
        page.route('**/api/details**', lambda route: route.fulfill(json=new))
        page.goto(url, wait_until='domcontentloaded')
        expect(page.locator('#title')).to_contain_text('Old selection')
        page.wait_for_function('window.pendingImages.length === 1')
        deadline = time.monotonic() + 5
        while 'old' not in pending and time.monotonic() < deadline:
            page.wait_for_timeout(10)
        assert 'old' in pending
        if kind == 'plate':
            expect(page.locator('#artwork')).to_have_attribute('data-artwork-state', 'loading')
        else:
            expect(page.locator('#imageState')).to_have_attribute('data-image-state', 'loading')
        assert page.evaluate('window.imageEvents') == []
        if update == 'timeout':
            page.clock.fast_forward(8001)
            expect(page.locator('#imageState')).to_have_attribute('data-image-state', 'failed')
            pending['old'].fulfill(status=200 if old_result == 'load' else 404,
                                   content_type='image/png', body=PNG if old_result == 'load' else b'missing')
            page.wait_for_function('window.imageEvents.length === 1')
            assert page.evaluate('window.imageEvents') == [{'url': old_url, 'type': old_result}]
            expect(page.locator('#imageState')).to_have_attribute('data-image-state', 'failed')
            expect(page.locator('#cover')).to_be_hidden()
            return
        if update != 'details':
            page.locator('#randomBtn').click()
        expect(page.locator('#title')).to_contain_text('New selection')
        page.wait_for_function('window.pendingImages.length === 2')
        deadline = time.monotonic() + 5
        while 'new' not in pending and time.monotonic() < deadline:
            page.wait_for_timeout(10)
        assert 'new' in pending

        def finish(route, outcome):
            if outcome == 'error':
                route.fulfill(status=404, content_type='text/plain', body='missing')
            else:
                route.fulfill(content_type='image/svg+xml' if kind == 'plate' else 'image/png', body=SVG if kind == 'plate' else PNG)

        finish(pending['new'], new_result)
        page.wait_for_function('window.imageEvents.length === 1')
        if kind == 'plate':
            expect(page.locator('#artwork')).to_have_attribute('data-artwork-state', 'ready' if new_result == 'load' else 'fallback')
        else:
            expect(page.locator('#imageState')).to_have_attribute('data-image-state', 'loaded' if new_result == 'load' else 'failed')
        snapshot = """() => ({id: document.querySelector('#card').dataset.id,
          title: document.querySelector('#title').textContent,
          art: document.querySelector('#artwork').getAttribute('src'),
          artState: document.querySelector('#artwork').dataset.artworkState,
          cover: document.querySelector('#cover').getAttribute('src'),
          hidden: document.querySelector('#cover').hidden,
          state: document.querySelector('#imageState').dataset.imageState})"""
        before = page.evaluate(snapshot)
        finish(pending['old'], old_result)
        page.wait_for_function('window.imageEvents.length === 2')
        assert page.evaluate('window.imageEvents') == [
            {'url': new_url, 'type': new_result}, {'url': old_url, 'type': old_result}]
        assert page.evaluate(snapshot) == before, (kind, old_result, new_result, update)
        assert before['id'] == new['id']
        if kind == 'plate':
            assert page.evaluate("window.pendingImages[0].getAttribute('src')") == old_url
            assert page.evaluate('window.pendingImages[0].dataset.artworkState') == 'loading'
    finally:
        context.close()

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

class Prefixed(Quiet):
    def do_GET(self):
        prefix = "/musical-spinningtop"
        if self.path == prefix:
            self.path = prefix + "/"
        if self.path.startswith(prefix + "/"):
            self.path = self.path[len(prefix):] or "/"
        return super().do_GET()

root = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(SITE)))
threading.Thread(target=root.serve_forever, daemon=True).start()
prefixed = ThreadingHTTPServer(("127.0.0.1", 0), partial(Prefixed, directory=str(SITE)))
threading.Thread(target=prefixed.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{root.server_port}/"
prefix_url = f"http://127.0.0.1:{prefixed.server_port}/musical-spinningtop/"
catalog = json.loads((SITE / "data/site-catalog.json").read_text(encoding="utf-8"))
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.route("https://example.test/cover-a.png", lambda route: route.fulfill(status=200, content_type="image/png", body=PNG))
        context.route("https://example.test/cover-b.png", lambda route: route.abort())
        one = json.loads(json.dumps(catalog))
        one["musicals"] = one["musicals"][:1]
        one["musicals"][0]["display_image"] = "https://example.test/cover-a.png"
        one["musicals"][0].update(image_reuse='verified', image_source='https://example.test/source',
                                  image_attribution='Fixture photographer', image_credit='Fixture collection',
                                  image_license='CC BY 4.0', image_license_url='https://creativecommons.org/licenses/by/4.0/')
        context.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(one)))
        page = context.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#imageState")).to_have_attribute("data-image-state", "loaded", timeout=8000)
        assert page.locator("#cover").is_visible()
        page.locator('#infoBtn').click()
        expect(page.locator('#imageCredit')).to_contain_text('Fixture photographer')
        expect(page.locator('#imageCredit')).to_contain_text('Fixture collection')
        expect(page.locator('#imageCredit')).to_contain_text('CC BY 4.0')
        expect(page.locator('#imageSource')).to_have_attribute('href', 'https://example.test/source')
        expect(page.locator('#imageLicense')).to_have_attribute('href', 'https://creativecommons.org/licenses/by/4.0/')
        page.keyboard.press('Escape')
        failed = json.loads(json.dumps(one))
        failed["musicals"][0]["display_image"] = "https://example.test/cover-b.png"
        failed['musicals'][0].update(image_source='javascript:alert(1)', image_license_url='data:text/html,unsafe',
                                    image_attribution='<img src=x onerror=alert(1)>')
        context.unroute("**/data/site-catalog.json")
        context.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(failed)))
        page.evaluate("spinningTopStatic.request('/api/catalog/refresh', {method: 'POST'})")
        page.reload()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#imageState")).to_have_attribute("data-image-state", "failed", timeout=8000)
        assert page.locator("#artwork").is_visible()
        assert page.locator("#cover").is_hidden()
        page.locator('#infoBtn').click()
        expect(page.locator('#imageCredit')).to_contain_text('<img src=x onerror=alert(1)>')
        assert page.locator('#imageCredit img').count() == 0
        for identifier in ('imageSource', 'imageLicense'):
            expect(page.locator('#' + identifier)).to_be_hidden()
            assert page.locator('#' + identifier).get_attribute('href') is None
        page.keyboard.press('Escape')
        missing = json.loads(json.dumps(catalog))
        missing["musicals"] = missing["musicals"][:1]
        missing["musicals"][0]["artwork_url"] = "./static/artwork/aaaaaaaaaaaaaaaaaaaa.svg"
        fallback = browser.new_context()
        image_requests = []
        fallback.on("request", lambda request: image_requests.append(request.url))
        fallback.route("**/aaaaaaaaaaaaaaaaaaaa.svg", lambda route: route.fulfill(status=404, content_type="text/plain", body="missing"))
        fallback.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(missing)))
        missed = fallback.new_page()
        missed.goto(url)
        missed.wait_for_load_state("networkidle")
        assert missed.locator("#artwork").get_attribute("src").split("?")[0].endswith("/base.svg")
        kept = missed.evaluate("spinningTopStatic.request('/api/musical')")["id"]
        missed.locator("#artwork").evaluate("node => node.dispatchEvent(new Event('error'))")
        assert missed.evaluate("spinningTopStatic.request('/api/musical')")["id"] == kept
        assert sum(1 for item in image_requests if item.split("?")[0].endswith("/base.svg")) == 1
        for kind in ('plate', 'cover'):
            for update in ('selection', 'details'):
                for old_result, new_result in (('load', 'load'), ('error', 'load'), ('load', 'error'), ('error', 'error')):
                    image_callback_order(browser, url, catalog, kind, old_result, new_result, update)
        for outcome in ('load', 'error'):
            image_callback_order(browser, url, catalog, 'cover', outcome, 'load', 'timeout')
        loop = browser.new_context()
        loop_requests = []
        loop.on("request", lambda request: loop_requests.append(request.url))
        loop.route("**/aaaaaaaaaaaaaaaaaaaa.svg", lambda route: route.fulfill(status=404, content_type="text/plain", body="missing"))
        loop.route("**/base.svg", lambda route: route.fulfill(status=404, content_type="text/plain", body="missing"))
        loop.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(missing)))
        looped = loop.new_page()
        looped.goto(url)
        looped.wait_for_load_state("networkidle")
        assert sum(1 for item in loop_requests if item.split("?")[0].endswith("/base.svg")) == 1
        assert looped.locator("#artwork").evaluate("node => node.dataset.artworkState") == "failed"
        sub = browser.new_context().new_page()
        sub.goto(prefix_url)
        sub.wait_for_load_state("networkidle")
        expect(sub.locator("#card")).to_have_attribute("aria-busy", "false")
        src = sub.locator("#artwork").evaluate("node => node.src")
        assert "/musical-spinningtop/static/artwork/" in src
        external = []
        sub.context.on("request", lambda request: external.append(request.url) if request.url.startswith("http") and "127.0.0.1" not in request.url else None)
        sub.reload()
        expect(sub.locator("#card")).to_have_attribute("aria-busy", "false")
        assert not any(urlparse(item).hostname == "upload.wikimedia.org" for item in external)
        browser.close()
finally:
    root.shutdown()
    root.server_close()
    prefixed.shutdown()
    prefixed.server_close()
