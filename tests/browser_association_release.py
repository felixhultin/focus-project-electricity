"""Check uncapped association data locally or on the deployed Pages site."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--site',type=Path);parser.add_argument('--url')
args=parser.parse_args();server=None
if args.url:base=args.url.rstrip('/')
else:
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(args.site.resolve())))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=1000))
        page.set_default_timeout(90000)
        page.on('pageerror',lambda error:errors.append(str(error)))
        for corpus,total in dict(tkr=382317,kubhist=36625,kubhist2=1245366,lb=126587).items():
            page.goto(base+'/associations.html?word=str%C3%B6m&corpus='+corpus+'&measure=cooccurrence')
            page.wait_for_selector('#chart .point')
            assert 'no yearly cap' in page.locator('#resourceNote').inner_text()
            metadata=page.evaluate('async c=>{const m=await window.siteDataJSON("data/associations/"+c+"/manifest.json");return {sampling:m.sampling,resources:m.resources};}',corpus)
            assert metadata['sampling']['sampled_usages']==total
            assert metadata['sampling']['per_word_year_cap'] is None
            assert metadata['sampling']['selection']=='all_available'
            assert sum(r['sampled_usages'] for r in metadata['resources'])==total
            assert page.locator('#values tr').count()==page.locator('#chart .point').count()
            assert page.locator('#values').text_content()
            page.select_option('#measure','similarity')
            assert page.locator('#chart .point').count()>0
            assert page.locator('#scoreHeading').text_content()=='Cosine similarity'
            resource=next((r for r in metadata['resources'] if r['id']=='aftonbladet'),max(metadata['resources'],key=lambda r:r['sampled_usages']))
            page.select_option('#resource',resource['id'])
            page.wait_for_function('label=>!document.getElementById("word").disabled && document.getElementById("chartTitle").textContent.includes(label)',arg=resource['label'])
            assert 'no yearly cap' in page.locator('#resourceNote').inner_text()
            assert page.locator('#chart .point').count()>0
            page.select_option('#measure','cooccurrence')
            assert page.locator('#chart .point').count()>0
            page.locator('#chart .point').first.press('Enter')
            assert page.locator('#passages .passage').count()>0
            print(corpus,total,'usages;',resource['label'],'resource checked',flush=True)
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path='/tmp/mats-uncapped-associations-mobile.png',full_page=True)
        page.goto(base+'/mia/index.html');assert page.locator('#kvinnsam-note').count()==1
        page.goto(base+'/mia/clusters.html?word=mor')
        page.wait_for_selector('#rows mark')
        assert page.locator('#model option').count()==3
        assert not errors,errors
        browser.close()
    print('Uncapped release browser checks passed: four corpora, both measures, resource subsets, excerpts, mobile and Mia.')
finally:
    if server:server.shutdown();server.server_close()
