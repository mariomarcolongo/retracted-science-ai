"""Offline execution regression checks (paper sections 3.3, 3.5 and 3.6).

Usage: python3 -m unittest discover -s tests -p 'test_execution.py' -v
Fixtures and logs are created only in temporary directories; no network is used.
"""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from budget import RequestBudget, BudgetReached
import openrouter


def load_functions(path, names, namespace):
    nodes = [n for n in ast.parse(path.read_text()).body if getattr(n, 'name', None) in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class BudgetTests(unittest.TestCase):
    def test_unknown_cost_is_reserved_and_survives_resume(self):
        records = [dict(uid='a', kind='request'), dict(uid='a', kind='response', body={'usage':{}})]
        budget = RequestBudget(.5, .25, records)
        self.assertEqual(budget.spent, .25)
        budget.observe(dict(uid='b', kind='request'))
        budget.observe(dict(uid='b', kind='error'))
        with self.assertRaises(BudgetReached):
            budget.observe(dict(uid='c', kind='request'))
        self.assertEqual(budget.unknown_attempts, 2)
        self.assertEqual(RequestBudget(1, .25, [records[0]]).spent, .25)

    def test_values_and_inflight(self):
        for ceiling, reserve in [(float('nan'), .1), (1, 0), (1, float('inf')), (-1, .1)]:
            with self.assertRaises(ValueError):
                RequestBudget(ceiling, reserve)
        budget = RequestBudget(.25, .25)
        budget.observe(dict(uid='a', kind='request'))
        with self.assertRaises(BudgetReached):
            budget.observe(dict(uid='b', kind='request'))
        budget.observe(dict(uid='a', kind='response', body={'usage':{'cost':'0.01'}}))
        self.assertEqual(budget.known_cost, .01)

    def test_transient_attempts_each_pass_budget_gate(self):
        body = {'error':{'code':500}, 'usage':{'cost':.1}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return json.dumps(body).encode()
        budget = RequestBudget(.15, .1)
        with patch.object(openrouter, '_key', return_value='fixture-token'), \
             patch.object(openrouter.urllib.request, 'urlopen', return_value=Response()) as send, \
             patch.object(openrouter.time, 'sleep'):
            with self.assertRaises(BudgetReached):
                openrouter._post('chat/completions', {}, log=budget.observe)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(budget.known_cost, .1)


class ConversationTests(unittest.TestCase):
    def test_blank_final_tools_off_is_terminal(self):
        namespace = {'MAX_TOKENS':16000, 'now':lambda:'fixture',
                     'M':types.SimpleNamespace(tools_chat=lambda:[]),
                     'client':types.SimpleNamespace(chat=None),
                     'openrouter':types.SimpleNamespace(usage_fields=lambda *a:{})}
        namespace['request'] = lambda *a, **kw: ({'choices':[{'message':{'content':''}, 'finish_reason':'stop'}]}, 0)
        load_functions(ROOT/'code/run_tests.py', {'converse', 'outcome_of'}, namespace)
        result = namespace['converse']({'api':'chat', 'id':'fixture', 'provider':'fixture'}, '', '', True,
                                       {'refused':True, 'exchanges':[]})
        self.assertEqual(namespace['outcome_of'](*result), ('tool limit exhausted', False, True))


class DryRunTests(unittest.TestCase):
    def test_modes_resume_context_and_invalid_judgments(self):
        with tempfile.TemporaryDirectory(prefix='execution-', dir='/tmp') as folder:
            tmp = Path(folder)
            item = {'pair_id':'fixture'}
            for side in ('R', 'K'):
                target = {'title':'Synthetic target '+side,'authors':[], 'journal':'Synthetic Journal',
                          'year':2025,'doi':'10.9999/target-'+side.lower(),'abstract':'A health outcome was measured.',
                          'conclusion':'The outcome increased.', 'retraction_date':'2026-07-01',
                          'retraction_doi':'10.9999/notice'}
                results = [dict(target, is_target=True)]
                for i in range(2, 6):
                    results.append(dict(target, title='Synthetic result '+str(i), doi='10.9999/result-'+str(i), is_target=False))
                item[side] = {'target':target,'results':results,'target_position':1,'topic':'health outcomes',
                              'forged':{'date':'2026-10-01','doi':'10.9999/forged'}}
            items = tmp/'items.json'; items.write_text(json.dumps([item]))
            registry = tmp/'registry.csv';registry.write_text('OriginalPaperDOI,Record ID,RetractionDate,RetractionNature,Reason,RetractionDOI\n')
            def run(command, expected=0):
                result = subprocess.run([sys.executable, '-I']+command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
                return result
            for mode in ('normal','tool-loop','empty','ratelimit','error-after-tool'):
                logdir = tmp/mode
                cmd = ['code/run_tests.py',str(items),str(logdir),'--registry',str(registry),
                       '--phase','pilot','--models','Hydrogen,Luna','--tests','R1,R3,SQ','--dry','--dry-mode',mode]
                run(cmd)
                rows = [json.loads(l) for l in (logdir/'runs.jsonl').read_text().splitlines()]
                terminal = [r for r in rows if r['terminal']]
                self.assertEqual(len(terminal), 8)
                requests = [json.loads(l) for l in (logdir/'http.jsonl').read_text().splitlines() if json.loads(l)['kind']=='request']
                self.assertEqual(len(requests), len({r['uid'] for r in requests}))
                self.assertTrue(all(r['topic_id']=='fixture' and r['test'] in ('R1','R3','SQ') for r in requests))
                if mode=='tool-loop': self.assertEqual(max(len(r['exchanges']) for r in terminal), 8)
                if mode=='empty': self.assertTrue(all(r['attempt']==4 and not r['usable'] for r in terminal))
                if mode=='error-after-tool':
                    errors = [r for r in terminal if r['outcome']=='API error']
                    self.assertEqual(len(errors), 2)
                    self.assertTrue(all(len(r['exchanges'])==1 for r in errors))
                if mode=='normal':
                    count = len(requests);run(cmd)
                    self.assertEqual(count, sum(json.loads(l)['kind']=='request' for l in (logdir/'http.jsonl').read_text().splitlines()))
                    judgecmd = ['code/judge.py',str(items),str(logdir),'--dry']
                    run(judgecmd)
                    jpath = logdir/'judging-dry/judging.jsonl'
                    judgments = [json.loads(l) for l in jpath.read_text().splitlines()]
                    self.assertEqual(len(judgments), 16)
                    for row in judgments: row.update(attempt=4, valid=False, form=None)
                    jpath.write_text(''.join(json.dumps(r)+'\n' for r in judgments))
                    # D66: answers the main judges could not score go to their backups.
                    self.assertIn('backup judges: 16 answers', run(judgecmd).stdout)
                    judgments = [json.loads(l) for l in jpath.read_text().splitlines()]
                    self.assertEqual(sum(1 for r in judgments if r.get('replaces') and r['valid']), 16)
                    for row in judgments: row.update(attempt=4, valid=False, form=None)
                    jpath.write_text(''.join(json.dumps(r)+'\n' for r in judgments))
                    self.assertIn('without valid form 16', run(judgecmd, 1).stdout)


if __name__ == '__main__':
    unittest.main()
