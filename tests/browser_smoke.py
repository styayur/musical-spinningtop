"""Browser regression checks against a running local application (real API + failure fixtures)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000'
artifacts = Path(__file__).resolve().parents[1] / 'artifacts'
artifacts.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_load_state('networkidle')
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
    today = page.locator('#dateInput').input_value()
    first = page.locator('#title').inner_text().split(' · ')[0]
    expect(page.locator('#catalogCount')).to_contain_text('部可探索')
    assert page.locator('#intro').inner_text()
    page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)

    page.locator('#flipBtn').click()
    expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'true')
    assert page.locator('#frontFace').evaluate('(node) => node.inert')
    assert not page.locator('#backFace').evaluate('(node) => node.inert')
    assert page.locator('#wikiBtn').get_attribute('href').startswith('https://en.wikipedia.org/')
    page.screenshot(path=str(artifacts / 'back.png'), full_page=True)
    page.keyboard.press('Escape')
    expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'false')

    page.locator('#randomBtn').click()
    expect(page.locator('#datePill')).to_have_text('自由探索')
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
    page.locator('#todayBtn').click()
    expect(page.locator('#datePill')).to_have_text('每日随机')
    expect(page.locator('#title')).to_contain_text(first)
    expect(page.locator('#dateInput')).to_have_value(today)

    page.locator('#prevBtn').click()
    expect(page.locator('#dateInput')).not_to_have_value(today)
    expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
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
    page.locator('#syncBtn').click()
    expect(page.locator('#catalogStatus')).to_contain_text('50 / 156')
    expect(page.locator('#syncBtn')).to_be_disabled()
    page.unroute('**/api/catalog')
    page.route('**/api/catalog', lambda route: route.fulfill(content_type='application/json', body='{"total":2650,"updated_at":"2026-09-25T00:00:00Z","sync":{"running":false,"done":50,"total":156,"error":"测试：更新未完成，已保留原有片库。"}}'))
    expect(page.locator('#catalogStatus')).to_contain_text('已保留原有片库', timeout=7000)
    expect(page.locator('#syncBtn')).to_be_enabled()
    page.unroute('**/api/catalog')
    page.unroute('**/api/catalog/refresh')

    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth') == width
        page.locator('#randomBtn').click()
        expect(page.locator('#card')).to_have_attribute('aria-busy', 'false')
        page.locator('#flipBtn').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#flipBtn')).to_have_attribute('aria-pressed', 'true')
        page.keyboard.press('Escape')
        page.screenshot(path=str(artifacts / f'mobile-{width}.png'), full_page=True)
    assert not errors, errors
    browser.close()
    print('Browser checks passed: desktop, mobile 390/320, keyboard, flip, daily persistence, random, dates, errors, update progress.')
