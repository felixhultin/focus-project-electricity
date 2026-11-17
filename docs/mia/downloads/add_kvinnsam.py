#!/usr/bin/env python3
"""Add Kvinnsam JSONL exports to an existing Mia static-site build, without Korp requests."""
import argparse
from collections import Counter, defaultdict
import csv
from html import escape
import json
from pathlib import Path
import random
import re
import shutil
from urllib.parse import quote, unquote, urlsplit

from build_mia_examples import excerpt, decade
from korp_mia_frequencies import draw_plot, write_csv, RESOURCES

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
WORKSPACE = HERE.parents[3]
RESOURCE = 'kvinnsam'
LIMIT = 100


def public_url(value):
    """Expose only web URLs; recover the public host from the export's local mirror."""
    if not value:return None
    parsed = urlsplit(value)
    if parsed.scheme in ('http', 'https') and parsed.hostname:
        return value
    marker = '/files.ub.gu.se/'
    if parsed.scheme == 'file' and marker in parsed.path:
        return 'https://files.ub.gu.se/' + quote(unquote(parsed.path.split(marker, 1)[1]), safe='/')
    return None


def collect(source):
    counts, journals, years, linked = Counter(), Counter(), Counter(), Counter()
    samples, seen, words = defaultdict(list), Counter(), set()
    invalid_spans = 0
    files = sorted(source.rglob('*.jsonl'))
    if not files:raise ValueError(f'No Kvinnsam JSONL files found: {source}')
    randomizer = random.Random(42)
    for index, path in enumerate(files):
        suffix = '_target_usages'
        if not path.stem.endswith(suffix):raise ValueError(f'Unexpected filename: {path.name}')
        expected = path.stem[len(path.parent.name)+1:-len(suffix)]
        words.add(expected)
        with path.open(encoding='utf-8') as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():continue
                row = json.loads(line)
                word = row.get('target') or row.get('lemma')
                if word != expected:raise ValueError(f'Target differs from filename: {path.name}:{line_number}')
                journal = row.get('resource') or path.parent.name
                if journal != path.parent.name:raise ValueError(f'Journal differs from directory: {path.name}:{line_number}')
                text = row['text']; start, end = int(row['start']), int(row['end'])
                valid = 0 <= start < end <= len(text)
                invalid_spans += not valid
                when = str(row.get('date') or '')
                # Keep missing/unusable dates visible in the undated example bucket.
                year = when[:4] if re.match(r'^[12]\d{3}(?:-|$)', when) else None
                dec = decade(when) if year else 'undated'
                key = (word, dec)
                counts[key] += 1; journals[(word, journal, dec)] += 1
                if year:years[(word, year)] += 1
                url = public_url(row.get('url'))
                linked[key] += bool(url)
                before, hit, after = excerpt(text, str(start), str(end))
                sample = [when, journal, before, hit, after, url]
                seen[key] += 1
                if len(samples[key]) < LIMIT:samples[key].append(sample)
                else:
                    choice = randomizer.randrange(seen[key])
                    if choice < LIMIT:samples[key][choice] = sample
        if (index+1) % 100 == 0:print(f'Read {index+1}/{len(files)} files; {sum(counts.values()):,} matches', flush=True)
    return dict(counts=counts,journals=journals,years=years,linked=linked,samples=samples,
                words=words,invalid_spans=invalid_spans,files=len(files))


def build(source, site=SITE):
    data = collect(source)
    if not data['counts']:raise ValueError('Kvinnsam export contains no matches')
    destination = site/'example_data'
    manifest = json.loads((destination/'manifest.json').read_text())
    source_data = json.loads((site/'data/source_breakdown.json').read_text())
    corpora = manifest['corpora']
    for journal in sorted({journal for _,journal,_ in data['journals']}):
        name = 'Kvinnsam · ' + journal
        if name not in corpora:corpora.append(name)
    manifest['buckets'] = [b for b in manifest['buckets'] if b['resource'] != RESOURCE]
    for (word, dec), count in sorted(data['counts'].items()):
        folder = destination/word/RESOURCE/dec
        folder.mkdir(parents=True, exist_ok=True)
        rows = [[when, corpora.index('Kvinnsam · '+journal), before, hit, after, url]
                for when,journal,before,hit,after,url in data['samples'][(word,dec)]]
        (folder/'0.json').write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')))
        manifest['buckets'].append(dict(word=word,resource=RESOURCE,decade=dec,count=count,
            sample_count=len(rows),with_source_url=data['linked'][(word,dec)]))
    manifest['buckets'].sort(key=lambda b:(b['word'],b['resource'],b['decade']))
    manifest['words'] = sorted(set(manifest['words']) | data['words'])
    manifest['resources'] = list(dict.fromkeys(manifest['resources']+[RESOURCE]))
    manifest['all_rows'][RESOURCE] = sum(data['counts'].values())
    manifest['without_source_url'][RESOURCE] = sum(data['counts'].values())-sum(data['linked'].values())
    manifest['dataset'] = 'the Mia workbooks and Kvinnsam journal exports'
    manifest['resource_labels'] = {RESOURCE:'Kvinnsam journals'}
    manifest['resource_notes'] = {RESOURCE:'Exact exported matches; no Korp API comparison or corpus token totals are available. Up to 100 excerpts per word and decade are selected with seed 42.'}
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
    source_data['words'] = manifest['words']
    source_data['kvinnsam'] = [[word,journal,dec,count] for (word,journal,dec),count in sorted(data['journals'].items())]
    (site/'data/source_breakdown.json').write_text(json.dumps(source_data,ensure_ascii=False,separators=(',',':')))
    write_csv(site/'data/kvinnsam_yearly_matches.csv',('year','resource','target','exported_matches'),
        ((year,RESOURCE,word,n) for (word,year),n in sorted(data['years'].items())))
    write_csv(site/'data/kvinnsam_decade_matches.csv',('decade','resource','target','exported_matches'),
        ((dec,RESOURCE,word,n) for (word,dec),n in sorted(data['counts'].items())))
    provenance = dict(resource=RESOURCE,input_format='JSONL target-usage exports',files=data['files'],
        journals=sorted({journal for _,journal,_ in data['journals']}),targets=sorted(data['words']),
        exported_matches=sum(data['counts'].values()),invalid_target_spans=data['invalid_spans'],
        undated_matches=sum(n for (_,dec),n in data['counts'].items() if dec=='undated'),
        token_denominators_available=False,sample_limit=LIMIT,sample_seed=42,
        date_basis='Exported date field; missing or invalid years remain undated.',
        count_basis='One match per supplied JSONL record; counts describe the export, not an independently verified complete corpus.',
        source_urls='Public files.ub.gu.se image URLs reconstructed from the local mirror paths; private paths are not published.')
    (site/'data/kvinnsam_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    plots(site, manifest['words'], data)
    integrate_pages(site)
    for template,page in [('mats_examples_viewer.html','examples.html'),('source_breakdown_viewer.html','source-breakdown.html')]:
        shutil.copyfile(HERE/template, site/page)
    print(f'Added {provenance["exported_matches"]:,} Kvinnsam matches from {len(provenance["journals"])} journals and {len(data["words"])} terms to {site}',flush=True)
    return provenance


def plots(site, words, data):
    decades, values = defaultdict(set), {}
    with (site/'data/decade_frequencies.csv').open() as stream:
        for row in csv.DictReader(stream):
            dec=int(row['decade']);resource=row['resource']
            if resource not in RESOURCES:continue
            decades[resource].add(dec)
            values[(dec,resource,row['target'])]=(int(row['absolute']),int(row['tokens']),float(row['per_million']) if row['per_million'] else None)
    for (word,dec),count in data['counts'].items():
        if dec!='undated':
            decades[RESOURCE].add(int(dec));values[(int(dec),RESOURCE,word)]=(count,0,None)
    if not decades[RESOURCE]:raise ValueError('No dated Kvinnsam matches to plot')
    periods={resource:list(range(min(periods),max(periods)+1,10)) for resource,periods in decades.items()}
    for word in words:
        draw_plot(site/'targets'/(word+'.svg'),word,periods,values,{},resources=(*RESOURCES,RESOURCE))


def integrate_pages(site):
    index=site/'index.html';content=index.read_text()
    content=content.replace('Mia · Korp frequencies for each term','Mia · frequencies for each term').replace('Mia · Korp word frequencies','Mia · word frequencies')
    notice='<p id="kvinnsam-note">Kvinnsam adds matches from seven digitized journals. Its plots show exact exported-match counts; per-million rates are unavailable because corpus token totals were not supplied. Undated matches remain accessible in the example browser.</p>'
    content=re.sub(r'<p id="kvinnsam-note">.*?</p>','',content,flags=re.S)
    content=content.replace('<nav aria-label="Target words">',notice+'<nav aria-label="Target words">',1) if '<nav aria-label="Target words">' in content else content.replace('<div class="word-picker">',notice+'<div class="word-picker">',1)
    content=content.replace('aspect-ratio:1600/940','aspect-ratio:1600/1190')
    # Keep original anchors stable while appending any terms unique to Kvinnsam.
    known={name for name in re.findall(r'<h2>(.*?)</h2>',content)}
    manifest=json.loads((site/'example_data/manifest.json').read_text())
    identifiers=[int(n) for n in re.findall(r'<section id="word-(\d+)"',content)]
    next_id=max(identifiers,default=-1)+1
    for word in manifest['words']:
        if escape(word) in known:continue
        section=f'<section id="word-{next_id}"><h2>{escape(word)}</h2><p><a href="examples.html?word={quote(word)}">Examples</a></p><object data="targets/{quote(word)}.svg" type="image/svg+xml" aria-label="Frequencies for {escape(word,quote=True)}"></object></section>'
        content=content.replace('</html>',section+'</html>',1);next_id+=1
    # Compact Mia navigation and word selector without electricity cluster links.
    cluster_link='<a href="clusters.html">Model clusters</a> · ' if (site/'clusters.html').exists() else ''
    content=re.sub(r'<p class="site-links">.*?</p>','<p class="site-links">'+cluster_link+'<a href="examples.html">Examples</a> · <a href="source-breakdown.html">Authors, newspapers and journals</a> · <a href="methodology.html">Method and sources</a></p>',content,flags=re.S)
    entries=re.findall(r'<section id="(word-\d+)"><h2>(.*?)</h2>',content)
    picker='<div class="word-picker"><label for="word-select">Term</label> <select id="word-select">'+''.join(f'<option value="{identifier}">{word}</option>' for identifier,word in entries)+'</select></div>'
    content=re.sub(r'<nav aria-label="Target words">.*?</nav>',lambda _:picker,content,flags=re.S)
    content=re.sub(r'<div class="word-picker">.*?</div>',lambda _:picker,content,flags=re.S)
    content=re.sub(r'<a href="targets/[^"<>]+">Open SVG</a>','',content)
    if '../assets/word-selector.js' not in content:content=content.replace('</html>','<script src="../assets/word-selector.js"></script></html>')
    if 'id="mia-picker-style"' not in content:content=content.replace('</style>','</style><style id="mia-picker-style">.word-picker{display:flex;gap:.7rem;align-items:center;margin:1.5rem 0}.word-picker select{font:inherit;padding:.5rem;max-width:100%}section[hidden]{display:none}</style>',1)
    index.write_text(content)
    method=site/'methodology.html';content=method.read_text()
    content=re.sub(r'<section id="kvinnsam-method">.*?</section>','',content,flags=re.S)
    content=content.replace('</html>','<section id="kvinnsam-method"><h2>Kvinnsam journals</h2><p>The supplied target-usage exports cover Dagny, Framåt, Hertha, Idun, Morgonbris, Tidevarvet and Tidskrift för hemmet. Each JSONL record counts as one exported match. Dates come from the export metadata; undated matches remain visible in the example browser but do not appear in dated plots.</p><p>All exported records contribute to counts. The example browser keeps a deterministic reservoir sample of up to 100 excerpts per term and decade (seed 42). Journal breakdowns use every record. Kvinnsam has no supplied corpus token totals or corresponding Korp API counts, so no per-million rate or API difference is calculated. Source links open public page images from files.ub.gu.se.</p></section></html>')
    method.write_text(content)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=WORKSPACE/'target_usages/kvinnsam_target_usages')
    parser.add_argument('--site',type=Path,default=SITE)
    args=parser.parse_args();build(args.source.resolve(),args.site.resolve())
