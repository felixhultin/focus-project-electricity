"""Exercise a compressed release locally or at its public Pages URL."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--site',type=Path)
parser.add_argument('--url')
args=parser.parse_args();server=None
if args.url:base=args.url.rstrip('/')
else:
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(args.site.resolve())))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for model in ['sv-l38bi','sv-ml38bi']:
            page=browser.new_page(viewport=dict(width=1440,height=1000))
            page.set_default_timeout(90000)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/clusters.html?model=llamadictionary-'+model+'-local--qwen3-8b--guide-v2&word=str%C3%B6m')
            page.wait_for_function('current()?.encoder_model==="Qwen/Qwen3-Embedding-8B" && document.getElementById("loading").textContent===""')
            assert model in page.locator('#model').input_value()
            for corpus in ['tkr','kubhist','kubhist2','lb']:
                page.select_option('#corpus',corpus)
                page.wait_for_function('(c)=>current()?.corpus===c && document.getElementById("loading").textContent===""',arg=corpus)
                assert page.locator('#rows mark').count()>0
                assert page.evaluate('scoped.length===current().manifest.usage_counts["ström"]')
            page.close()
        page=browser.new_page(viewport=dict(width=1440,height=1000));page.set_default_timeout(90000)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/associations.html?word=str%C3%B6m&corpus=kubhist2&resource=aftonbladet&measure=cooccurrence&minimum=1')
        page.wait_for_selector('#chart .point')
        assert page.locator('#resource').input_value()=='aftonbladet'
        assert 'Aftonbladet' in page.locator('#chartTitle').text_content()
        page.select_option('#measure','similarity')
        assert page.locator('#chart .point').count()>0
        assert 'Cosine' in page.locator('#scoreHeading').text_content()
        page.locator('#chart .point').first.press('Enter')
        assert page.locator('#selection').is_visible()
        page.screenshot(path='/tmp/mats-pages-release-desktop.png')
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path='/tmp/mats-pages-release-mobile.png')
        page.goto(base+'/mia/index.html');assert page.locator('h1').count()>0
        assert not errors,errors
        browser.close()
    print('Release browser checks passed: both Qwen generators, all four corpora, packed newspaper data, both measures, excerpts and Mia landing page.')
finally:
    if server:server.shutdown();server.server_close()
