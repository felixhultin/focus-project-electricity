import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

WORKSPACE=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('cooccurrence_clustering',WORKSPACE/'focus-projects/cooccurrence_clustering.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
spec=importlib.util.spec_from_file_location('cluster_builder',WORKSPACE/'focus-project-electricity/docs/downloads/build_cluster_pages.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class CooccurrenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:import sklearn
        except ImportError:raise unittest.SkipTest('Requires .venv-languagechange-cpu scikit-learn')

    def test_clear_groups_and_empty_contexts_are_distinct(self):
        contexts=[['vatten','flod']]*8+[['elektrisk','ledning']]*8+[[]]
        labels,words,report=c.cluster_contexts(contexts)
        self.assertEqual(len(set(labels[:8])),1)
        self.assertEqual(len(set(labels[8:16])),1)
        self.assertNotEqual(labels[0],labels[8])
        self.assertEqual(labels[-1],0)
        self.assertEqual(set(words[str(labels[0])]),{'vatten','flod'})
        self.assertEqual(report['selected_k'],2)
        self.assertEqual(report['uninformative'],1)
        self.assertGreater(report['selected_silhouette'],.99)
        self.assertEqual((labels,words,report),c.cluster_contexts(contexts))

    def test_tiny_and_uninformative_contexts(self):
        self.assertEqual(c.cluster_contexts([[],[]])[0],[0,0])
        self.assertEqual(c.cluster_contexts([['ensam']])[0],[0])
        labels,_,report=c.cluster_contexts([['vatten']]*5)
        self.assertEqual(labels,[1]*5)
        self.assertEqual(report['selected_k'],1)

    def test_end_to_end_shared_labels_and_site_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for corpus in c.CORPORA:
                folder=root/'target_usages'/corpus/'mats_sampled';folder.mkdir(parents=True)
                if corpus=='kubhist2':filename='kubhist2-aftonbladet-1900.xml.bz2_strom.jsonl'
                elif corpus=='kubhist':filename='kubhist-dalpilen-1900.xml.bz2_strom.jsonl'
                else:filename=corpus+'-open.xml.bz2_strom.jsonl'
                records=[]
                for phrase in ['ström vatten flod']*4+['ström elektrisk ledning']*4:
                    records.append(dict(text=phrase,lemma='ström',start=0,end=5,date='1901',id=str(len(records)),url=None))
                (folder/filename).write_text('\n'.join(json.dumps(r) for r in records))
                (folder/'sampling_manifest.json').write_text(json.dumps(dict(sampling_period='year',per_word_year_cap=30,seed=42,sampled_usages=8)))
            c.run(root,root/'run',root/'site',publish=False)
            discovered=b.discover(root)
            self.assertEqual(len(discovered),4)
            datasets=[b.load_dataset(*entry) for entry in discovered]
            self.assertTrue(all(d['method']=='cooccurrence' and d['pipeline_id']=='cooccurrence-tfidf' for d in datasets))
            labels=[[r['cluster'] for r in d['rows']] for d in datasets]
            self.assertTrue(all(row==labels[0] for row in labels))
            self.assertNotEqual(labels[0][0],labels[0][-1])
            self.assertTrue(all(d['rows'][0]['text'][d['rows'][0]['start']:d['rows'][0]['end']]=='ström' for d in datasets))
            paper=next(d for d in datasets if d['corpus']=='kubhist2')
            self.assertEqual(paper['rows'][0]['resource_id'],'aftonbladet')
            self.assertIn('characteristic_words',paper['manifest'])
            self.assertEqual(paper['manifest']['shared_clustering']['corpora'],c.CORPORA)
            b.build(root,root/'site')
            manifest=json.loads((root/'site/data/clusters/manifest.json').read_text())
            self.assertEqual(len(manifest['datasets']),4)

if __name__=='__main__':unittest.main()
