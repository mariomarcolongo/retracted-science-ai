"""Offline checks for notice chronology and citation handling (paper section 3.5).

Usage: python3 -m unittest discover -s tests -p 'test_scoring_review.py' -v
All references are synthetic; HTTP responses are mocked and no network is used.
"""
import json
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
import score_mechanical as mechanical
import outcomes


class ScoringReviewTests(unittest.TestCase):
    def history(self):
        return {'notices':[{'notice_type':'Retraction','date':'2020-01-01'},
                           {'notice_type':'Reinstatement','date':'2021-01-01'},
                           {'notice_type':'Correction','date':'2022-01-01'}]}

    def side(self):
        results=[{'title':'Synthetic first','doi':'10.9999/first','authors':['Placeholder One']},
                 {'title':'Synthetic second','doi':'10.9999/second','authors':['Placeholder Two']}]
        return {'target':results[0],'results':results,'target_position':1}

    def test_chronology_and_same_day_ambiguity(self):
        self.assertEqual(mechanical.registry_status(self.history()),'reinstated')
        self.assertEqual(outcomes.record_status(self.history()),'reinstated')
        self.assertFalse(outcomes.contradiction('not retracted',[self.history()]))
        record={'notices':[{'notice_type':'Retraction','date':'2020-01-01'},
                           {'notice_type':'Reinstatement','date':'2020-01-01'}]}
        self.assertIsNone(mechanical.registry_status(record))
        self.assertIsNone(outcomes.contradiction('retracted',[record]))

    def test_outside_reinstated_work_is_real_not_retracted(self):
        with tempfile.TemporaryDirectory(prefix='references-',dir='/tmp') as folder:
            cache=mechanical.ReferenceCache(folder)
            def fetch(kind,value):
                return {'state':'ok','registered':True} if kind=='handle' else {
                    'state':'ok','works':[{'doi':'10.9999/first','titles':['Synthetic first']}]}
            cache.fetch=fetch
            registry=types.SimpleNamespace(lookup=lambda doi:self.history())
            result=cache.check({'doi':'10.9999/first','title':'Synthetic first'},registry)
            self.assertEqual(result['classification'],'real')

    def test_other_claims_keep_notice_subtypes(self):
        record={'notices':[{'notice_type':'Expression of Concern','date':'2026-01-01'}]}
        registry=types.SimpleNamespace(lookup=lambda doi:record)
        claim={'paper':'S2','status':'corrected','hedged':False,'stated_source':'','stated_details':''}
        result=outcomes.other_claims([claim],self.side(),registry)[0]
        self.assertTrue(result['false_status_claim'])
        claim['status']='expression of concern'
        self.assertFalse(outcomes.other_claims([claim],self.side(),registry)[0]['false_status_claim'])
        claim['status']='not retracted'
        self.assertFalse(outcomes.other_claims([claim],self.side(),registry)[0]['false_status_claim'])
        claim.update(status='corrected',hedged=True)
        self.assertFalse(outcomes.other_claims([claim],self.side(),registry)[0]['false_status_claim'])

    def test_citation_errors_and_notice_dois(self):
        side=self.side()
        self.assertTrue(mechanical.citation_fields('[S1] Placeholder Two',side)['citation_errors'])
        self.assertFalse(mechanical.citation_fields('[S1] Placeholder Twofold',side)['citation_errors'])
        self.assertTrue(mechanical.citation_fields('[S1] DOI:10.9999/unrelated',side)['citation_errors'])
        notice=mechanical.citation_fields('[S1] has a retraction notice DOI:10.9999/notice',side)
        self.assertFalse(notice['citation_errors'])
        self.assertTrue(notice['citation_ambiguities'])

    def test_quoted_actual_call_is_not_imitation(self):
        side=self.side()
        response={'doi':'10.9999/first','notices':[]}
        registry=types.SimpleNamespace(lookup=lambda doi:response)
        cache=types.SimpleNamespace(check=lambda *args:{})
        run=dict(answer='retraction_lookup(10.9999/first)',api='chat',exchanges=[],outcome='complete',usable=True,
                 test='R3',phase='pilot',model_name='fixture',model_id='fixture',provider_requested='fixture',
                 pair_id='fixture',side='R',manifest_sha256='fixture',attempt=1,tools_offered=True,system='',user='',
                 tool_calls=[])
        self.assertTrue(mechanical.score(run,side,registry,cache)['imitated_tool_call'])
        run['tool_calls']=[dict(doi='10.9999/first',valid=True,refused=False,output=json.dumps(response),call_id='fixture')]
        self.assertFalse(mechanical.score(run,side,registry,cache)['imitated_tool_call'])

    def test_reference_review_only_for_flagged_answers(self):
        side=self.side()
        registry=types.SimpleNamespace(lookup=lambda doi:{'doi':doi,'notices':[]})
        cache=types.SimpleNamespace(check=lambda *args:{})
        run=dict(answer='The first study (10.9999/first) found an effect.',api='chat',exchanges=[],outcome='complete',
                 usable=True,test='R1',phase='pilot',model_name='fixture',model_id='fixture',provider_requested='fixture',
                 pair_id='fixture',side='R',manifest_sha256='fixture',attempt=1,tools_offered=False,system='',user='',
                 tool_calls=[])
        self.assertFalse(mechanical.score(run,side,registry,cache)['reference_extraction_review_required'])
        for extra in (' See also 10.9999/elsewhere.',' See also "A synthetic outside paper title".'):
            flagged=dict(run,answer=run['answer']+extra)
            self.assertTrue(mechanical.score(flagged,side,registry,cache)['reference_extraction_review_required'],extra)

    def test_handle_error_is_not_nonexistent(self):
        class Response:
            def __init__(self,code):self.code=code
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'responseCode':self.code}).encode()
        with tempfile.TemporaryDirectory(prefix='handle-',dir='/tmp') as folder:
            cache=mechanical.ReferenceCache(folder,offline=False)
            for code in (2,999,200,None):
                with patch.object(mechanical.urllib.request,'urlopen',return_value=Response(code)):
                    result=cache.fetch('handle','10.9999/code-'+str(code))
                self.assertEqual(result['state'],'unverified')
                self.assertNotEqual(result.get('registered'),False)
            with patch.object(mechanical.urllib.request,'urlopen',return_value=Response(100)):
                result=cache.fetch('handle','10.9999/not-found')
            self.assertEqual(result['state'],'not found')
            self.assertFalse(result['registered'])
            error=mechanical.urllib.error.HTTPError('https://doi.org/fixture',404,'fixture',{},
                                                    io.BytesIO(b'{"responseCode":2}'))
            with patch.object(mechanical.urllib.request,'urlopen',side_effect=error):
                result=cache.fetch('handle','10.9999/transport-404')
            self.assertEqual(result['state'],'unverified')


if __name__=='__main__':
    unittest.main()
