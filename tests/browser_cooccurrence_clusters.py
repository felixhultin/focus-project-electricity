"""Real-browser checks for shared co-occurrence clusters and resource filters."""
from collections import Counter
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def copyfile(self,source,destination):
        try:super().copyfile(source,destination)
        except (BrokenPipeError,ConnectionResetError):pass

server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'docs')))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1100))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/clusters.html?model=cooccurrence-tfidf&corpus=kubhist2&word=str%C3%B6m')
        page.wait_for_function('current()?.method==="cooccurrence" && document.getElementById("loading").textContent===""')
        assert page.locator('#corpus option').count()==4
        assert page.locator('#clusterOverview').is_visible()
        assert page.locator('#resourceControl').is_visible()
        assert not page.locator('.definition-header').is_visible()
        assert 'Characteristic words' in page.locator('#clusterCards').text_content()
        assert 'TF–IDF' in page.locator('#samplingNote').text_content()
        assert 'Example:' in page.locator('#clusterCards').text_content()
        run_id=page.evaluate('current().manifest.shared_clustering.run_id')
        for corpus in ['tkr','kubhist','kubhist2','lb']:
            page.select_option('#corpus',corpus)
            page.wait_for_function('(c)=>current()?.corpus===c && document.getElementById("loading").textContent===""',arg=corpus)
            assert page.evaluate('current().manifest.shared_clustering.run_id')==run_id
            assert page.evaluate('scoped.length===current().manifest.usage_counts[document.getElementById("lemma").value]')
            expected=Counter(page.evaluate('scoped.map(r=>r.year)'))
            bins=page.locator('.year-bin').evaluate_all('nodes=>nodes.map(n=>[Number(n.dataset.year),Number(n.dataset.count)])')
            assert all(n==expected[y] for y,n in bins)
            assert sum(n for _,n in bins)==sum(expected.values())
        page.goto(base+'/clusters.html?model=cooccurrence-tfidf&corpus=kubhist2&word=str%C3%B6m&source=aftonbladet')
        page.wait_for_function('current()?.corpus==="kubhist2" && document.getElementById("loading").textContent===""')
        assert page.locator('#resource').input_value()=='aftonbladet'
        assert page.evaluate('scoped.length>0 && scoped.every(r=>r.resource_id==="aftonbladet")')
        assert 'not separately balanced' in page.locator('#samplingNote').text_content()
        assert page.evaluate('scoped.length===current().rows.filter(r=>r.lemma==="ström" && r.resource_id==="aftonbladet").length')
        assert page.evaluate('Object.keys(current().manifest.characteristic_words["ström"]).includes(String(scoped[0].cluster))')
        page.locator('[data-summary-cluster]').first.click()
        assert page.evaluate('filtered.length>0 && filtered.every(r=>String(r.cluster)===document.getElementById("cluster").value && r.resource_id==="aftonbladet")')
        assert page.locator('#rows mark').count()>0
        page.click('#reset')
        assert page.locator('#resource').input_value()=='all'
        page.select_option('#resource','aftonbladet')
        page.fill('#from','1890');page.locator('#from').dispatch_event('change')
        assert page.evaluate('scoped.every(r=>r.year>=1890 && r.resource_id==="aftonbladet")')
        page.reload()
        page.wait_for_function('current()?.method==="cooccurrence" && document.getElementById("loading").textContent===""')
        assert page.locator('#resource').input_value()=='aftonbladet'
        assert page.locator('#from').input_value()=='1890'
        page.screenshot(path='/tmp/mats-cooccurrence-clusters-desktop.png',full_page=True)
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path='/tmp/mats-cooccurrence-clusters-mobile.png',full_page=True)
        # A switch back to a definition model restores definition summaries and columns.
        page.select_option('#model','llm-wsd')
        page.wait_for_function('current()?.method==="definitions" && document.getElementById("loading").textContent===""')
        assert page.locator('.definition-header').is_visible()
        assert page.locator('#clusterOverview').is_visible()
        assert 'generated definition' in page.locator('#overviewNote').text_content()
        assert page.locator('#resourceControl').is_hidden()
        assert not errors,errors
        browser.close()
    print('Co-occurrence cluster browser checks passed: shared IDs, yearly counts, summaries, resources, deep links, filters, mobile and model switching.')
finally:server.shutdown();server.server_close()
