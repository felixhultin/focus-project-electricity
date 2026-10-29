import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'docs/downloads/build_cluster_pages.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class ClusterPagesTests(unittest.TestCase):
    def write_data(self, folder, method, count=1):
        folder.mkdir(parents=True)
        manifest=dict(input_dir='/private/local/path',usage_counts={'bank':count},cluster_counts={'bank':1},metric='cosine')
        row=dict(lemma='bank',cluster_id=0,text='😀 bank',start=2,end=6,date='1901-01-01')
        if method=='definitions':
            row.update(generated_definition='A financial institution.',generation_config={'model':'swap-uniba/LLM-wsd-FT-ALL','prompt':'test'})
        else:
            manifest['representation_model']='pierluigic/xl-lexeme'
        (folder/'clustering_manifest.json').write_text(json.dumps(manifest))
        (folder/'usages.jsonl').write_text(json.dumps(row)+'\n')

    def test_model_discovery_and_public_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace=Path(temp)
            llm=workspace/'focus-projects/data/clustered_definitions_llm_wsd_mats_lb'
            xl=workspace/'target_usages/tkr/mats_clustered_xllexeme'
            self.write_data(llm,'definitions');self.write_data(xl,'usages')
            sources=builder.discover(workspace)
            self.assertEqual({(c,m) for c,m,_ in sources},{('lb','definitions'),('tkr','usages')})
            result=builder.load_dataset('tkr','usages',xl)
            self.assertEqual(result['model_label'],'XL-LEXEME')
            self.assertEqual(result['rows'][0]['definition'],'')
            self.assertNotIn('/private',json.dumps(result))
            row=result['rows'][0]
            raw=row['text'].encode('utf-16-le')
            self.assertEqual(raw[row['start']*2:row['end']*2].decode('utf-16-le'),'bank')
            self.assertEqual(builder.load_dataset('lb','definitions',llm)['model_label'],'LLM-wsd-FT-ALL')

    def test_same_generator_different_encoders_have_distinct_identities(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'result';self.write_data(folder,'definitions')
            path=folder/'clustering_manifest.json'
            manifest=json.loads(path.read_text())
            manifest['embedding_model']='sentence-transformers/paraphrase-multilingual-mpnet-base-v2'
            path.write_text(json.dumps(manifest))
            multilingual=builder.load_dataset('tkr','definitions',folder)
            manifest['embedding_model']='sentence-transformers/all-mpnet-base-v2'
            path.write_text(json.dumps(manifest))
            english=builder.load_dataset('tkr','definitions',folder)
            self.assertEqual(multilingual['pipeline_id'],'llm-wsd')
            self.assertNotEqual(multilingual['id'],english['id'])
            self.assertEqual(multilingual['generator_model'],english['generator_model'])
            self.assertNotEqual(multilingual['encoder_model'],english['encoder_model'])
            row=json.loads((folder/'usages.jsonl').read_text())
            row['generation_config']['model']='ltg/flan-t5-definition-en-xl'
            (folder/'usages.jsonl').write_text(json.dumps(row)+'\n')
            tutorial=builder.load_dataset('tkr','definitions',folder)
            self.assertEqual(tutorial['pipeline_id'],'t5-xl--mpnet')
            self.assertIn('FLAN-T5',tutorial['pipeline_label'])

    def test_explorer_uses_current_script_version(self):
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory)
            builder.write_explorer_page(site)
            content=(site/'clusters.html').read_text()
            version=hashlib.sha256((ROOT/'docs/assets/cluster-explorer.js').read_bytes()).hexdigest()[:16]
            self.assertIn('assets/cluster-explorer.js?v='+version,content)
            self.assertNotIn('src="assets/cluster-explorer.js"',content)
            self.assertNotIn('id="csv"',content)
            self.assertNotIn('id="datasetDownload"',content)

    def test_incomplete_result_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'result';self.write_data(folder,'usages',2)
            with self.assertRaisesRegex(ValueError,'totals disagree'):
                builder.load_dataset('tkr','usages',folder)

    def test_navigation_is_idempotent_and_word_specific(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)
            (site/'index.html').write_text('<p class="site-links">Links</p><section><h2>ström</h2><p>Examples</p></section>')
            (site/'examples.html').write_text('<p><a href="index.html">Home</a></p>')
            builder.integrate_navigation(site)
            first=(site/'index.html').read_text()
            self.assertIn('clusters.html?word=str%C3%B6m',first)
            builder.integrate_navigation(site)
            self.assertEqual(first,(site/'index.html').read_text())
            self.assertEqual((site/'examples.html').read_text().count('href="clusters.html"'),1)

if __name__=='__main__':
    unittest.main()
