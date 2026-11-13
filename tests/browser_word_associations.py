"""Run with Playwright available; tests real samples and a controlled similarity fixture."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def copyfile(self,source,outputfile):
        try:super().copyfile(source,outputfile)
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
        page.goto(base+'/associations.html?word=str%C3%B6m&measure=cooccurrence')
        page.wait_for_selector('#chart .point')
        assert page.locator('#word').input_value()=='ström'
        assert page.locator('#corpus option').count()==4
        for corpus in ['tkr','kubhist','kubhist2','lb']:
            page.select_option('#corpus',corpus)
            page.wait_for_function('(c)=>document.querySelector("#chartTitle").textContent.includes(" · "+c.toUpperCase()+" · ") && !document.querySelector("#word").disabled',arg=corpus)
            assert page.locator('#chart .point').count()>0
            assert page.locator('#values tr').count()==page.locator('#chart .point').count()
            page.select_option('#measure','similarity')
            assert page.locator('#chart .point').count()>0
            assert page.locator('#scoreHeading').text_content()=='Cosine similarity'
            assert '%' not in page.locator('#values').text_content()
            page.select_option('#measure','cooccurrence')
            page.locator('#chart .point').first.press('Enter')
            assert page.locator('#selection').is_visible()
            assert page.locator('#passages .passage').count()>0
            page.click('#clear')
        page.goto(base+'/associations.html?word=str%C3%B6m&corpus=tkr&measure=similarity')
        page.wait_for_selector('#chart .point')
        page.screenshot(path='/tmp/mats-word-associations-desktop.png',full_page=True)
        page.set_viewport_size(dict(width=390,height=844))
        page.screenshot(path='/tmp/mats-word-associations-mobile.png',full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.goto(base+'/index.html')
        assert page.locator('a[href="associations.html"]').count()==1
        page.goto(base+'/clusters.html')
        assert page.locator('a[href="associations.html"]').count()==1

        # Resource deep links and switching load separately calculated paper data.
        page.set_viewport_size(dict(width=1440,height=1100))
        page.goto(base+'/associations.html?word=str%C3%B6m&corpus=kubhist2&resource=aftonbladet&measure=cooccurrence&minimum=1')
        page.wait_for_function('!document.querySelector("#word").disabled && document.querySelector("#chartTitle").textContent.includes("Aftonbladet")')
        assert page.locator('#resource').input_value()=='aftonbladet'
        assert page.locator('#resource option').count()>2
        assert 'not separately balanced' in page.locator('#resourceNote').text_content()
        parent=page.request.get(base+'/data/associations/kubhist2/manifest.json').json()
        entry=next(r for r in parent['resources'] if r['id']=='aftonbladet')
        submeta=page.request.get(base+'/'+entry['data']).json()
        subdata=page.request.get(base+'/'+submeta['files']['ström']).json()
        assert submeta['embedding_status']=='ready'
        page.select_option('#measure','similarity')
        assert page.locator('#chart .point').count()==sum(min(3,len(r['similarity'])) for r in subdata['years'])
        assert 'Aftonbladet' in page.locator('#chart svg').get_attribute('aria-label')
        page.select_option('#measure','cooccurrence')
        expected=sum(min(3,len(r['cooccurrence'])) for r in subdata['years'])
        assert page.locator('#chart .point').count()==expected
        assert submeta['resource']['id']=='aftonbladet'
        assert all(p['share']==p['count']/r['n'] for r in subdata['years'] for p in r['cooccurrence'])
        if expected:
            page.locator('#chart .point').first.press('Enter')
            assert page.locator('#passages .passage').count()>0
            page.click('#clear')
        page.screenshot(path='/tmp/mats-newspaper-associations.png',full_page=True)
        page.set_viewport_size(dict(width=390,height=844))
        page.screenshot(path='/tmp/mats-newspaper-associations-mobile.png',full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.reload()
        page.wait_for_function('!document.querySelector("#word").disabled && document.querySelector("#chartTitle").textContent.includes("Aftonbladet")')
        assert page.locator('#resource').input_value()=='aftonbladet'
        page.select_option('#resource','all')
        page.wait_for_function('!document.querySelector("#word").disabled && document.querySelector("#chartTitle").textContent.endsWith("All resources")')
        assert 'resource=' not in page.url
        page.select_option('#corpus','lb')
        page.wait_for_function('!document.querySelector("#word").disabled && document.querySelector("#chartTitle").textContent.includes(" · LB · ")')
        assert page.locator('#resource').input_value()=='all'
        assert page.locator('#resource option').count()>1

        # A controlled fixture checks both axes even before background training finishes.
        def metadata(route):
            value=route.fetch().json();value['embedding_status']='ready'
            route.fulfill(json=value)
        page.route('**/data/associations/tkr/manifest.json',metadata)
        def fixture(route):
            value=route.fetch().json()
            if value.get('word')=='ström':
                value['years']=[dict(year=y,n=10,model=dict(training_from=y-2,training_through=y+2,training_contexts=80),
                    cooccurrence=[dict(word='vatten',count=5,share=.5,examples=[dict(text='<script>example</script>',date=str(y),id='test')])],
                    similarity=[dict(word='vatten',count=5,cosine=.75,examples=[])]) for y in [1901,1902]]
            route.fulfill(json=value)
        page.route('**/data/associations/tkr/*.json',lambda route:metadata(route) if route.request.url.endswith('/manifest.json') else fixture(route))
        page.goto(base+'/associations.html?word=str%C3%B6m&corpus=tkr&measure=similarity')
        page.wait_for_selector('#chart .point')
        assert '0.750' in page.locator('#values').text_content(), (page.url,page.locator('#measure').input_value(),page.locator('#values').text_content()[:500])
        page.locator('#chart .point').first.press('Enter')
        assert 'No immediate co-occurrence' in page.locator('#passages').inner_text()
        page.select_option('#measure','cooccurrence')
        assert '50.0%' in page.locator('#values').text_content()
        page.locator('#chart .point').first.press('Enter')
        assert '<script>example</script>' in page.locator('#passages').inner_text()
        assert page.locator('#passages script').count()==0
        page.locator('summary').filter(has_text='Year range and display').click()
        page.fill('#from','1902');page.locator('#from').dispatch_event('change')
        assert page.locator('#chart .point').count()==1
        assert '1901' not in page.locator('#values').text_content()
        page.select_option('#minimum','20')
        assert page.locator('#chart .point').count()==0
        assert 'No associations' in page.locator('#chart').inner_text()
        page.click('#reset')
        assert page.locator('#chart .point').count()==2
        with page.expect_download() as download:page.click('#save')
        saved=download.value
        assert saved.suggested_filename.endswith('.svg')
        assert '<svg' in Path(saved.path()).read_text()
        page.reload();page.wait_for_selector('#chart .point')
        assert page.locator('#measure').input_value()=='cooccurrence'
        assert page.locator('#chart .point').count()==2
        assert not errors,errors
        browser.close()
    print('Association chart browser checks passed (four real corpora + both-measure fixture).')
finally:server.shutdown();server.server_close()
