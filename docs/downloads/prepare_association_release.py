#!/usr/bin/env python3
"""Package Mats associations over a published base while preserving the rest of the site."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OVERLAY=['docs/assets/site-data.js','docs/assets/word-associations.js','docs/associations.html',
    'docs/downloads/build_word_associations.py','docs/downloads/word_associations_template.html',
    'docs/downloads/prepare_association_release.py','tests/test_word_associations.py',
    'tests/test_association_release.py','tests/browser_association_release.py']


def blob_sha(payload):
    return hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()


def pack(source,site,chunk_bytes=8_000_000):
    folder=site/'data/associations'
    if folder.exists():shutil.rmtree(folder)
    folder.mkdir(parents=True)
    mapping=json.loads((site/'data/asset-map.json').read_text())
    mapping['files']={key:value for key,value in mapping.get('files',{}).items() if not key.startswith('data/associations/')}
    mapping['bundles']=[b for b in mapping.get('bundles',[]) if not b.get('url','').startswith('data/associations/')]
    catalog=json.loads((source/'data/associations/manifest.json').read_text())
    shutil.copy2(source/'data/associations/manifest.json',folder/'manifest.json')
    for entry in catalog['corpora']:
        corpus=entry['corpus'];values={};size=0;index=0
        def flush():
            nonlocal values,size,index
            if not values:return
            relative=f'data/associations/{corpus}-{index:03d}.json.gz'
            raw=json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()
            (site/relative).write_bytes(gzip.compress(raw,compresslevel=6,mtime=0))
            mapping['bundles'].append(dict(paths=list(values),url=relative))
            values={};size=0;index+=1
        for path in sorted((source/'data/associations'/corpus).rglob('*.json')):
            raw=path.read_bytes()
            if size+len(raw)>chunk_bytes:flush()
            values[path.relative_to(source).as_posix()]=json.loads(raw);size+=len(raw)
        flush()
        print(corpus,index,'bundles',flush=True)
    (site/'data/asset-map.json').write_text(json.dumps(mapping,ensure_ascii=False,separators=(',',':')))


def build(destination,repo=ROOT,base='origin/main'):
    destination.mkdir(parents=True,exist_ok=False)
    archive=subprocess.Popen(['git','archive',base],cwd=repo,stdout=subprocess.PIPE)
    subprocess.run(['tar','-x','-C',str(destination)],stdin=archive.stdout,check=True)
    archive.stdout.close()
    if archive.wait():raise RuntimeError('Could not export the published site')
    for name in OVERLAY:
        source=repo/name
        if source.is_file():
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    pack(repo/'docs',destination/'docs')
    baseline={}
    for record in subprocess.check_output(['git','ls-tree','-rlz',base],cwd=repo).decode().split('\0'):
        if not record:continue
        fields,name=record.split('\t',1);mode,kind,sha,size=fields.split();baseline[name]=dict(mode=mode,sha=sha)
    entries=[];present=set();total=0
    for path in sorted(destination.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(destination).as_posix();present.add(name)
        if name.startswith('docs/'):total+=path.stat().st_size
        # Only these paths can have changed. Leave Mia and model results untouched.
        if name not in OVERLAY and not name.startswith('docs/data/associations/') and name!='docs/data/asset-map.json':continue
        raw=path.read_bytes();sha=blob_sha(raw)
        if baseline.get(name,{}).get('sha')!=sha:
            entries.append(dict(path=name,mode='100644',sha=sha,size=len(raw),binary=name.endswith('.gz') or len(raw)>150_000))
    entries.extend(dict(path=name,mode=value['mode'],sha=None) for name,value in baseline.items() if name not in present)
    if total>=1_000_000_000:raise ValueError(f'Pages release exceeds 1 GB: {total}')
    if any(e['path'].startswith('docs/mia/') for e in entries):raise ValueError('Mia must be preserved')
    report=dict(base_commit=subprocess.check_output(['git','rev-parse',base],cwd=repo,text=True).strip(),
        base_tree=subprocess.check_output(['git','rev-parse',base+'^{tree}'],cwd=repo,text=True).strip(),
        site_bytes=total,entries=entries)
    Path(str(destination)+'-upload.json').write_text(json.dumps(report))
    print(json.dumps(dict(site_MB=round(total/1e6,1),changed_files=len(entries),upload_MB=round(sum(e.get('size',0) for e in entries)/1e6,1))),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path);parser.add_argument('--base',default='origin/main')
    args=parser.parse_args();build(args.destination.resolve(),base=args.base)
