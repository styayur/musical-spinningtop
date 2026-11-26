"""Browser regression checks against a running local application (real API + failure fixtures)."""
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect

artifacts = Path(__file__).resolve().parents[1] / 'artifacts'
artifacts.mkdir(exist_ok=True)

def screenshot(page, name):
    page.wait_for_function("document.querySelector('#artwork').complete && document.querySelector('#artwork').naturalWidth > 0")
    page.screenshot(path=str(artifacts / name), full_page=True)

@contextmanager
def running_app():
    if len(sys.argv) > 1:
        yield sys.argv[1]
        return
    from werkzeug.serving import make_server
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='spinningtop-browser-') as directory:
        with patch.dict('os.environ', {'SPINNINGTOP_DATA_DIR': directory}):
            from app import create_app
            application = create_app(directory, background=False)
        server = make_server('127.0.0.1', 0, application, threaded=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            worker.join()
            server.server_close()
            application.extensions['library'].pool.shutdown()

with running_app() as url, sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_load_state('networkidle')
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
    today = page.locator('#dateInput').input_value()
    first = page.locator('#title').inner_text().split(' · ')[0]
    page.locator('#infoBtn').click()
    page.locator('#tabAbout').click()
    expect(page.locator('#catalogCount')).to_contain_text('部可探索')
    page.keyboard.press('Home')
    expect(page.locator('#tabWork')).to_be_focused()
    page.keyboard.press('ArrowRight')
    expect(page.locator('#tabUse')).to_be_focused()
    page.keyboard.press('Tab')
    expect(page.locator('#panelUse')).to_be_focused()
    page.keyboard.press('Tab')
    expect(page.locator('#infoClose')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(page.locator('#panelUse')).to_be_focused()
    page.locator('#tabAbout').click()
    screenshot(page, 'info.png')
    page.keyboard.press('Escape')
    expect(page.locator('#infoBtn')).to_be_focused()
    assert page.locator('#intro').inner_text()
    screenshot(page, 'desktop.png')

    page.locator('#flipBtn').click()
    expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'true')
    assert page.locator('#frontFace').evaluate('(node) => node.inert')
    assert not page.locator('#backFace').evaluate('(node) => node.inert')
    assert page.locator('#wikiBtn').get_attribute('href').startswith('https://en.wikipedia.org/')
    screenshot(page, 'back.png')
    page.keyboard.press('Escape')
    expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'false')

    page.locator('#randomBtn').click()
    expect(page.locator('#datePill')).to_have_text('自由探索')
    expect(page.locator('#randomBtn')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#todayBtn')).to_have_attribute('aria-pressed', 'false')
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
    screenshot(page, 'random.png')
    page.locator('#todayBtn').click()
    expect(page.locator('#datePill')).to_have_text('每日随机')
    expect(page.locator('#todayBtn')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#title')).to_contain_text(first)
    expect(page.locator('#dateInput')).to_have_value(today)

    page.locator('#prevBtn').click()
    expect(page.locator('#dateInput')).not_to_have_value(today)
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
    screenshot(page, 'previous-date.png')
    previous = page.locator('#title').inner_text().split(' · ')[0]
    page.locator('#nextBtn').click()
    expect(page.locator('#dateInput')).to_have_value(today)
    expect(page.locator('#title')).to_contain_text(first)
    page.reload()
    page.wait_for_load_state('networkidle')
    expect(page.locator('#title')).to_contain_text(first)

    # Preserve a valid card, expose a retry, and recover after a failed request.
    page.route('**/api/musical**', lambda route: route.fulfill(status=503, content_type='application/json', body='{"error":"测试：暂时无法读取片库"}'))
    page.locator('#prevBtn').click()
    expect(page.locator('#notice')).to_contain_text('暂时无法读取片库')
    expect(page.locator('#retryBtn')).to_be_visible()
    expect(page.locator('#dateInput')).to_have_value(today)
    expect(page.locator('#title')).to_contain_text(first)
    page.unroute('**/api/musical**')
    page.locator('#retryBtn').click()
    expect(page.locator('#retryBtn')).to_be_hidden()
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')

    # Update states without starting another full remote crawl during a UI test.
    page.route('**/api/catalog/refresh', lambda route: route.fulfill(status=202, content_type='application/json', body='{"started":true,"sync":{"running":true}}'))
    page.route('**/api/catalog', lambda route: route.fulfill(content_type='application/json', body='{"total":2650,"updated_at":"2026-09-25T00:00:00Z","sync":{"running":true,"done":50,"total":156}}'))
    page.locator('#infoBtn').click()
    page.locator('#tabAbout').click()
    page.locator('#syncBtn').click()
    expect(page.locator('#catalogStatus')).to_contain_text('50 / 156')
    expect(page.locator('#syncBtn')).to_be_disabled()
    page.unroute('**/api/catalog')
    page.route('**/api/catalog', lambda route: route.fulfill(content_type='application/json', body='{"total":2650,"updated_at":"2026-09-25T00:00:00Z","sync":{"running":false,"done":50,"total":156,"error":"测试：更新未完成，已保留原有片库。"}}'))
    expect(page.locator('#catalogStatus')).to_contain_text('已保留原有片库', timeout=7000)
    expect(page.locator('#syncBtn')).to_be_enabled()
    page.unroute('**/api/catalog')
    page.unroute('**/api/catalog/refresh')
    page.locator('#infoClose').click()

    for width in (390, 320, 768):
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth') == width
        page.locator('#randomBtn').click()
        expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
        page.locator('#flipBtn').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'true')
        page.keyboard.press('Escape')
        screenshot(page, f'mobile-{width}.png')
    page.evaluate("document.documentElement.style.zoom = '1.5'")
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
    page.locator('#infoBtn').click()
    expect(page.locator('#tabWork')).to_be_focused()
    screenshot(page, 'css-zoom-150.png')
    page.keyboard.press('Escape')
    expect(page.locator('#infoBtn')).to_be_focused()
    page.evaluate("document.documentElement.style.zoom = '1'")
    assert not errors, errors
    browser.close()
