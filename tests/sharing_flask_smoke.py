"""Local read-only work UI and card parity against the real static build."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

with tempfile.TemporaryDirectory() as folder:
    os.environ['SPINNINGTOP_DATA_DIR']=str(Path(folder)/'import')
    from app import create_app
    application=create_app(Path(folder)/'runtime',background=False)
    server=make_server('127.0.0.1',0,application,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    index=json.loads((ROOT/'_site/data/share-index.json').read_text(encoding='utf-8'))
    identity,info=next(iter(index.items()))
    route=info['url'].split('/musical-spinningtop',1)[1]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(locale='en-US')
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url+route,wait_until='networkidle')
            expect(page.locator('#card')).to_have_attribute('data-id',identity)
            expect(page.locator('#sharedNotice')).to_be_visible()
            page.locator('#shareBtn').click()
            expect(page.locator('#copyShare')).to_be_enabled()
            expect(page.locator('#sharePublication')).to_contain_text('has not been confirmed online')
            assert page.locator('#shareLink').input_value()==info['url']
            public_image=page.locator('meta[property="og:image"]').get_attribute('content')
            assert public_image=='https://styayur.github.io/musical-spinningtop/'+info['image'][2:]
            local=context.request.get(url+'/api/share',params={'id':identity}).json()
            png=context.request.get(url+local['image']).body()
            assert png==(ROOT/'_site'/info['image'][2:]).read_bytes()
            with application.extensions['store'].connect() as db:
                for table in ('daily','seen','last_pick'):
                    assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            page.keyboard.press('Escape')
            expect(page.locator('#shareBtn')).to_be_focused()
            for button, endpoint in [('todayBtn','/api/musical'),('randomBtn','/api/random')]:
                page.goto(url+route,wait_until='networkidle')
                title=page.title()
                metadata=page.locator('[data-work-meta]').evaluate_all('(nodes)=>nodes.map(n=>n.outerHTML)')
                page.route('**'+endpoint,lambda request:request.fulfill(status=503,json={'error':'controlled failure'}))
                page.locator('#'+button).click()
                expect(page.locator('#retryBtn')).to_be_visible()
                assert page.url==url+route and page.title()==title
                assert page.locator('[data-work-meta]').evaluate_all('(nodes)=>nodes.map(n=>n.outerHTML)')==metadata
                page.unroute('**'+endpoint)
                page.locator('#retryBtn').click()
                expect(page.locator('#sharedNotice')).to_be_hidden()
                expect(page.locator('#card')).to_have_attribute('aria-busy','false')
                assert page.url==url+'/'
                assert page.title()==page.locator('#title').inner_text()+' · Spinning Top'
                assert page.locator('[data-work-meta], #sharedWork').count()==0
                expect(page.locator('#'+button)).to_have_attribute('aria-pressed','true')
            page.goto(url+'/works/unknown.html',wait_until='networkidle')
            expect(page.locator('#sharedNotice')).to_be_visible()
            expect(page.locator('#shareBtn')).to_be_disabled()
            assert context.request.get(url+'/api/share?id=local:only').json()=={'available':False,'reason':'not-public'}
            application.extensions['library'].entries=[{'id':'local:only','title':'Local card','intro_en':'A letter arrives.'}]
            page.goto(url+'/',wait_until='networkidle')
            page.locator('#randomBtn').click()
            expect(page.locator('#card')).to_have_attribute('data-id','local:only')
            page.locator('#shareBtn').click()
            expect(page.locator('#sharePublication')).to_contain_text('local only')
            expect(page.locator('#copyShare')).to_be_disabled()
            expect(page.locator('#sharePlatforms')).to_be_hidden()
            expect(page.locator('#saveShare')).to_be_enabled()
            with page.expect_download() as saved:
                page.locator('#saveShare').click()
            assert saved.value.suggested_filename=='Spinning-Top-local.png'
            assert not errors,errors
            context.close()
            context=browser.new_context(java_script_enabled=False)
            page=context.new_page(); page.goto(url+route)
            expect(page.locator('#introSource')).to_be_visible()
            expect(page.locator('#sharedTextCredit')).to_be_visible()
            expect(page.locator('#sharedTextCredit')).to_contain_text('CC BY-SA 4.0')
            expect(page.locator('#yearChip')).to_be_visible()
            context.close(); browser.close()
    finally:
        server.shutdown(); server.server_close()
        application.extensions['library'].pool.shutdown()
