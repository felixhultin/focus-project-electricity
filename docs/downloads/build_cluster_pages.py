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
PUBLIC_KEYS = {'representation_model', 'embedding_model', 'embedding_revision', 'clustering', 'metric', 'linkage',
               'distance_threshold', 'cluster_labels_scope', 'shared_clustering', 'definition_coverage', 'usage_counts', 'cluster_counts', 'sampling'}
GENERATION_KEYS = {'provider', 'model', 'revision', 'prompt', 'dtype', 'max_new_tokens',
                   'max_input_tokens', 'context_chars', 'do_sample', 'prompt_index', 'num_beams', 'filter_target', 'context_policy'}


def discover(workspace):
    found = []
    for manifest in sorted((workspace/'focus-projects'/'data').glob('clustered_definitions*_mats_*/clustering_manifest.json')):
        found.append((manifest.parent.name.rsplit('_mats_', 1)[-1], 'definitions', manifest.parent))
    for manifest in sorted((workspace/'target_usages').glob('*/mats_clustered_xllexeme/clustering_manifest.json')):
        found.append((manifest.parent.parent.name, 'usages', manifest.parent))
    return found


def load_dataset(corpus, method, folder):
    manifest = json.loads((folder/'clustering_manifest.json').read_text())
    counts, clusters, rows = Counter(), defaultdict(set), []
    generation_config = None
    model = manifest.get('representation_model') if method == 'usages' else None
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
                                 id=str(row.get('id') or ''), url=row.get('url'), source=path.name))
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
    elif model == 'pierluigic/xl-lexeme':
        label, alias = 'XL-LEXEME', 'xl-lexeme'
    elif model == 'unrecorded-definition-model':
        label, alias = 'Prompted definitions (model unrecorded)', model
    else:
        label, alias = model, re.sub(r'[^a-z0-9-]+', '-', model.lower()).strip('-')
    encoder = manifest.get('embedding_model') if method == 'definitions' else None
    encoder_labels = {
        'sentence-transformers/paraphrase-multilingual-mpnet-base-v2': 'multilingual MPNet',
        'sentence-transformers/all-mpnet-base-v2': 'MPNet (all-mpnet-base-v2)',
    }
    if method == 'definitions':
        encoder_label = encoder_labels.get(encoder, encoder or 'encoder unrecorded')
        pipeline_label = label + ' + ' + encoder_label
        if alias == 'llm-wsd' and encoder == 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2':
            pipeline_id = alias  # Preserve existing share links.
        elif alias == 't5-xl' and encoder == 'sentence-transformers/all-mpnet-base-v2':
            pipeline_id = 't5-xl--mpnet'
        else:
            pipeline_id = alias + '--' + re.sub(r'[^a-z0-9-]+', '-', (encoder or 'encoder-unrecorded').lower()).strip('-')
    else:
        pipeline_id, pipeline_label = alias, label + ' (usage embeddings)'
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
    index = site/'index.html'
    if index.exists():
        content = index.read_text()
        links = '<p class="site-links"><a href="clusters.html">Model clusters</a> · <a href="examples.html">Workbook examples</a> · <a href="source-breakdown.html">Authors and newspapers</a> · <a href="methodology.html">Method and sources</a></p>'
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
        if 'href="clusters.html"' not in content:
            content = re.sub(r'(<p[^>]*>.*?)(</p>)', r'\1 · <a href="clusters.html">Model clusters</a>\2', content, count=1, flags=re.S)
        content = re.sub(r'<p class="downloads">.*?</p>', '', content, flags=re.S)
        content = content.replace('<a href="data/frequency_reconciliation.csv">Download the comparison</a> for every bin.', 'Counts are compared for every bin.')
        content = re.sub(r'<a\b[^>]*href="(?:[^"<>]*\.csv|downloads/[^"<>]*\.py)"[^>]*>(.*?)</a>', r'\1', content, flags=re.S)
        page.write_text(content, encoding='utf-8')


def write_explorer_page(site):
    """Change the script URL whenever code changes, avoiding cached incompatible controls."""
    script = HERE.parent/'assets'/'cluster-explorer.js'
    version = hashlib.sha256(script.read_bytes()).hexdigest()[:16]
    content = (HERE/'cluster_explorer_template.html').read_text()
    content = content.replace('src="assets/cluster-explorer.js"', f'src="assets/cluster-explorer.js?v={version}"')
    (site/'clusters.html').write_text(content, encoding='utf-8')


def build(workspace, site):
    destination = site/'data'/'clusters'
    destination.mkdir(parents=True, exist_ok=True)
    entries, used = [], set()
    for corpus, method, folder in discover(workspace):
        data = load_dataset(corpus, method, folder)
        if data['id'] in used:
            raise ValueError(f'Duplicate model/corpus result: {data["id"]}')
        used.add(data['id'])
        filename = data['id']+'.json'
        (destination/filename).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        entry = {key: data[key] for key in ['id', 'corpus', 'model', 'model_label', 'model_alias', 'method', 'pipeline_id', 'pipeline_label', 'generator_model', 'encoder_model']}
        entry.update(data='data/clusters/'+filename, usage_count=len(data['rows']),
                     word_count=len(data['manifest']['usage_counts']),
                     cluster_count=sum(data['manifest']['cluster_counts'].values()))
        entries.append(entry)
    if not entries:
        raise ValueError('No completed clustering result sets found')
    experiments_path = workspace/'focus-projects/definition_experiments.json'
    experiments = json.loads(experiments_path.read_text()) if experiments_path.exists() else []
    available = {entry['pipeline_id'] for entry in entries}
    pending = [{key: experiment[key] for key in ['pipeline_id', 'pipeline_label']} for experiment in experiments if experiment['pipeline_id'] not in available]
    (destination/'manifest.json').write_text(json.dumps(dict(schema_version=2, datasets=entries, pending=pending), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_explorer_page(site)
    for name in ['cluster-explorer.js', 'word-selector.js']:
        asset = site/'assets'/name
        asset.parent.mkdir(parents=True, exist_ok=True)
        source_asset = HERE.parent/'assets'/name
        if asset.resolve() != source_asset.resolve():
            asset.write_text(source_asset.read_text(), encoding='utf-8')
    integrate_navigation(site)
    for entry in entries:
        print(entry['model_label'], entry['corpus'], entry['usage_count'], 'usages')
    print('Built', site/'clusters.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=HERE.parents[2])
    parser.add_argument('--site', type=Path, default=HERE.parent)
    args = parser.parse_args()
    build(args.workspace.resolve(), args.site.resolve())


if __name__ == '__main__':
    main()
