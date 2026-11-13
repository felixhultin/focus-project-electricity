#!/usr/bin/env python3
"""Prepare a compact Mats Pages release on top of the committed site (including Mia)."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def build(destination,repo=ROOT):
    destination.mkdir(parents=True,exist_ok=False)
    archive=subprocess.Popen(['git','archive','HEAD'],cwd=repo,stdout=subprocess.PIPE)
    subprocess.run(['tar','-x','-C',str(destination)],stdin=archive.stdout,check=True)
    archive.stdout.close()
    if archive.wait():raise RuntimeError('Could not export the committed site')
    changed=set(subprocess.check_output(['git','diff','--name-only','-z','HEAD'],cwd=repo).decode().split('\0'))
    changed.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=repo).decode().split('\0'))
    for name in sorted(changed):
        if not name or name.startswith('docs/mia/'):continue
        if not (name=='README.md' or name.startswith('docs/') or name.startswith('tests/')):continue
        if name.startswith(('docs/data/clusters/','docs/data/associations/')):continue
        if 'mia' in name or 'kvinnsam' in name:continue
        source=repo/name
        if source.is_file():
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    source=repo/'docs';site=destination/'docs';catalog=json.loads((source/'data/clusters/manifest.json').read_text())
    mapping=dict(files={},bundles=[])
    # Replace model result files with deterministic gzip assets. Keep public logical URLs stable.
    for path in (site/'data/clusters').glob('*.json'):
        if path.name!='manifest.json':path.unlink()
    for entry in catalog['datasets']:
        logical=entry['data'];target=site/(logical+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress((source/logical).read_bytes(),compresslevel=6,mtime=0))
        mapping['files'][logical]=logical+'.gz'
    (site/'data/clusters/manifest.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')))
    association=source/'data/associations'
    for folder in sorted(association.iterdir()):
        if not folder.is_dir():continue
        values={path.relative_to(source).as_posix():json.loads(path.read_text()) for path in sorted(folder.rglob('*.json'))}
        relative='data/associations/'+folder.name+'.json.gz';target=site/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode(),compresslevel=6,mtime=0))
        mapping['bundles'].append(dict(prefix='data/associations/'+folder.name+'/',url=relative))
    shutil.copy2(association/'manifest.json',site/'data/associations/manifest.json')
    (site/'data/asset-map.json').write_text(json.dumps(mapping,separators=(',',':')))
    total=sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    if total>=1_000_000_000:raise ValueError(f'Pages release exceeds 1 GB: {total}')
    # Produce only changed Git objects; unchanged examples and committed Mia remain in the base tree.
    baseline={}
    for line in subprocess.check_output(['git','ls-tree','-rlz','HEAD'],cwd=repo).decode().split('\0'):
        if not line:continue
        fields,name=line.split('\t',1);mode,kind,sha,size=fields.split();baseline[name]=dict(sha=sha,mode=mode)
    entries=[];present=set()
    for path in sorted(destination.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(destination).as_posix();present.add(name);payload=path.read_bytes()
        sha=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        if baseline.get(name,{}).get('sha')!=sha:
            entries.append(dict(path=name,sha=sha,mode='100644',size=len(payload),binary=name.endswith('.gz')))
    entries.extend(dict(path=name,sha=None,mode=value['mode']) for name,value in baseline.items() if name not in present)
    report=dict(base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        base_tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=repo,text=True).strip(),
        site_bytes=total,entries=entries)
    (destination.parent/(destination.name+'-upload.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(site_MB=round(total/1e6,1),changed_files=len(entries),
        upload_MB=round(sum(e.get('size',0) for e in entries)/1e6,1),release=str(destination))),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    args=parser.parse_args();build(args.destination.resolve())
