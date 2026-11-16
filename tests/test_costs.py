"""Offline cost export checks (paper section 4 and Appendix I).

Usage: python3 -m unittest discover -s tests -p 'test_costs.py' -v
All request fixtures, estimates and exports are created under /tmp.
"""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
import costs
import environment as runtime_environment


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))


class CostTests(unittest.TestCase):
    def test_runtime_metadata_and_commit_are_exported(self):
        with tempfile.TemporaryDirectory(prefix='environment-',dir='/tmp') as folder:
            root=Path(folder)
            git=root/'.git';git.mkdir()
            (git/'HEAD').write_text('ref: refs/heads/main\n')
            self.assertIsNone(runtime_environment.git_commit(root))
            commit='a'*40
            (git/'packed-refs').write_text(commit+' refs/heads/main\n')
            self.assertEqual(runtime_environment.git_commit(root),commit)
            source=root/'sample.py';source.write_text('pass\n')
            info=runtime_environment.capture_environment([source])
            self.assertTrue(info['python'])
            self.assertEqual(set(info['code_sha256']),{'sample.py'})
            self.assertNotIn(folder,json.dumps(info))
            info['git_commit']=commit
            live=self.fixture(root)
            write_jsonl(live/'events.jsonl',[
                dict(info,event='run started',utc='2026-11-15T10:00:00+00:00'),
                dict(info,event='run ended',utc='2026-11-15T10:00:10+00:00')])
            exported=costs.environment(live/'http.jsonl','run-1')
            self.assertEqual(exported['git_commit'],commit)
            self.assertEqual(json.loads(exported['package_versions']),info['packages'])
            self.assertAlmostEqual(exported['elapsed_hours'],10/3600)

    def fixture(self, root, dry=False):
        directory = root/('dry' if dry else 'live')
        directory.mkdir()
        (directory/'manifest.json').write_text(json.dumps({'phase':'pilot','dry':dry}))
        requests = []
        for uid, kind in [('one','response'),('two','error'),('three',None)]:
            requests.append(dict(uid=uid,kind='request',utc='2026-11-15T10:00:00+00:00',attempt=1,
                                 phase='judging',source_phase='pilot',role='judge',test='R3',topic_id='fixture',
                                 model_requested='fixture-model',provider_requested='fixture-provider',
                                 dry=dry,body={'model':'fixture-model','unapproved_metadata':'PRIVATE_MARKER'}))
            if kind:
                if kind=='response':
                    requests.append(dict(uid=uid,kind=kind,utc='2026-11-15T10:00:02+00:00',seconds=2,
                                         body={'id':'fixture-response','model':'fixture-model','provider':'fixture-provider',
                                               'usage':{'prompt_tokens':100,'completion_tokens':20,'cost':.2},
                                               'choices':[{'finish_reason':'stop'}], 'account_id':'PRIVATE_MARKER'}))
                else:
                    requests.append(dict(uid=uid,kind=kind,utc='2026-11-15T10:00:03+00:00',http_status=500,
                                         error='PRIVATE_MARKER'))
        write_jsonl(directory/'http.jsonl', requests)
        write_jsonl(directory/'events.jsonl',[
            {'event':'judging started','utc':'2026-11-15T10:00:00+00:00','python':'3.fixture',
             'platform':'fixture-os','code_sha256':'fixture-hash'},
            {'event':'judging ended','utc':'2026-11-15T10:00:03+00:00'}])
        return directory

    def test_allowlist_unknown_dry_and_source_phase(self):
        with tempfile.TemporaryDirectory(prefix='costs-',dir='/tmp') as folder:
            root = Path(folder)
            live, dry = self.fixture(root), self.fixture(root,True)
            prices = {'fixture-model':{'prompt':'.001','completion':'.002'}}
            rows = costs.request_rows(live/'http.jsonl','run-1',prices)
            self.assertEqual([r['cost_usd'] for r in rows],[.2,None,None])
            self.assertAlmostEqual(rows[0]['list_price_usd'],.14)
            self.assertIsNone(rows[0]['reasoning_tokens'])
            summary = costs.summaries(rows)[0]
            self.assertEqual(summary['source_phase'],'pilot')
            self.assertIsNone(summary['cost_usd'])
            self.assertEqual(summary['cost_usd_known'],.2)
            # D66: the request that failed with a recorded error is not charged; only the unrecorded one is unknown.
            self.assertEqual(summary['missing_cost_requests'],1)
            self.assertIsNone(summary['elapsed_hours'])
            dry_rows = costs.request_rows(dry/'http.jsonl','run-2',prices)
            self.assertEqual([r['cost_usd'] for r in dry_rows],[0,0,0])
            self.assertEqual(costs.summaries(dry_rows)[0]['synthetic_reported_cost_usd'],.2)
            self.assertEqual(costs.summaries(dry_rows)[0]['cost_usd'],0)
            output=root/'export'
            result=subprocess.run([sys.executable,'-I','code/costs.py','--logs',str(live),str(dry),
                                   '--output',str(output)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with (output/'requests.csv').open() as stream:
                self.assertEqual(tuple(csv.DictReader(stream).fieldnames), costs.REQUEST_FIELDS)
            for file in output.iterdir():
                self.assertNotIn('PRIVATE_MARKER',file.read_text())
            self.assertEqual({f.name for f in output.iterdir()},
                             {'requests.csv','summary.csv','estimate_vs_actual.csv','environment.csv','cost_coverage.json'})
            self.assertIsNone(costs.environment(live/'http.jsonl','run-1')['git_commit'])

    def test_estimate_context_and_manual_inputs(self):
        with tempfile.TemporaryDirectory(prefix='costs-',dir='/tmp') as folder:
            root=Path(folder);live=self.fixture(root)
            rows=costs.request_rows(live/'http.jsonl','run-1',{})
            expected={'scenario':'mid','phase':'judging','source_phase':'pilot','role':'judge',
                      'model_id':'fixture-model','provider':'fixture-provider','test':'R3','estimate_usd':'.5'}
            result=costs.compare_estimate([expected],rows)[0]
            self.assertEqual(result['actual_requests'],3)
            self.assertEqual(result['actual_known_usd'],.2)
            self.assertIsNone(result['actual_cost_usd'])
            self.assertEqual(result['coverage'],'unknown charges')
            complete=costs.compare_estimate([expected],rows[:1])[0]
            self.assertEqual(complete['actual_cost_usd'],.2)
            self.assertAlmostEqual(complete['difference_usd'],-.3)
            self.assertEqual(costs.compare_estimate([],rows)[0]['coverage'],'not in supplied estimate')
            other=dict(expected,source_phase='main run')
            self.assertEqual(costs.compare_estimate([other],rows)[0]['coverage'],'not run')
            other=dict(expected,provider='another-provider')
            self.assertEqual(costs.compare_estimate([other],rows)[0]['coverage'],'not run')
            manual=costs.manual_summary([dict(source='paid (OpenRouter)',amount='4',unit='USD',note='PRIVATE_MARKER')],
                                        [dict(phase='analysis',hours='1.5',note='PRIVATE_MARKER')])
            self.assertEqual(manual['author_hours_by_phase'],{'analysis':1.5})
            self.assertEqual(manual['deposits'][0]['amount'],4)
            self.assertNotIn('PRIVATE_MARKER',json.dumps(manual))
            self.assertIn('not inferable',manual['credit_source_allocation'])

    def test_duplicate_request_ids_and_protected_output_rejected(self):
        with tempfile.TemporaryDirectory(prefix='costs-',dir='/tmp') as folder:
            root=Path(folder);live=self.fixture(root)
            records=costs.read_jsonl(live/'http.jsonl')
            write_jsonl(live/'http.jsonl',records+[records[0]])
            with self.assertRaises(ValueError): costs.request_rows(live/'http.jsonl','run-1',{})
            result=subprocess.run([sys.executable,'-I','code/costs.py','--logs',str(live),
                                   '--output',str(ROOT/'data/costs/forbidden-test-output')],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((ROOT/'data/costs/forbidden-test-output').exists())


    def test_knowledge_check_phase_matches_the_estimate_label(self):
        # The runner writes phase "knowledge_check"; the estimate rows say "knowledge check".
        self.assertEqual(costs.phase_name('knowledge_check','status question'),'knowledge check')
        self.assertEqual(costs.phase_name('main','R4-I'),'instruction test')
        self.assertEqual(costs.phase_name('stability','R3'),'stability')
        import cost_estimate
        config={'tested':[],'drafter':{'id':'d','provider':'p'},'judges':[],'backups':[]}
        prices={'d':{'input':0,'output':0,'list_input':0,'list_output':0,'source':'test'}}
        phases={r['phase'] for r in cost_estimate.estimate(config,prices,1,0)}
        self.assertIn(costs.phase_name('knowledge_check',''),phases)

if __name__=='__main__':
    unittest.main()
