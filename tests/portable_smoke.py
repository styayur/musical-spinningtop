"""Two real build outputs under strict mounts; personal HTML normalization is simulated."""
import argparse
import hashlib
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment import get_deployment


def records(page):
    return page.evaluate("""async()=>{const db=await new Promise((res,rej)=>{const r=indexedDB.open('musical-spinningtop-v2',1);r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)});const out={};for(const n of ['daily','cycles'])out[n]=await new Promise(res=>{const r=db.transaction(n).objectStore(n).getAll();r.onsuccess=()=>res(r.result)});db.close();return out}""")


class MountHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, config, directory, **kwargs):
        self.config=config
        super().__init__(*args,directory=str(directory),**kwargs)

    def do_GET(self):
        path=urlsplit(self.path).path
        base=self.config.base_path
        if path==base.rstrip('/'):
            self.send_response(308);self.send_header('Location',base);self.end_headers();return
        if not path.startswith(base):
            self.send_error(404);return
        tail=path[len(base):]
        if self.config.target=='personal' and tail.startswith('works/'):
            canonical=path.rstrip('/')
            if canonical.endswith('.html'): canonical=canonical[:-5]
            if canonical!=path:
                self.send_response(308);self.send_header('Location',canonical);self.end_headers();return
            tail += '.html'
        file=Path(self.directory)/(tail or 'index.html')
        if not file.is_file():
            self.send_response(404);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
            self.wfile.write((Path(self.directory)/'404.html').read_bytes());return
        self.path='/'+(tail or 'index.html')
        super().do_GET()

    def end_headers(self):
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; connect-src 'self'; base-uri 'self'; object-src 'none'")
        super().end_headers()

    def log_message(self,*_):
        pass


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def run(github,personal,report_path):
    outputs={'github':github,'personal':personal}
    inventories={name:inventory(path) for name,path in outputs.items()}
    assert inventories['github'].keys()==inventories['personal'].keys()
    differences=[name for name in inventories['github'] if inventories['github'][name]!=inventories['personal'][name]]
    allowed={'index.html','404.html','data/share-index.json','deployment.json','build-manifest.json','build-metrics.json'}
    assert all(name in allowed or name.startswith('works/') for name in differences),differences
    for suffix in ('.svg','.png','.js','.css'):
        assert all(inventories['github'][name]==inventories['personal'][name] for name in inventories['github'] if name.endswith(suffix))
    report={'files_per_target':len(inventories['github']),'different_files':sorted(differences),
            'identical_svg_count':sum(name.endswith('.svg') for name in inventories['github']),
            'identical_png_count':sum(name.endswith('.png') for name in inventories['github']),
            'same_core_js_css_catalog_ids':True,'targets':{},
            'scope':'Local strict HTTP mounts and simulated Cloudflare HTML normalization; no live personal deployment.'}
    servers=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            shared_context=browser.new_context()
            previous=None
            for target,output in outputs.items():
                config=get_deployment(target)
                server=ThreadingHTTPServer(('127.0.0.1',0),partial(MountHandler,config=config,directory=output))
                servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
                origin=f'http://127.0.0.1:{server.server_port}'
                home=origin+config.base_path
                index=json.loads((output/'data/share-index.json').read_text(encoding='utf-8'))
                context=browser.new_context(locale='en-US')
                errors=[];context.on('weberror',lambda error:errors.append(str(error)))
                page=context.new_page();page.goto(home.rstrip('/'),wait_until='networkidle')
                assert page.url==home
                expect(page.locator('#card')).to_have_attribute('aria-busy','false')
                daily=page.locator('#card').get_attribute('data-id')
                for button in (None,'randomBtn','prevBtn'):
                    if button: page.locator('#'+button).click()
                    expect(page.locator('#card')).to_have_attribute('aria-busy','false')
                    identity=page.locator('#card').get_attribute('data-id')
                    page.locator('#shareBtn').click();expect(page.locator('#copyShare')).to_be_enabled()
                    public=page.locator('#shareLink').input_value()
                    assert public==config.public_url(identity)
                    for name,param in [('shareX','url'),('shareFacebook','u'),('shareThreads','url')]:
                        assert parse_qs(urlsplit(page.locator('#'+name).get_attribute('href')).query)[param]==[public]
                    assert public in parse_qs(urlsplit(page.locator('#shareWhatsApp').get_attribute('href')).query)['text'][0]
                    with page.expect_download() as saved: page.locator('#saveShare').click()
                    assert saved.value.failure() is None
                    page.keyboard.press('Escape')
                saved_records=records(page)
                page.reload(wait_until='networkidle')
                page.locator('#todayBtn').click();expect(page.locator('#card')).to_have_attribute('data-id',daily)
                assert records(page)==saved_records
                # Exact current origin/path/id only, including PNG directory boundaries.
                selected=page.locator('#card').get_attribute('data-id')
                original=index[selected]
                for malicious in (original['url']+'?track=1',original['url']+'#fragment',
                                  original['url'].replace(config.public_origin,'https://evil.example'),
                                  config.public_url('different:id')):
                    page.route('**/data/share-index.json',lambda route,request,bad=malicious:route.fulfill(json={selected:{**original,'url':bad}}))
                    page.locator('#shareBtn').click();expect(page.locator('#shareStatus')).to_contain_text('could not load')
                    expect(page.locator('#copyShare')).to_be_disabled();page.keyboard.press('Escape')
                    page.unroute('**/data/share-index.json')
                for image in ('https://evil.example/'+ 'a'*64+'.png','/elsewhere/'+'a'*64+'.png',
                              './static/share/'+'a'*64+'.png?x=1','./static/share/%61'+'a'*63+'.png'):
                    assert not page.evaluate('(value)=>spinningTopDeployment.safeImage(value)',image)
                page.route('**/data/site-catalog.json',lambda route:route.abort())
                page.reload(wait_until='networkidle');expect(page.locator('#card')).to_have_attribute('data-id',daily)
                assert records(page)==saved_records
                context.close()

                identity,info=next(iter(index.items()))
                path=urlsplit(info['url']).path
                for alias in ([path] if target=='github' else [path,path+'/',path+'.html']):
                    context=browser.new_context(java_script_enabled=False)
                    page=context.new_page();response=page.goto(origin+alias,wait_until='networkidle')
                    assert response.status==200
                    assert page.locator('link[rel="canonical"]').get_attribute('href')==info['url']
                    assert page.locator('meta[property="og:url"]').get_attribute('content')==info['url']
                    assert page.locator('meta[property="og:image"]').get_attribute('content').startswith(config.public_base+'static/share/')
                    expect(page.locator('#sharedTextCredit')).to_be_visible()
                    context.close()
                context=browser.new_context();page=context.new_page();page.goto(origin+path,wait_until='networkidle')
                expect(page.locator('#card')).to_have_attribute('data-id',identity)
                assert records(page)=={'daily':[],'cycles':[]}
                old_url=page.url;old_title=page.title()
                page.evaluate("() => {window.originalRequest=spinningTopStatic.request; spinningTopStatic.request=async()=>{throw new Error('controlled failure')}}")
                page.locator('#randomBtn').click();expect(page.locator('#retryBtn')).to_be_visible()
                assert page.url==old_url and page.title()==old_title
                assert page.locator('link[rel="canonical"]').get_attribute('href')==info['url']
                assert records(page)=={'daily':[],'cycles':[]}
                page.evaluate('() => {spinningTopStatic.request=window.originalRequest}')
                page.locator('#retryBtn').click();expect(page.locator('#sharedNotice')).to_be_hidden()
                assert page.url==home
                assert page.locator('link[rel="canonical"]').get_attribute('href')==config.public_base
                assert page.locator('meta[property^="og:"]').count()==0
                assert records(page)['daily']==[]
                before=records(page)
                response=page.goto(home+'works/unknown',wait_until='networkidle');assert response.status==404
                expect(page.locator('#sharedNotice')).to_be_visible()
                assert page.locator('meta[name="robots"]').get_attribute('content')=='noindex'
                assert records(page)==before
                assert context.request.get(origin+'/static/app.js').status==404
                assert context.request.get(home+'static/missing.js').status==404
                # A valid missing SVG falls back without selecting another work.
                page.route('**/static/artwork/*.svg*',lambda route:route.continue_() if '/base.svg' in route.request.url else route.fulfill(status=404,body='missing'))
                page.goto(origin+path,wait_until='networkidle')
                expect(page.locator('#artwork')).to_have_attribute('data-artwork-state','fallback')
                expect(page.locator('#card')).to_have_attribute('data-id',identity)
                assert records(page)==before
                context.close()
                # Different origins keep the existing storage namespace independent.
                probe=shared_context.new_page();probe.goto(origin+path,wait_until='networkidle')
                assert records(probe)=={'daily':[],'cycles':[]}
                if previous:
                    old_page,old_records=previous
                    assert records(old_page)==old_records
                probe.locator('#todayBtn').click();expect(probe.locator('#sharedNotice')).to_be_hidden()
                previous=(probe,records(probe))
                assert not errors,errors
                report['targets'][target]={'passed':True,'public_base':config.public_base,'strict_mount':True,'csp_self_scripts':True,
                    'history_and_offline_cache':True,'url_security_negative_cases':True,'no_js_metadata':True,'aliases':len([path] if target=='github' else [path,path+'/',path+'.html'])}
            shared_context.close();browser.close()
    finally:
        for server in servers: server.shutdown();server.server_close()
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='different_files'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--github',type=Path,default=ROOT/'_site')
    parser.add_argument('--personal',type=Path,default=ROOT/'artifacts/portable/personal')
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/portable/comparison.json')
    args=parser.parse_args();run(args.github,args.personal,args.report)
