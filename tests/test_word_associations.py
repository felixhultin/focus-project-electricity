import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH=Path(__file__).resolve().parents[1]/'docs/downloads/build_word_associations.py'
spec=importlib.util.spec_from_file_location('associations',PATH)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def row(text,year=1901):
    start=text.index('ström')
    return dict(text=text,start=start,end=start+5,lemma='ström',date=str(year),id='example',url='file:///private')

class AssociationsTest(unittest.TestCase):
    def test_resource_identity_across_years_and_author_urls(self):
        for year in [1870,1880]:
            result=a.resource_identity('kubhist2',Path(f'kubhist2-post-ochinrikestidningar-{year}.xml.bz2_strom.jsonl'),{},
                                       {'post-ochinrikestidningar':'Post- och Inrikes Tidningar'})
            self.assertEqual(result,dict(id='post-ochinrikestidningar',label='Post- och Inrikes Tidningar',kind='newspaper'))
        result=a.resource_identity('lb',Path('lb-open_strom.jsonl'),dict(url='https://litteraturbanken.se/f%C3%B6rfattare/StrindbergA/titlar/Test'))
        self.assertEqual(result['id'],'StrindbergA')
        self.assertEqual(a.resource_identity('lb',Path('lb-open.jsonl'),{})['id'],'unknown-author')

    def test_resources_have_independent_counts_training_and_excerpts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'target_usages/kubhist2/mats_sampled';folder.mkdir(parents=True)
            for paper,word in [('aftonbladet','vatten'),('dalpilen','ånga')]:
                records=[row(f'ström {word}')]*3
                (folder/f'kubhist2-{paper}-1900.xml.bz2_strom.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
            (folder/'sampling_manifest.json').write_text(json.dumps(dict(sampling_period='year',sampled_usages=6,per_word_year_cap=30,seed=42)))
            source=a.read_source(root,'kubhist2',include_resources=True)
            self.assertEqual(sum(sum(s['totals'].values()) for s in source['resources'].values()),6)
            for identifier,word in [('aftonbladet','vatten'),('dalpilen','ånga')]:
                subset=source['resources'][identifier]
                self.assertEqual(subset['totals'][('ström',1901)],3)
                self.assertEqual(set(subset['counts'][('ström',1901)]),{word})
                self.assertEqual(subset['sentences'][1901],[['ström',word]]*3)
                self.assertEqual(a.cooccurrence_rows(subset,'ström',1901)[0]['share'],1)
                self.assertEqual(subset['sampling']['parent_sampled_usages'],6)
            site=root/'site';meta=a.write_corpus(root,site,'kubhist2')
            before=(site/meta['files']['ström']).read_bytes()
            entries=a.write_resources(root,site,'kubhist2')
            self.assertEqual(len(entries),2)
            self.assertEqual((site/meta['files']['ström']).read_bytes(),before)
            submeta=json.loads((site/entries[0]['data']).read_text())
            exported=json.loads((site/submeta['files']['ström']).read_text())
            self.assertEqual(exported['years'][0]['n'],3)
            self.assertEqual(exported['years'][0]['cooccurrence'][0]['word'],'vatten')
            a.write_corpus(root,site,'kubhist2')
            parent=json.loads((site/'data/associations/kubhist2/manifest.json').read_text())
            self.assertEqual(parent['resources'],entries)

    def test_context_counts_unique_words_and_bounded_window(self):
        text='utanför '+' '.join(['och']*10)+' ström vatten vatten äfven ÅNGA'
        target,tokens,nearby,evidence=a.context(row(text))
        self.assertEqual(target,'ström')
        self.assertEqual(nearby,{'vatten','ånga'})
        self.assertEqual(tokens.count('vatten'),2)
        self.assertIsNone(evidence['url'])
        with self.assertRaises(ValueError):a.context(dict(row(text),end=len(text)+1))

    def test_yearly_denominators_and_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'target_usages/tkr/mats_sampled';folder.mkdir(parents=True)
            records=[row('ström vatten vatten'),row('ström vatten'),row('ström och'),row('ström ånga',1902)]
            (folder/'strom.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
            manifest=dict(sampling_period='year',sampled_usages=4,per_word_year_cap=30,seed=42)
            (folder/'sampling_manifest.json').write_text(json.dumps(manifest))
            source=a.read_source(root,'tkr')
            point=a.cooccurrence_rows(source,'ström',1901)[0]
            self.assertEqual(point['count'],2)
            self.assertAlmostEqual(point['share'],2/3)
            self.assertEqual(len(point['examples']),2)
            site=root/'site';meta=a.write_corpus(root,site,'tkr')
            data=json.loads((site/meta['files']['ström']).read_text())
            self.assertEqual([(y['year'],y['n']) for y in data['years']],[(1901,3),(1902,1)])
            self.assertEqual(data['years'][1]['cooccurrence'],[])
            manifest['sampled_usages']=5
            (folder/'sampling_manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'counts disagree'):a.read_source(root,'tkr')

    def test_training_window_and_real_cosines(self):
        try:import gensim
        except ImportError:self.skipTest('Use .venv-languagechange-cpu for Word2Vec test')
        from collections import Counter
        source=dict(sentences={1901:[['ström','vatten','flod','ström','vatten']]*60,
                               1920:[['framtid','laser']]*60},totals=Counter({('ström',1901):60}))
        settings=copy.deepcopy(a.SETTINGS)
        settings['minimum_training_tokens']=100
        settings['word2vec'].update(vector_size=10,min_count=2,epochs=3)
        result=a.fit_year(source,1901,settings)
        self.assertEqual(result['training_contexts'],60)
        self.assertEqual(result['training_tokens'],300)
        self.assertEqual({p['word'] for p in result['results']['ström']},{'vatten','flod'})
        self.assertTrue(all(-1<=p['cosine']<=1 for p in result['results']['ström']))
        self.assertEqual(result,a.fit_year(source,1901,settings))
        self.assertIn('unavailable',a.fit_year(source,1910,settings))

if __name__=='__main__':unittest.main()
