import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'docs/downloads/prepare_pages_release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReleaseTests(unittest.TestCase):
    def test_lossless_data_packing_and_unchanged_unicode_mia(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'repo';repo.mkdir()
            def write(name,value):
                p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
            write('docs/mia/ström.json','{"old":true}')
            write('docs/example_data/ström.json','{"same":true}')
            write('docs/data/clusters/old.json','{}')
            subprocess.run(['git','init','-q'],cwd=repo,check=True)
            subprocess.run(['git','add','.'],cwd=repo,check=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','baseline'],cwd=repo,check=True)
            write('docs/mia/ström.json','{"unreleased":true}')
            write('docs/data/clusters/manifest.json',json.dumps(dict(datasets=[dict(data='data/clusters/new.json')])))
            write('docs/data/clusters/new.json','{"word":"ström","rows":[1,2]}')
            write('docs/data/associations/manifest.json','{"corpora":[]}')
            write('docs/data/associations/tkr/paper/word.json','{"n":3}')
            output=root/'release';report=r.build(output,repo)
            self.assertEqual((output/'docs/mia/ström.json').read_text(),'{"old":true}')
            self.assertFalse(any(e['path'].startswith('docs/mia/') for e in report['entries']))
            self.assertFalse(any('example_data' in e['path'] for e in report['entries']))
            data=json.loads(gzip.decompress((output/'docs/data/clusters/new.json.gz').read_bytes()))
            self.assertEqual(data,dict(word='ström',rows=[1,2]))
            bundle=json.loads(gzip.decompress((output/'docs/data/associations/tkr.json.gz').read_bytes()))
            self.assertEqual(bundle['data/associations/tkr/paper/word.json'],dict(n=3))
            self.assertTrue(any(e['path']=='docs/data/clusters/old.json' and e['sha'] is None for e in report['entries']))
            self.assertFalse(any(e['path'].startswith('"') for e in report['entries']))

if __name__=='__main__':unittest.main()
