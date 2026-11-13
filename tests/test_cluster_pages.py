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

    def test_dictionary_combinations_are_distinct_and_expose_encoder_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'dictionary';self.write_data(folder,'definitions')
            row=json.loads((folder/'usages.jsonl').read_text())
            row['generation_config'].update(model='FrancescoPeriti/LlamaDictionary-sv-de-en_ML38BI',base_model='meta-llama/Meta-Llama-3-8B-Instruct',language='sv')
            (folder/'usages.jsonl').write_text(json.dumps(row)+'\n')
            for encoder,alias,prefix in [('KBLab/sentence-bert-swedish-cased','kblab',''),('intfloat/multilingual-e5-large','e5-large','query: '),('oxfrug/bge-m3-swedish-superlim','bge-m3-swedish',''),('Qwen/Qwen3-Embedding-8B','qwen3-8b','Instruct: Clustering\nQuery:'),('BAAI/bge-m3','bge-m3','')]:
                path=folder/'clustering_manifest.json';manifest=json.loads(path.read_text())
                manifest.update(embedding_model=encoder,embedding_input_prefix=prefix,embedding_output='dense')
                path.write_text(json.dumps(manifest))
                data=builder.load_dataset('tkr','definitions',folder)
                self.assertEqual(data['pipeline_id'],'llamadictionary-sv-de-en-ml38bi--'+alias)
                self.assertEqual(data['encoder_model'],encoder)
                self.assertEqual(data['manifest']['embedding_input_prefix'],prefix)
                self.assertEqual(data['manifest']['generation']['language'],'sv')
                self.assertEqual(data['manifest']['generation']['base_model'],'meta-llama/Meta-Llama-3-8B-Instruct')
            row['generation_config'].update(prompt='llamadictionary-sv-usage-guide-v2',
                temperature=0.001,repetition_penalty=1.2,stop_strings=['.', ' .'],do_sample=True)
            (folder/'usages.jsonl').write_text(json.dumps(row)+'\n')
            guide=builder.load_dataset('tkr','definitions',folder)
            self.assertEqual(guide['pipeline_id'],'llamadictionary-sv-de-en-ml38bi--bge-m3--guide-v2')
            self.assertIn('usage-guide v2',guide['pipeline_label'])
            self.assertEqual(guide['manifest']['generation']['repetition_penalty'],1.2)
            self.assertEqual(guide['manifest']['generation']['stop_strings'],['.', ' .'])

    def test_local_swedish_generators_have_separate_public_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'local';self.write_data(folder,'definitions')
            manifest=json.loads((folder/'clustering_manifest.json').read_text())
            manifest['embedding_model']='KBLab/sentence-bert-swedish-cased'
            (folder/'clustering_manifest.json').write_text(json.dumps(manifest))
            row=json.loads((folder/'usages.jsonl').read_text());identities=[]
            for name in sorted(builder.LOCAL_DICTIONARIES):
                row['generation_config'].update(model=name,prompt='llamadictionary-sv-usage-guide-v2',revision='checkpoint-hash')
                (folder/'usages.jsonl').write_text(json.dumps(row)+'\n')
                data=builder.load_dataset('tkr','definitions',folder)
                expected=name.lower().replace('_','-')+'-local--kblab--guide-v2'
                self.assertEqual(data['pipeline_id'],expected)
                self.assertIn('(local)',data['pipeline_label'])
                identities.append(data['id'])
            self.assertEqual(len(set(identities)),3)

    def test_incomplete_result_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'result';self.write_data(folder,'usages',2)
            with self.assertRaisesRegex(ValueError,'totals disagree'):
                builder.load_dataset('tkr','usages',folder)

    def test_mia_catalog_is_separate_and_loads_one_word_at_a_time(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory);site=workspace/'site'
            mia=workspace/'focus-projects/data/clustered_definitions_test_mia_kvinnsam'
            mats=workspace/'focus-projects/data/clustered_definitions_test_mats_lb'
            self.write_data(mia,'definitions');self.write_data(mats,'definitions')
            builder.build(workspace,site,dataset='mia')
            catalog=json.loads((site/'data/clusters/manifest.json').read_text())
            self.assertEqual([d['corpus'] for d in catalog['datasets']],['kvinnsam'])
            entry=catalog['datasets'][0]
            data=json.loads((site/entry['data']).read_text())
            self.assertEqual(data['rows'],[])
            self.assertEqual(data['words'],['bank'])
            rows=json.loads((site/data['word_files']['bank']).read_text())
            self.assertEqual(len(rows),entry['usage_count'])
            self.assertIn('Mia word frequencies',(site/'clusters.html').read_text())

    def test_mia_pending_page_needs_no_finished_results(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory);site=workspace/'site'
            (workspace/'focus-projects').mkdir()
            (workspace/'focus-projects/mia_definition_experiments.json').write_text(json.dumps([
                dict(pipeline_id='test',pipeline_label='Test combination')]))
            builder.build(workspace,site,dataset='mia')
            catalog=json.loads((site/'data/clusters/manifest.json').read_text())
            self.assertEqual(catalog['datasets'],[])
            self.assertEqual(catalog['pending'][0]['pipeline_id'],'test')

    def test_navigation_is_idempotent_and_word_specific(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)
            (site/'index.html').write_text('<p class="site-links">Links</p><section><h2>ström</h2><p>Examples</p></section>')
            (site/'examples.html').write_text('<p><a href="index.html">Home</a></p>')
            (site/'associations.html').write_text('Association graph')
            builder.integrate_navigation(site)
            first=(site/'index.html').read_text()
            self.assertIn('clusters.html?word=str%C3%B6m',first)
            builder.integrate_navigation(site)
            self.assertEqual(first,(site/'index.html').read_text())
            self.assertEqual((site/'examples.html').read_text().count('href="clusters.html"'),1)
            self.assertEqual(first.count('href="associations.html"'),1)
            self.assertEqual((site/'examples.html').read_text().count('href="associations.html"'),1)
            builder.write_explorer_page(site)
            self.assertEqual((site/'clusters.html').read_text().count('href="associations.html"'),1)

if __name__=='__main__':
    unittest.main()
