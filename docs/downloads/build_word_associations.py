#!/usr/bin/env python3
"""Build yearly co-occurrence shares and temporal Word2Vec neighbours for Mats."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[2]
SITE=HERE.parent
CORPORA=['tkr','kubhist','kubhist2','lb']
TOKEN=re.compile(r'[^\W\d_]+',re.UNICODE)
STOP=set('''och att det den de en ett i på av af till från för med om som är var vara varit voro äro hade har ha få får fick ficko man han hon hans hennes deras dess sig sin sitt sina vi ni du jag mig dig oss er vår vårt våra eder denna detta dessa sådan sådant sådana så här där der dit då nu när hur vad hvem vem hvar vilket vilken vilka hvars ej icke inte men eller utan också även äfven samt än över öfver under genom hos vid mot efter före innan sedan ut upp ned in fram bort igen mellan bland inom utom mycket mer mest mindre minst alla allt alltid aldrig ofta bara endast dock väl nog ju någon något några ingen inget inga annan annat andra samma skall skulle ska kunde kunna kan bör borde blir bli blev blivit göra gör gjorde gjord gjort låta låter måste vilja vill ville under år åren herr herrar fru kap sid sida delen del exempel t ex enligt alltså emedan ty hvarken varken både såväl dels såsom annars egentligen särskilt själf själv ju desto närmare sen senaste först första andra tredje ännu ytterligare omkring omkring ifrån däraf därför derför huru dylika angående beträffande emellertid härvid sålunda alltså ehuru hvarje varje hvilka hvilken hvilket blott huruvida hafva haft hafver komma kommer kom gälla gäller gällde synes sade säger sagdt säga hvarandra andra ene ena ene många flera dessutan dessutom dessförinnan vara äfvensom alltså kunna ganska skulle kunna något'''.split())
SETTINGS=dict(training_context_words_each_side=30,cooccurrence_words_each_side=10,
    context_characters_each_side=2000,
    minimum_cooccurrence=2,exported_neighbours=30,temporal_window_years=5,
    word2vec=dict(vector_size=100,window=5,min_count=5,sg=1,negative=5,epochs=15,
                  seed=42,workers=1,sample=0.001),
    minimum_training_tokens=3000,minimum_training_contexts=50)


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temporary.replace(path)


def stable_hash(value):
    return int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:8],'little')


def eligible(word,target):
    return word!=target and 3<=len(word)<=40 and word not in STOP


def context(row):
    text=row['text'];start,end=int(row['start']),int(row['end'])
    if not 0<=start<end<=len(text):raise ValueError('Invalid target offsets')
    target=str(row.get('lemma') or row['target']).casefold()
    before=[m.group().casefold() for m in TOKEN.finditer(text[max(0,start-2000):start]) if len(m.group())<=40][-30:]
    after=[m.group().casefold() for m in TOKEN.finditer(text[end:end+2000]) if len(m.group())<=40][:30]
    nearby={w for w in before[-10:]+after[:10] if eligible(w,target)}
    left=max(0,start-150);right=min(len(text),end+150)
    evidence=dict(text=('…' if left else '')+text[left:right]+('…' if right<len(text) else ''),
        date=str(row.get('date') or ''),id=str(row.get('id') or ''),
        url=row.get('url') if isinstance(row.get('url'),str) and re.match(r'^https?://',row['url']) else None)
    return target,before+[target]+after,nearby,evidence


def resource_identity(corpus,path,row,titles=None):
    """Recover stable resource IDs from source filenames or public author URLs."""
    if corpus in {'kubhist','kubhist2'}:
        match=re.match(r'^'+re.escape(corpus)+r'-(.+)-\d{4}\.xml',path.name)
        if not match:raise ValueError(f'Cannot identify newspaper: {path.name}')
        identifier=match[1]
        return dict(id=identifier,label=(titles or {}).get(identifier,identifier.replace('-',' ').title()),kind='newspaper')
    if corpus=='lb':
        match=re.search(r'/författare/([^/]+)',unquote(urlsplit(row.get('url') or '').path))
        identifier=match[1] if match else 'unknown-author'
        return dict(id=identifier,label=identifier if match else 'Unknown author',kind='author')
    identifier=path.name.split('.xml')[0].removeprefix('tkr-')
    labels={'protokoll':'Parliamentary proceedings','motioner':'Motions','propositioner':'Government bills',
            'utredningar-kombet-sou':'Committee reports and SOU'}
    return dict(id=identifier,label=labels.get(identifier,identifier),kind='document collection')


def empty_source():
    return dict(totals=Counter(),counts=defaultdict(Counter),examples=defaultdict(lambda:defaultdict(list)),
                sentences=defaultdict(list),hasher=hashlib.sha256())


def accumulate(source,target,year,tokens,nearby,evidence,line):
    key=(target,year);source['totals'][key]+=1;source['sentences'][year].append(tokens)
    source['counts'][key].update(nearby);source['hasher'].update(line.encode())
    for word in sorted(nearby):
        if len(source['examples'][key][word])<2:source['examples'][key][word].append(evidence)


def read_source(workspace,corpus,include_resources=False,titles=None):
    folder=workspace/'target_usages'/corpus/'mats_sampled'
    sampling=json.loads((folder/'sampling_manifest.json').read_text())
    if sampling.get('sampling_period')!='year':raise ValueError('Yearly samples are required')
    source=empty_source();resources={}
    for path in sorted(folder.glob('*.jsonl')):
        source['hasher'].update(path.name.encode())
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():continue
                row=json.loads(line);year=int(str(row['date'])[:4])
                target,tokens,nearby,evidence=context(row)
                accumulate(source,target,year,tokens,nearby,evidence,line)
                if include_resources:
                    identity=resource_identity(corpus,path,row,titles)
                    if identity['id'] not in resources:
                        resources[identity['id']]=dict(empty_source(),resource=identity)
                    # Including the source filename makes checkpoints sensitive to provenance.
                    accumulate(resources[identity['id']],target,year,tokens,nearby,evidence,path.name+line)
    if sum(source['totals'].values())!=sampling['sampled_usages']:raise ValueError('Sample counts disagree with manifest')
    public={k:sampling[k] for k in ['sampling_period','per_word_year_cap','seed','sampled_usages']}
    source.update(digest=source.pop('hasher').hexdigest(),sampling=public)
    for subset in resources.values():
        subset.update(digest=subset.pop('hasher').hexdigest(),sampling=dict(public,
            sampled_usages=sum(subset['totals'].values()),parent_sampled_usages=public['sampled_usages'],
            quota_scope='The yearly cap applies to the whole corpus, not separately to each resource.'))
    if include_resources:source['resources']=resources
    return source


def cooccurrence_rows(source,target,year):
    key=(target,year);n=source['totals'][key]
    candidates=sorted(source['counts'][key].items(),key=lambda item:(-item[1],item[0]))
    return [dict(word=word,count=count,share=count/n,examples=source['examples'][key][word])
            for word,count in candidates if count>=SETTINGS['minimum_cooccurrence']][:SETTINGS['exported_neighbours']]


def fit_year(source,year,settings=SETTINGS):
    from gensim.models import Word2Vec
    half=settings['temporal_window_years']//2
    sentences=[sentence for y in range(year-half,year+half+1) for sentence in source['sentences'].get(y,[])]
    tokens=sum(map(len,sentences))
    report=dict(year=year,training_from=year-half,training_through=year+half,
                training_contexts=len(sentences),training_tokens=tokens,results={})
    if tokens<settings['minimum_training_tokens'] or len(sentences)<settings['minimum_training_contexts']:
        report['unavailable']='Too few training contexts or tokens';return report
    model=Word2Vec(hashfxn=stable_hash,**settings['word2vec'])
    model.build_vocab(sentences)
    if len(model.wv)<2:
        report['unavailable']='Too few words meet the vocabulary threshold';return report
    model.train(sentences,total_examples=model.corpus_count,epochs=model.epochs)
    report['vocabulary']=len(model.wv)
    for target in sorted({word for word,y in source['totals'] if y==year}):
        if target not in model.wv:continue
        candidates=model.wv.most_similar(target,topn=min(500,len(model.wv)-1))
        report['results'][target]=[dict(word=word,cosine=float(score),training_count=int(model.wv.get_vecattr(word,'count')))
            for word,score in candidates if eligible(word,target)][:settings['exported_neighbours']]
    return report


def write_corpus(workspace,site,corpus,embeddings=False,workers=4,cache=None):
    source=read_source(workspace,corpus)
    return write_source(source,workspace,site,corpus,embeddings,workers,cache)


def write_source(source,workspace,site,corpus,embeddings=False,workers=4,cache=None):
    relative=Path('data/associations')/corpus
    resource=source.get('resource')
    suffix=Path('resources')/hashlib.sha256(resource['id'].encode()).hexdigest()[:16] if resource else Path()
    relative=relative/suffix;destination=site/relative
    words=sorted({word for word,_ in source['totals']})
    models={}
    if embeddings:
        signature=hashlib.sha256((source['digest']+json.dumps(SETTINGS,sort_keys=True)).encode()).hexdigest()
        cache=(cache or workspace/'focus-projects/association_runs/mats_word2vec_v1')/corpus/suffix
        cache.mkdir(parents=True,exist_ok=True)
        def calculate(year):
            path=cache/f'{year}.json'
            if path.exists():
                saved=json.loads(path.read_text())
                if saved.get('signature')==signature:return saved['model']
            result=fit_year(source,year)
            atomic_json(path,dict(signature=signature,model=result))
            print(corpus,resource['id'] if resource else 'all',year,'trained',result['training_contexts'],'contexts',flush=True)
            return result
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for model in executor.map(calculate,sorted(source['sentences'])):models[model['year']]=model
    files={}
    for word in words:
        years=[]
        for target,year in sorted(source['totals']):
            if target!=word:continue
            key=(word,year);model=models.get(year)
            similarity=[]
            if model:
                for point in model['results'].get(word,[]):
                    similarity.append(dict(point,count=source['counts'][key][point['word']],examples=source['examples'][key].get(point['word'],[])))
            years.append(dict(year=year,n=source['totals'][key],cooccurrence=cooccurrence_rows(source,word,year),
                similarity=similarity,model={k:v for k,v in model.items() if k!='results'} if model else None))
        name=hashlib.sha256(word.encode()).hexdigest()[:16]+'.json'
        atomic_json(destination/name,dict(corpus=corpus,word=word,years=years))
        files[word]=(relative/name).as_posix()
    meta=dict(corpus=corpus,words=words,files=files,sampling=source['sampling'],source_digest=source['digest'],
        settings=SETTINGS,embedding_status='ready' if embeddings else 'pending',
        words_are='Lowercased word forms; neighbours are not lemmatized. Selected target forms are normalized to their target lemma.',
        training_source='Yearly-balanced Mats target-usage samples, not the full corpus.',
        scope='Each corpus is analysed separately. Word2Vec uses a centred five-year training window for every displayed year.')
    if embeddings:
        import gensim
        meta['gensim_version']=gensim.__version__
    if resource:
        meta['resource']=resource
        meta['scope']='Only this resource contributes to counts, excerpts and Word2Vec training. The centred five-year training window is unchanged.'
    elif (destination/'manifest.json').exists():
        previous=json.loads((destination/'manifest.json').read_text())
        if previous.get('source_digest')==source['digest'] and 'resources' in previous:
            meta['resources']=previous['resources']
    atomic_json(destination/'manifest.json',meta)
    print('Built',corpus,source['sampling']['sampled_usages'],'usages; embeddings:',embeddings,flush=True)
    return meta


def write_resources(workspace,site,corpus,embeddings=False,workers=4):
    parent=site/'data/associations'/corpus/'manifest.json'
    if not parent.exists():raise ValueError('Build the corpus-level data before its resources')
    labels=site/'data/source_breakdown.json'
    titles=json.loads(labels.read_text()).get('newspaper_titles',{}) if labels.exists() else {}
    source=read_source(workspace,corpus,include_resources=True,titles=titles)
    entries=[]
    for identifier,subset in sorted(source['resources'].items()):
        meta=write_source(subset,workspace,site,corpus,embeddings,workers)
        folder=Path(next(iter(meta['files'].values()))).parent
        entries.append(dict(meta['resource'],data=(folder/'manifest.json').as_posix(),
                            words=meta['words'],sampled_usages=meta['sampling']['sampled_usages']))
    meta=json.loads(parent.read_text());meta['resources']=entries
    atomic_json(parent,meta)
    print('Built',corpus,len(entries),'resources',flush=True)
    return entries


def write_manifest(site):
    entries=[]
    for corpus in CORPORA:
        path=site/'data/associations'/corpus/'manifest.json'
        if path.exists():entries.append(dict(corpus=corpus,data='data/associations/'+corpus+'/manifest.json'))
    atomic_json(site/'data/associations/manifest.json',dict(schema_version=1,corpora=entries))


def write_page(site):
    script=HERE.parent/'assets/word-associations.js'
    version=hashlib.sha256(script.read_bytes()).hexdigest()[:16]
    content=(HERE/'word_associations_template.html').read_text().replace('assets/word-associations.js','assets/word-associations.js?v='+version)
    (site/'associations.html').write_text(content)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=WORKSPACE)
    parser.add_argument('--site',type=Path,default=SITE)
    parser.add_argument('--corpus',choices=CORPORA)
    parser.add_argument('--embeddings',action='store_true')
    parser.add_argument('--resources',action='store_true',help='Build resource subsets, preserving corpus-level results')
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.workers<1:parser.error('--workers must be positive')
    for corpus in [args.corpus] if args.corpus else CORPORA:
        build=write_resources if args.resources else write_corpus
        build(args.workspace.resolve(),args.site.resolve(),corpus,args.embeddings,args.workers)
    if not args.corpus:write_manifest(args.site.resolve());write_page(args.site.resolve())
