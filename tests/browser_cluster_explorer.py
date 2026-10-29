"""Optional real-browser checks: requires Playwright and headless Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from collections import Counter
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'docs')))
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
base=f'http://127.0.0.1:{server.server_port}'
errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/clusters.html?word=str%C3%B6m')
        page.wait_for_function('current() && document.getElementById("loading").textContent === ""')
        assert page.locator('#model option:not([disabled])').count()==page.evaluate('new Set(catalog.map(d=>d.pipeline_id)).size')
        assert page.locator('#model').locator('option:checked').inner_text().find('MPNet')>=0
        if page.locator('#model option[value="t5-xl--mpnet"][disabled]').count():
            assert 'results pending' in page.locator('#experimentStatus').inner_text()
        assert page.locator('#corpus option').count()==4
        assert '?v=' in page.locator('script[src*="cluster-explorer.js"]').get_attribute('src')
        assert page.locator('#lemma').input_value()=='ström'
        assert page.locator('#rows mark').count()>0
        assert page.locator('#clusterOverview').is_visible()
        synthetic_summary=page.evaluate("""[...summarizeClusters([
            {cluster:0,definition:'  Electric current  ',year:1901},
            {cluster:0,definition:'Electric current',year:1902},
            {cluster:0,definition:'Flow of water',year:null},
            {cluster:1,definition:'<script>unsafe</script>',year:1910}
        ]).values()]""")
        assert synthetic_summary[0]['definitions'][0]==['Electric current',2]
        assert synthetic_summary[0]['n']==3
        assert synthetic_summary[0]['firstYear']==1901
        assert synthetic_summary[0]['lastYear']==1902
        assert page.evaluate("document.getElementById('clusterOverview').compareDocumentPosition(document.getElementById('chart')) & Node.DOCUMENT_POSITION_FOLLOWING")
        assert page.evaluate("document.querySelectorAll('[data-summary-cluster]').length===new Set(scoped.map(r=>r.cluster)).size")
        assert page.evaluate("[...document.querySelectorAll('.representative')].every(node=>scoped.some(row=>row.definition.replace(/\\s+/g,' ').trim()===node.textContent))")
        page.locator('[data-summary-cluster]').first.click()
        assert page.evaluate('filtered.length>0 && filtered.every(r=>String(r.cluster)===document.getElementById("cluster").value)')
        page.click('#reset')
        for corpus in ['tkr','kubhist','kubhist2','lb']:
            page.select_option('#corpus',corpus)
            page.wait_for_function('(c)=>current() && current().corpus===c && document.getElementById("loading").textContent===""',arg=corpus)
            assert page.locator('#chart rect').count()>0
            assert page.locator('#rows tr').count()>0
            expected=Counter(page.evaluate('scoped.map(r=>r.year)'))
            actual=page.locator('#chart .year-bin').evaluate_all('nodes=>nodes.map(node=>[node.dataset.year,Number(node.dataset.count)])')
            assert sum(n for year,n in actual)==sum(expected.values())
            assert all(n==expected[int(year)] for year,n in actual)
            years=[int(year) for year,n in actual]
            assert years==list(range(min(expected),max(expected)+1))
            assert page.locator('#metric option[value="share"]').inner_text()=='Share within year'
            assert page.locator('#chart svg').evaluate('node=>node.getBoundingClientRect().width')>=46*len(years)
        synthetic=page.evaluate("buildYearBins([{year:1901,cluster:0},{year:1909,cluster:0},{year:null,cluster:0}],[0]).map(b=>[b.year,b.n])")
        assert synthetic==[[year,1 if year in (1901,1909) else 0] for year in range(1901,1910)]+[['Unknown',1]]
        # Shared IDs are advertised only when the active manifest establishes them.
        original_shared=page.evaluate('current().manifest.shared_clustering || null')
        page.evaluate('current().manifest.shared_clustering={run_id:"test",corpora:["tkr","lb"],weighting:"Each sampled usage contributes once."};render();')
        assert 'Shared clustering across TKR, LB' in page.locator('#samplingNote').inner_text()
        assert 'IDs are local' not in page.locator('#samplingNote').inner_text()
        page.evaluate('(value)=>{if(value)current().manifest.shared_clustering=value;else delete current().manifest.shared_clustering;render();}',original_shared)
        # Failed definition counts must be visible, not hidden by the sampling cap.
        original_coverage=page.evaluate('current().manifest.definition_coverage || null')
        page.evaluate('current().manifest.definition_coverage={source_usage_count:30,usable_definition_count:28,empty_definition_count:2};render();')
        assert '28 of 30 sampled usages' in page.locator('#samplingNote').inner_text()
        assert '2 remained empty' in page.locator('#samplingNote').inner_text()
        assert 'yearly balance can be affected' in page.locator('#samplingNote').inner_text()
        page.evaluate('(value)=>{if(value)current().manifest.definition_coverage=value;else delete current().manifest.definition_coverage;render();}',original_coverage)
        # Sampling notices must follow the dataset, not merely the yearly axis.
        original_sampling=page.evaluate('current().manifest.sampling || null')
        page.evaluate('current().manifest.sampling={sampling_period:"year",per_word_year_cap:30};render();')
        assert 'per word per year' in page.locator('#samplingNote').inner_text()
        assert 'per decade' not in page.locator('#samplingNote').inner_text()
        page.evaluate('(value)=>{if(value)current().manifest.sampling=value;else delete current().manifest.sampling;render();}',original_sampling)
        # The corpus selector must match completed datasets for XL.
        page.select_option('#model','xl-lexeme')
        page.wait_for_function('current() && current().method==="usages" && document.getElementById("loading").textContent===""')
        assert page.locator('#corpus option').count()==page.evaluate('catalog.filter(d=>d.pipeline_id===current().pipeline_id).length')
        assert not page.locator('#clusterOverview').is_visible()
        assert page.locator('#clusterCards').inner_html()==''
        assert not page.locator('.definition-header').is_visible()
        assert not page.locator('#rows .definition').first.is_visible()
        assert page.locator('#rows mark').count()>0
        expected=Counter(page.evaluate('scoped.map(r=>r.year)'))
        actual=page.locator('#chart .year-bin').evaluate_all('nodes=>nodes.map(node=>[node.dataset.year,Number(node.dataset.count)])')
        assert all(n==expected[int(year)] for year,n in actual)
        page.locator('#chart rect').first.press('Enter')
        assert page.locator('#cluster').input_value()!='all'
        assert page.evaluate('filtered.every(r=>String(r.cluster)===document.getElementById("cluster").value)')
        page.click('#reset')
        page.fill('#query','unlikelyNoMatchZXCV')
        assert page.locator('#rows tr').count()==0
        page.click('#reset')
        page.goto(base+'/clusters.html?model=xl-lexeme&corpus=lb&word=str%C3%B6m&from=1900&to=1919&metric=count')
        page.wait_for_function('current() && document.getElementById("loading").textContent===""')
        assert page.locator('#from').input_value()=='1900'
        assert page.locator('#to').input_value()=='1919'
        assert page.evaluate('scoped.length>0 && scoped.every(r=>r.year>=1900&&r.year<=1919)')
        assert page.locator('#metric').input_value()=='count'
        page.select_option('#model','llm-wsd')
        page.wait_for_function('current() && current().method==="definitions" && document.getElementById("loading").textContent===""')
        assert page.locator('#clusterOverview').is_visible()
        assert page.locator('.definition-header').is_visible()
        page.click('#reset')
        # Two encoders for one generator must remain distinct selectable datasets.
        original_pipeline=page.evaluate('current().pipeline_id')
        page.evaluate("""()=>{
            const data=structuredClone(current());
            data.pipeline_id='browser-test-combination';data.model_alias=data.pipeline_id;
            data.id=data.pipeline_id+'--'+data.corpus;data.encoder_model='test/other-encoder';
            data.pipeline_label=data.model_label+' + other encoder';
            const entry={...catalog.find(d=>d.id===current().id),...data,usage_count:data.rows.length};
            delete entry.rows;catalog.push(entry);dataCache.set(data.id,data);
            document.getElementById('model').add(new Option(data.pipeline_label,data.pipeline_id));
        }""")
        page.select_option('#model','browser-test-combination')
        page.wait_for_function('current() && current().pipeline_id==="browser-test-combination" && document.getElementById("loading").textContent===""')
        assert page.evaluate('current().encoder_model==="test/other-encoder"')
        assert 'browser-test-combination' in page.url
        page.select_option('#model',original_pipeline)
        page.wait_for_function('(pipeline)=>current() && current().pipeline_id===pipeline && document.getElementById("loading").textContent===""',arg=original_pipeline)
        page.evaluate("catalog=catalog.filter(d=>d.pipeline_id!=='browser-test-combination');document.querySelector('#model option[value=browser-test-combination]').remove();")
        page.screenshot(path='/tmp/electricity-clusters-desktop.png' ,full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Mobile layout overflows viewport'
        page.screenshot(path='/tmp/electricity-clusters-mobile.png',full_page=True)
        # Main frequency navigation carries the selected word into the explorer.
        page.goto(base+'/index.html')
        assert page.locator('#word-select option').count()==25
        assert page.locator('nav[aria-label="Target words"] a').count()==0
        assert page.locator('a[href$=".csv"]').count()==0
        assert page.locator('a[href="mia/"]').count()==0
        assert page.locator('section:visible').count()==1
        word_option=page.locator('#word-select option').filter(has_text='ström').all()
        exact=next(option for option in word_option if option.inner_text()=='ström')
        page.select_option('#word-select',exact.get_attribute('value'))
        assert page.locator('section:visible h2').inner_text()=='ström'
        assert 'word=str' in page.url
        page.reload()
        assert page.locator('section:visible h2').inner_text()=='ström'
        link=page.locator('a[href="clusters.html?word=str%C3%B6m"]').first
        link.click()
        page.wait_for_function('current() && document.getElementById("loading").textContent===""')
        assert page.locator('#lemma').input_value()=='ström'
        assert not errors,errors
        browser.close()
    print('Browser checks passed: definition summaries, cluster selection, yearly counts and gaps, model/corpus availability, deep links, filters, keyboard chart selection, compact navigation, word dropdown, mobile layout, and site navigation.')
finally:
    server.shutdown()
    server.server_close()
