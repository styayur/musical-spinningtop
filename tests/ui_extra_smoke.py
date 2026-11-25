"""Image-state and subpath checks for the built static site."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082")

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

root = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(BASE / "_site")))
threading.Thread(target=root.serve_forever, daemon=True).start()
prefixed = ThreadingHTTPServer(("127.0.0.1", 0), partial(Prefixed, directory=str(BASE / "_site")))
threading.Thread(target=prefixed.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{root.server_port}/"
prefix_url = f"http://127.0.0.1:{prefixed.server_port}/musical-spinningtop/"
catalog = json.loads((BASE / "_site/data/site-catalog.json").read_text(encoding="utf-8"))
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.route("https://example.test/cover-a.png", lambda route: route.fulfill(status=200, content_type="image/png", body=PNG))
        context.route("https://example.test/cover-b.png", lambda route: route.abort())
        one = json.loads(json.dumps(catalog))
        one["musicals"] = one["musicals"][:1]
        one["musicals"][0]["display_image"] = "https://example.test/cover-a.png"
        context.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(one)))
        page = context.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#imageState")).to_have_attribute("data-image-state", "loaded", timeout=8000)
        assert page.locator("#cover").is_visible()
        failed = json.loads(json.dumps(one))
        failed["musicals"][0]["display_image"] = "https://example.test/cover-b.png"
        context.unroute("**/data/site-catalog.json")
        context.route("**/data/site-catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps(failed)))
        page.evaluate("indexedDB.deleteDatabase('musical-spinningtop-v2')")
        page.wait_for_timeout(200)
        page.goto(url)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#imageState")).to_have_attribute("data-image-state", "failed", timeout=8000)
        assert page.locator("#artwork").is_visible()
        assert page.locator("#cover").is_hidden()
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
        assert not any("upload.wikimedia.org" in item for item in external)
        browser.close()
        print("Image states and subpath passed.")
finally:
    root.shutdown()
    root.server_close()
    prefixed.shutdown()
    prefixed.server_close()
