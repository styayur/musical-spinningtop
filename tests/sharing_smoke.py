"""Real static work pages under a Pages subpath; isolated, simulated share capabilities."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / '_site'
OUT = ROOT / 'artifacts' / 'ui-sharing'
OUT.mkdir(parents=True, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/musical-spinningtop/'):
            self.path = self.path[len('/musical-spinningtop'):]
        else:
            self.send_error(404)
            return
        super().do_GET()

    def log_message(self, *_):
        pass


def records(page):
    return page.evaluate("""async () => {
      const db = await new Promise((resolve,reject) => { const r=indexedDB.open('musical-spinningtop-v2',1); r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error); });
      const out={};
      for(const name of ['daily','cycles']) out[name]=await new Promise(resolve=> {const r=db.transaction(name).objectStore(name).getAll(); r.onsuccess=()=>resolve(r.result);});
      db.close(); return out;
    }""")


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(SITE)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/musical-spinningtop/'
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for locale, invitation, lang in [('zh-CN','把今天，交给一场好戏。','zh-CN'),('zh-TW','把今天，交给一场好戏。','zh-TW'),('en-US','Give today to a good show.','en'),('ja-JP','Give today to a good show.','en')]:
            context = browser.new_context(locale=locale,viewport={'width':1440,'height':900},reduced_motion='reduce')
            context.add_init_script("Object.defineProperty(navigator,'canShare',{value:()=>false, configurable:true});")
            page = context.new_page()
            errors=[]
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(url,wait_until='networkidle')
            expect(page.locator('#card')).to_have_attribute('aria-busy','false')
            expect(page.locator('#invitation')).to_have_text(invitation)
            expect(page.locator('#invitation')).to_have_attribute('lang',lang)
            assert page.locator('#infoBtn').bounding_box()['width'] >=44
            assert page.locator('#infoBtn span').bounding_box()['width'] ==24
            assert page.locator('#title').bounding_box()['y'] <900
            for mode in ('daily','random','history'):
                if mode == 'random': page.locator('#randomBtn').click()
                if mode == 'history': page.locator('#prevBtn').click()
                expect(page.locator('#card')).to_have_attribute('aria-busy','false')
                identity = page.locator('#card').get_attribute('data-id')
                before = records(page)
                page.locator('#shareBtn').click()
                expect(page.locator('#copyShare')).to_be_enabled()
                expect(page.locator('#sharePublication')).to_contain_text('尚未在线确认' if locale.startswith('zh') else 'has not been confirmed online')
                expect(page.locator('#nativeShare')).to_be_hidden()
                public = page.locator('#shareLink').input_value()
                assert public.startswith('https://styayur.github.io/musical-spinningtop/works/')
                assert not urlparse(public).query
                for selector,param in [('#shareX','url'),('#shareFacebook','u'),('#shareThreads','url')]:
                    assert parse_qs(urlparse(page.locator(selector).get_attribute('href')).query)[param] == [public]
                assert public in parse_qs(urlparse(page.locator('#shareWhatsApp').get_attribute('href')).query)['text'][0]
                receiver = browser.new_context(java_script_enabled=True)
                work = receiver.new_page()
                work.goto(public.replace('https://styayur.github.io/musical-spinningtop/',url),wait_until='networkidle')
                expect(work.locator('#card')).to_have_attribute('data-id',identity)
                expect(work.locator('#sharedNotice')).to_be_visible()
                assert records(work)=={'daily':[],'cycles':[]}
                work.reload(wait_until='networkidle')
                assert records(work)=={'daily':[],'cycles':[]}
                work.locator('#todayBtn').click()
                expect(work.locator('#sharedNotice')).to_be_hidden()
                assert len(records(work)['daily'])==1
                receiver.close()
                assert records(page)==before
                page.keyboard.press('Escape')
                expect(page.locator('#shareBtn')).to_be_focused()
            page.locator('#shareBtn').click()
            expect(page.locator('#saveShare')).to_be_enabled()
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw new Error('denied')}},configurable:true})")
            page.locator('#copyShare').click()
            expect(page.locator('#shareLink')).to_be_focused()
            page.screenshot(path=str(OUT/f'share-{locale}.png'),full_page=True)
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copiedLink=text}},configurable:true})")
            page.locator('#copyShare').click()
            expect(page.locator('#shareStatus')).to_have_text('链接已复制。' if locale.startswith('zh') else 'Link copied.')
            assert page.evaluate('window.copiedLink')==page.locator('#shareLink').input_value()
            with page.expect_download() as download:
                page.locator('#saveShare').click()
            assert download.value.suggested_filename.endswith('.png')
            page.route('**/static/share/*.png',lambda route:route.fulfill(status=404,body='missing'))
            page.locator('#saveShare').click()
            expect(page.locator('#shareStatus')).to_contain_text('图片加载失败' if locale.startswith('zh') else 'Image could not load')
            page.keyboard.press('Escape')
            page.screenshot(path=str(OUT/f'desktop-{locale}.png'),full_page=True)
            for width in (320,390,768):
                page.set_viewport_size({'width':width,'height':1024})
                assert page.evaluate('document.documentElement.scrollWidth') <= width
                page.screenshot(path=str(OUT/f'viewport-{width}-{locale}.png'),full_page=True)
            page.locator('#infoBtn').click()
            page.locator('#tabWork').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#tabUse')).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.locator('#infoBtn')).to_be_focused()
            assert not errors,errors
            context.close()
        # Missing language and controlled native sharing/cancellation; no platform is contacted.
        context=browser.new_context()
        context.add_init_script("""Object.defineProperty(navigator,'languages',{value:[]}); Object.defineProperty(navigator,'language',{value:''});
          window.shareCalls=[]; Object.defineProperty(navigator,'canShare',{value:()=>true});
          Object.defineProperty(navigator,'share',{value:async(data)=>{window.shareCalls.push(data); if(window.nativeFailure) throw new Error('unsupported'); throw new DOMException('cancelled','AbortError')}});""")
        page=context.new_page(); page.goto(url,wait_until='networkidle')
        expect(page.locator('#invitation')).to_have_attribute('lang','en')
        assert page.evaluate('shareCalls.length')==0
        page.locator('#shareBtn').click()
        expect(page.locator('#nativeShare')).to_be_visible()
        assert page.evaluate('shareCalls.length')==0
        page.locator('#nativeShare').click()
        expect(page.locator('#shareStatus')).to_have_text('Sharing cancelled.')
        assert page.evaluate('shareCalls.length')==1
        page.evaluate('window.nativeFailure=true')
        page.locator('#nativeShare').click()
        expect(page.locator('#shareStatus')).to_contain_text('Device sharing is unavailable')
        expect(page.locator('#copyShare')).to_be_enabled()
        page.keyboard.press('Escape')
        page.goto(url+'404.html',wait_until='networkidle')
        expect(page.locator('#sharedNotice')).to_be_visible()
        expect(page.locator('#shareBtn')).to_be_disabled()
        saved=records(page)
        page.reload(wait_until='networkidle')
        assert records(page)==saved
        page.locator('#todayBtn').click()
        expect(page.locator('#card')).to_have_attribute('aria-busy','false')
        page.route('**/data/share-index.json',lambda route:route.fulfill(json={}))
        page.locator('#shareBtn').click()
        expect(page.locator('#shareStatus')).to_contain_text('no published public page')
        expect(page.locator('#copyShare')).to_be_disabled()
        context.close()
        # Crawler path: no JS needed for metadata, image dimensions, title or synopsis.
        index=json.loads((SITE/'data/share-index.json').read_text(encoding='utf-8'))
        info=next(iter(index.values()))
        # Simulate the public origin with locally served bytes; no live deployment claim.
        context=browser.new_context(locale='en-US')
        page=context.new_page()
        public_base='https://styayur.github.io/musical-spinningtop/'
        def public_response(route):
            if route.request.url.startswith(public_base):
                route.fulfill(response=context.request.get(route.request.url.replace(public_base,url)))
            else:
                route.abort()
        page.route('**/*',public_response)
        page.goto(info['url'],wait_until='networkidle')
        page.locator('#shareBtn').click()
        expect(page.locator('#sharePublication')).to_contain_text('listed in the current public site')
        expect(page.locator('#copyShare')).to_be_enabled()
        context.close()
        # Failed exits must keep the shared URL, title, metadata and draw stores.
        for button, endpoint in [('todayBtn','/api/musical'), ('randomBtn','/api/random')]:
            context=browser.new_context()
            page=context.new_page()
            page.goto(info['url'].replace('https://styayur.github.io/musical-spinningtop/',url),wait_until='networkidle')
            before_url, before_title = page.url, page.title()
            before_meta = page.locator('[data-work-meta]').evaluate_all('(nodes)=>nodes.map(n=>n.outerHTML)')
            before_records = records(page)
            page.evaluate("""() => {
              const original = window.spinningTopStatic.request;
              window.selectionCalls = []; window.holdSelection = true;
              window.spinningTopStatic.request = (path, options) => {
                if(path.startsWith('/api/musical') || path === '/api/random') {
                  window.selectionCalls.push(path);
                  if(window.holdSelection) return new Promise((resolve,reject)=>{window.rejectSelection=reject});
                }
                return original(path,options);
              };
            }""")
            page.locator('#'+button).click()
            expect(page.locator('#card')).to_have_attribute('aria-busy','true')
            assert page.url==before_url and page.title()==before_title
            page.evaluate("window.rejectSelection(new Error('controlled selection failure'))")
            expect(page.locator('#retryBtn')).to_be_visible()
            expect(page.locator('#card')).to_have_attribute('aria-busy','false')
            expect(page.locator('#sharedNotice')).to_be_visible()
            assert page.url==before_url and page.title()==before_title
            assert page.locator('[data-work-meta]').evaluate_all('(nodes)=>nodes.map(n=>n.outerHTML)')==before_meta
            assert records(page)==before_records
            page.evaluate('window.holdSelection=false')
            page.locator('#retryBtn').click()
            expect(page.locator('#sharedNotice')).to_be_hidden()
            expect(page.locator('#card')).to_have_attribute('aria-busy','false')
            assert page.url==url
            assert page.title()==page.locator('#title').inner_text()+' · Spinning Top'
            assert page.locator('[data-work-meta], #sharedWork, link[rel="canonical"], meta[property^="og:"], meta[name^="twitter:"]').count()==0
            assert page.evaluate('selectionCalls')==[endpoint,endpoint]
            if button=='randomBtn':
                expect(page.locator('#randomBtn')).to_have_attribute('aria-pressed','true')
                assert records(page)['daily']==[]
            else:
                assert len(records(page)['daily'])==1
            context.close()
        context=browser.new_context(java_script_enabled=False)
        page=context.new_page(); page.goto(info['url'].replace('https://styayur.github.io/musical-spinningtop/',url))
        assert page.locator('meta[property="og:url"]').get_attribute('content')==info['url']
        image=page.locator('meta[property="og:image"]').get_attribute('content')
        assert image.startswith('https://styayur.github.io/')
        assert context.request.get(image.replace('https://styayur.github.io/musical-spinningtop/',url)).status==200
        assert page.locator('meta[name="twitter:card"]').get_attribute('content')=='summary_large_image'
        assert page.locator('#title').inner_text()!='即将开场'
        catalog=json.loads((SITE/'data/site-catalog.json').read_text(encoding='utf-8'))['musicals']
        row=next(row for row in catalog if index[row['id']]==info)
        expect(page.locator('#yearChip')).to_have_text(str(row['year']))
        expect(page.locator('#introSource')).to_be_visible()
        assert page.locator('#introSource').get_attribute('href')==(row.get('intro_source') or row['wiki_url'])
        expect(page.locator('#sharedTextCredit')).to_be_visible()
        expect(page.locator('#sharedTextCredit')).to_contain_text('Wikipedia contributors')
        assert page.locator('#sharedTextCredit a[rel="license"]').get_attribute('href')=='https://creativecommons.org/licenses/by-sa/4.0/'
        context.close(); browser.close()
finally:
    server.shutdown(); server.server_close()
