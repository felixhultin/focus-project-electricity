#!/usr/bin/env python3
"""Build the site's model-cluster explorer from completed local result sets."""
from __future__ import annotations
import argparse
import hashlib
from collections import Counter, defaultdict
from html import unescape, escape
import json
from pathlib import Path
import re
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
PUBLIC_KEYS = {'representation_model', 'embedding_model', 'embedding_revision', 'embedding_input_prefix', 'embedding_max_seq_length', 'embedding_output', 'embedding_normalized', 'clustering', 'metric', 'linkage',
               'distance_threshold', 'cluster_labels_scope', 'shared_clustering', 'definition_coverage', 'preview', 'usage_counts', 'cluster_counts', 'sampling',
               'embedding_dimensions', 'embedding_pooling', 'embedding_truncate_dim', 'embedding_dtype',
               'cooccurrence', 'characteristic_words', 'model_selection', 'source_digest'}
GENERATION_KEYS = {'provider', 'model', 'revision', 'prompt', 'dtype', 'max_new_tokens',
                   'max_input_tokens', 'context_chars', 'do_sample', 'prompt_index', 'num_beams', 'filter_target', 'context_policy', 'base_model', 'base_revision', 'language',
                   'temperature', 'top_p', 'repetition_penalty', 'stop_strings', 'forced_eos',
                   'tokenizer_model', 'tokenizer_revision', 'tokenizer_add_eos_token', 'tokenizer_add_bos_token'}
LOCAL_DICTIONARIES={'LlamaDictionary-sv_L27BCH','LlamaDictionary-sv_L38BI','LlamaDictionary-sv_ML38BI'}


def discover(workspace, dataset='mats'):
    found = []
    for manifest in sorted((workspace/'focus-projects'/'data').glob(f'clustered_definitions*_{dataset}_*/clustering_manifest.json')):
        found.append((manifest.parent.name.rsplit('_'+dataset+'_', 1)[-1], 'definitions', manifest.parent))
    for manifest in sorted((workspace/'target_usages').glob(f'*/{dataset}_clustered_xllexeme/clustering_manifest.json')):
        found.append((manifest.parent.parent.name, 'usages', manifest.parent))
    for manifest in sorted((workspace/'focus-projects/data').glob(f'clustered_cooccurrence_{dataset}_*/clustering_manifest.json')):
        found.append((manifest.parent.name.rsplit('_'+dataset+'_',1)[-1], 'cooccurrence', manifest.parent))
    return found


def load_dataset(corpus, method, folder):
    manifest = json.loads((folder/'clustering_manifest.json').read_text())
    counts, clusters, rows = Counter(), defaultdict(set), []
    generation_config = None
    model = manifest.get('representation_model') if method != 'definitions' else None
    for path in sorted(folder.glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                lemma = str(row.get('lemma') or row.get('target') or '')
                definition = str(row.get('generated_definition') or '').strip()
                if not lemma or (method == 'definitions' and not definition):
                    raise ValueError(f'Missing lemma/definition: {path}')
                config = row.get('generation_config')
                if config is not None:
                    if generation_config is not None and config != generation_config:
                        raise ValueError(f'Mixed generation settings: {folder}')
                    generation_config = config
                    model = config['model']
                cluster = int(row['cluster_id'])
                text, start, end = row['text'], int(row['start']), int(row['end'])
                if not 0 <= start < end <= len(text):
                    raise ValueError(f'Invalid target span: {path}')
                left, right = max(0, start-220), min(len(text), end+220)
                prefix = '…' if left else ''
                snippet = prefix + text[left:right] + ('…' if right < len(text) else '')
                a, b = start-left+len(prefix), end-left+len(prefix)
                a, b = len(snippet[:a].encode('utf-16-le'))//2, len(snippet[:b].encode('utf-16-le'))//2
                date = str(row.get('date') or '')
                year = int(date[:4]) if re.match(r'^\d{4}', date) else None
                rows.append(dict(lemma=lemma, cluster=cluster, definition=definition, token=text[start:end],
                                 text=snippet, start=a, end=b, date=date, year=year,
                                 id=str(row.get('id') or ''), url=row.get('url'),
                                 source=str(row.get('journal') or Path(str(row.get('source_file') or path.name)).name)))
                if row.get('resource'):
                    rows[-1]['resource_id']=row['resource']['id']
                    rows[-1]['resource_label']=row['resource']['label']
                counts[lemma] += 1
                clusters[lemma].add(cluster)
    if dict(counts) != manifest['usage_counts']:
        raise ValueError(f'Record totals disagree with manifest: {folder}')
    if {word: len(labels) for word, labels in clusters.items()} != manifest['cluster_counts']:
        raise ValueError(f'Cluster totals disagree with manifest: {folder}')
    model = model or 'unrecorded-definition-model'
    if model == 'swap-uniba/LLM-wsd-FT-ALL':
        label, alias = 'LLM-wsd-FT-ALL', 'llm-wsd'
    elif model == 'ltg/flan-t5-definition-en-xl':
        label, alias = 'FLAN-T5-Definition XL', 't5-xl'
    elif model == 'FrancescoPeriti/LlamaDictionary-sv-de-en_ML38BI':
        label, alias = 'LlamaDictionary-sv-de-en_ML38BI', 'llamadictionary-sv-de-en-ml38bi'
    elif model in LOCAL_DICTIONARIES:
        label, alias = model+' (local)', model.lower().replace('_','-')+'-local'
    elif model == 'pierluigic/xl-lexeme':
        label, alias = 'XL-LEXEME', 'xl-lexeme'
    elif model == 'tfidf-cooccurrence-kmeans':
        label, alias = 'Co-occurrence contexts · TF–IDF + K-means', 'cooccurrence-tfidf'
    elif model == 'unrecorded-definition-model':
        label, alias = 'Prompted definitions (model unrecorded)', model
    else:
        label, alias = model, re.sub(r'[^a-z0-9-]+', '-', model.lower()).strip('-')
    encoder = manifest.get('embedding_model') if method == 'definitions' else None
    encoder_labels = {
        'sentence-transformers/paraphrase-multilingual-mpnet-base-v2': 'multilingual MPNet',
        'sentence-transformers/all-mpnet-base-v2': 'MPNet (all-mpnet-base-v2)',
        'KBLab/sentence-bert-swedish-cased': 'KBLab Swedish Sentence-BERT',
        'intfloat/multilingual-e5-large': 'multilingual E5 large',
        'BAAI/bge-m3': 'BGE-M3 (dense)',
        'oxfrug/bge-m3-swedish-superlim': 'BGE-M3 Swedish SuperLim (768d)',
        'Qwen/Qwen3-Embedding-8B': 'Qwen3-Embedding-8B (4096d)',
    }
    if method == 'definitions':
        encoder_label = encoder_labels.get(encoder, encoder or 'encoder unrecorded')
        pipeline_label = label + ' + ' + encoder_label
        if alias == 'llm-wsd' and encoder == 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2':
            pipeline_id = alias  # Preserve existing share links.
        elif (alias == 'llamadictionary-sv-de-en-ml38bi' or model in LOCAL_DICTIONARIES) and encoder in {'KBLab/sentence-bert-swedish-cased','intfloat/multilingual-e5-large','BAAI/bge-m3','oxfrug/bge-m3-swedish-superlim','Qwen/Qwen3-Embedding-8B'}:
            encoder_alias = {'KBLab/sentence-bert-swedish-cased':'kblab','intfloat/multilingual-e5-large':'e5-large','BAAI/bge-m3':'bge-m3','oxfrug/bge-m3-swedish-superlim':'bge-m3-swedish','Qwen/Qwen3-Embedding-8B':'qwen3-8b'}[encoder]
            pipeline_id = alias + '--' + encoder_alias
        elif alias == 't5-xl' and encoder == 'sentence-transformers/all-mpnet-base-v2':
            pipeline_id = 't5-xl--mpnet'
        else:
            pipeline_id = alias + '--' + re.sub(r'[^a-z0-9-]+', '-', (encoder or 'encoder-unrecorded').lower()).strip('-')
    else:
        pipeline_id, pipeline_label = alias, label + (' (usage embeddings)' if method=='usages' else '')
    if generation_config and generation_config.get('prompt') == 'llamadictionary-sv-usage-guide-v2':
        pipeline_id += '--guide-v2'
        pipeline_label += ' (usage-guide v2)'
    if manifest.get('preview'):
        if manifest.get('shared_clustering'):
            raise ValueError('A corpus preview cannot advertise shared clustering')
        if manifest['preview']['superseded_by'] != pipeline_id:
            raise ValueError('Preview replacement does not match its generator/encoder')
        pipeline_id += '--preview-' + corpus
        pipeline_label += ' (' + corpus.upper() + ' preview)'
    public = {key: value for key, value in manifest.items() if key in PUBLIC_KEYS}
    if "sampling" in manifest:
        allowed_sampling = {"sampling_period", "per_word_year_cap", "per_word_decade_cap", "seed", "sampled_usages", "skipped_empty_targets", "skipped_invalid_targets", "skipped_unknown_years"}
        public["sampling"] = {key: value for key, value in manifest["sampling"].items() if key in allowed_sampling}
    if generation_config:
        public['generation'] = {key: value for key, value in generation_config.items() if key in GENERATION_KEYS}
    return dict(id=f'{pipeline_id}--{corpus}', corpus=corpus, model=model, model_label=label, model_alias=pipeline_id,
                pipeline_id=pipeline_id, pipeline_label=pipeline_label, generator_model=model if method=='definitions' else None, encoder_model=encoder,
                method=method, rows=rows, manifest=public)


def integrate_navigation(site):
    """Apply the compact navigation to generated pages and their templates."""
    association_link = ' · <a href="associations.html">Associated words</a>' if (site/'associations.html').exists() else ''
    index = site/'index.html'
    if index.exists():
        content = index.read_text()
        links = '<p class="site-links"><a href="clusters.html">Model clusters</a> · <a href="examples.html">Workbook examples</a> · <a href="source-breakdown.html">Authors and newspapers</a> · <a href="methodology.html">Method and sources</a></p>'
        links = links.replace('</p>', association_link+'</p>')
        if re.search(r'<p class="site-links">.*?</p>', content, flags=re.S):
            content = re.sub(r'<p class="site-links">.*?</p>', lambda _: links, content, count=1, flags=re.S)
        else:
            content = content.replace('<nav aria-label="Target words">', links+'<nav aria-label="Target words">', 1)
        words = re.findall(r'<section id="(word-\d+)"><h2>(.*?)</h2>', content)
        selector = '<div class="word-picker"><label for="word-select">Word</label> <select id="word-select">'+''.join('<option value="'+escape(identifier,quote=True)+'">'+label+'</option>' for identifier,label in words)+'</select></div>'
        content = re.sub(r'<nav aria-label="Target words">.*?</nav>', lambda _: selector, content, count=1, flags=re.S)
        if 'id="word-select"' not in content and words:
            content = content.replace(links,links+selector,1)
        def link_word(match):
            section = match.group(0)
            title = re.search(r'<h2>(.*?)</h2>', section)
            if 'clusters.html?word=' in section or not title:
                return section
            word = quote(unescape(re.sub('<[^>]+>', '', title.group(1))))
            return section.replace('</p>', f' · <a href="clusters.html?word={word}">Model clusters</a></p>', 1)
        content = re.sub(r'<section\b.*?</section>', link_word, content, flags=re.S)
        content = re.sub(r'<a href="targets/[^"<>]+">Open SVG</a>', '', content)
        if 'assets/word-selector.js' not in content:
            content = content.replace('</html>','<script src="assets/word-selector.js"></script></html>')
        if 'id="word-picker-style"' not in content:
            content = content.replace('</style>','</style><style id="word-picker-style">.word-picker{display:flex;gap:.7rem;align-items:center;margin:1.5rem 0}.word-picker label{font-weight:600}.word-picker select{font:inherit;padding:.5rem .75rem;max-width:100%;min-width:12rem;border:1px solid #a9b5c3;border-radius:6px}section[hidden]{display:none}</style>',1)
        index.write_text(content, encoding='utf-8')
    for name in ['examples.html', 'source-breakdown.html', 'methodology.html',
                 'downloads/mats_examples_viewer.html', 'downloads/source_breakdown_viewer.html']:
        page = site/name
        if not page.exists():
            continue
        content = page.read_text()
        if association_link and 'href="associations.html"' not in content:
            content = re.sub(r'(<p[^>]*>.*?)(</p>)', lambda m: m[1]+association_link+m[2], content, count=1, flags=re.S)
        if 'href="clusters.html"' not in content:
            content = re.sub(r'(<p[^>]*>.*?)(</p>)', r'\1 · <a href="clusters.html">Model clusters</a>\2', content, count=1, flags=re.S)
        content = re.sub(r'<p class="downloads">.*?</p>', '', content, flags=re.S)
        content = content.replace('<a href="data/frequency_reconciliation.csv">Download the comparison</a> for every bin.', 'Counts are compared for every bin.')
        content = re.sub(r'<a\b[^>]*href="(?:[^"<>]*\.csv|downloads/[^"<>]*\.py)"[^>]*>(.*?)</a>', r'\1', content, flags=re.S)
        page.write_text(content, encoding='utf-8')


def write_explorer_page(site, dataset='mats'):
    """Change the script URL whenever code changes, avoiding cached incompatible controls."""
    script = HERE.parent/'assets'/'cluster-explorer.js'
    version = hashlib.sha256(script.read_bytes()).hexdigest()[:16]
    content = (HERE/'cluster_explorer_template.html').read_text()
    if dataset == 'mats' and (site/'associations.html').exists():
        content = content.replace('</p>', ' · <a href="associations.html">Associated words</a></p>', 1)
    if dataset == 'mia':
        content = content.replace('Electricity word frequencies','Mia word frequencies').replace('the electricity words','the Mia terms')
        content = content.replace(' XL-LEXEME clusters contextual usage embeddings directly.','')
        content = content.replace('Workbook examples','Source examples').replace('Authors and newspapers','Authors, newspapers and journals')
    content = content.replace('src="assets/cluster-explorer.js"', f'src="assets/cluster-explorer.js?v={version}"')
    (site/'clusters.html').write_text(content, encoding='utf-8')
    (site/'assets').mkdir(exist_ok=True)
    shared=HERE.parent/'assets/site-data.js'
    if (site/'assets/site-data.js').resolve()!=shared.resolve():
        (site/'assets/site-data.js').write_bytes(shared.read_bytes())
    (site/'data').mkdir(exist_ok=True)
    if not (site/'data/asset-map.json').exists():(site/'data/asset-map.json').write_text('{}')


def build(workspace, site, dataset='mats'):
    destination = site/'data'/'clusters'
    destination.mkdir(parents=True, exist_ok=True)
    entries, used = [], set()
    datasets = [load_dataset(corpus, method, folder) for corpus, method, folder in discover(workspace, dataset)]
    final_ids = {data['id'] for data in datasets if not data['manifest'].get('preview')}
    for data in datasets:
        preview = data['manifest'].get('preview')
        if preview and preview['superseded_by'] + '--' + data['corpus'] in final_ids:
            continue
        if data['id'] in used:
            raise ValueError(f'Duplicate model/corpus result: {data["id"]}')
        used.add(data['id'])
        filename = data['id']+'.json'
        usage_count = len(data['rows'])
        if dataset == 'mia':
            groups = defaultdict(list)
            for row in data['rows']: groups[row['lemma']].append(row)
            folder = destination/data['id'];folder.mkdir(exist_ok=True)
            data['words'] = sorted(groups)
            data['word_counts'] = {word:len(rows) for word,rows in groups.items()}
            data['word_files'] = {}
            for word,rows in groups.items():
                word_file = hashlib.sha256(word.encode()).hexdigest()[:16]+'.json'
                (folder/word_file).write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
                data['word_files'][word] = 'data/clusters/'+data['id']+'/'+word_file
            data['rows'] = []
        (destination/filename).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        entry = {key: data[key] for key in ['id', 'corpus', 'model', 'model_label', 'model_alias', 'method', 'pipeline_id', 'pipeline_label', 'generator_model', 'encoder_model']}
        entry.update(data='data/clusters/'+filename, usage_count=usage_count,
                     word_count=len(data['manifest']['usage_counts']),
                     cluster_count=sum(data['manifest']['cluster_counts'].values()))
        entries.append(entry)
    if not entries and dataset != 'mia':
        raise ValueError('No completed clustering result sets found')
    experiments_path = workspace/'focus-projects'/('mia_definition_experiments.json' if dataset=='mia' else 'definition_experiments.json')
    experiments = json.loads(experiments_path.read_text()) if experiments_path.exists() else []
    available = {entry['pipeline_id'] for entry in entries}
    pending = [{key: experiment[key] for key in ['pipeline_id', 'pipeline_label']} for experiment in experiments if experiment['pipeline_id'] not in available]
    (destination/'manifest.json').write_text(json.dumps(dict(schema_version=2, datasets=entries, pending=pending), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_explorer_page(site, dataset)
    for name in ['cluster-explorer.js', 'word-selector.js']:
        asset = site/'assets'/name
        asset.parent.mkdir(parents=True, exist_ok=True)
        source_asset = HERE.parent/'assets'/name
        if asset.resolve() != source_asset.resolve():
            asset.write_text(source_asset.read_text(), encoding='utf-8')
    integrate_navigation(site)
    if dataset == 'mia' and (site/'index.html').exists():
        index=site/'index.html';content=index.read_text()
        content=content.replace('Authors and newspapers','Authors, newspapers and journals').replace('Workbook examples','Source examples')
        index.write_text(content)
    for entry in entries:
        print(entry['model_label'], entry['corpus'], entry['usage_count'], 'usages')
    print('Built', site/'clusters.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=HERE.parents[2])
    parser.add_argument('--site', type=Path, default=HERE.parent)
    parser.add_argument('--dataset', choices=['mats','mia'], default='mats')
    args = parser.parse_args()
    build(args.workspace.resolve(), args.site.resolve(), args.dataset)


if __name__ == '__main__':
    main()
