import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH=Path(__file__).resolve().parents[1]/'docs/downloads/prepare_association_release.py'
spec=importlib.util.spec_from_file_location('association_release',PATH)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class AssociationReleaseTest(unittest.TestCase):
    def test_chunk_roundtrip_preserves_model_map_and_mia(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';site=root/'site'
            (source/'data/associations/tkr').mkdir(parents=True)
            (site/'data/associations').mkdir(parents=True)
            (site/'mia').mkdir();(site/'mia/ö.json').write_bytes(b'unchanged')
            (site/'data/associations/old.json.gz').write_bytes(b'old')
            mapping=dict(files={'data/clusters/model.json':'data/clusters/model.json.gz'},
                bundles=[dict(prefix='data/associations/tkr/',url='data/associations/old.json.gz')])
            (site/'data/asset-map.json').write_text(json.dumps(mapping))
            catalog=dict(corpora=[dict(corpus='tkr',data='data/associations/tkr/manifest.json')])
            (source/'data/associations/manifest.json').write_text(json.dumps(catalog))
            expected={}
            for word in ['ström','åska','ö']:
                logical=f'data/associations/tkr/{word}.json';value=dict(word=word,n=123,share=1/3)
                expected[logical]=value;(source/logical).write_text(json.dumps(value,ensure_ascii=False))
            release.pack(source,site,chunk_bytes=60)
            result=json.loads((site/'data/asset-map.json').read_text())
            self.assertEqual(result['files'],mapping['files'])
            self.assertGreater(len(result['bundles']),1)
            actual={}
            for bundle in result['bundles']:
                values=json.loads(gzip.decompress((site/bundle['url']).read_bytes()))
                self.assertEqual(set(bundle['paths']),set(values));actual.update(values)
            self.assertEqual(actual,expected)
            self.assertEqual((site/'mia/ö.json').read_bytes(),b'unchanged')
            self.assertFalse((site/'data/associations/old.json.gz').exists())
