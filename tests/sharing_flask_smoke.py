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
            page.goto(url+'/works/unknown.html',wait_until='networkidle')
            expect(page.locator('#sharedNotice')).to_be_visible()
            expect(page.locator('#shareBtn')).to_be_disabled()
            assert context.request.get(url+'/api/share?id=local:only').json()=={'available':False,'reason':'not-public'}
            assert not errors,errors
            context.close(); browser.close()
    finally:
        server.shutdown(); server.server_close()
        application.extensions['library'].pool.shutdown()
