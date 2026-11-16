"""Offline checks for the fixes C1-C6 (16 Nov 2026): tools-off final turn, provider outages in the runner and the
judges, notice DOIs in the lookup tool, abstract boilerplate cleaning.

Usage: python3 -I tests/run_all.py   (or: python3 -m unittest discover -s tests -p 'test_robustness.py' -v)
Fixtures and logs are created only in temporary directories; no network is used.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
import materials as M
import openrouter

REG_HEADER = 'OriginalPaperDOI,Record ID,RetractionDate,RetractionNature,Reason,RetractionDOI\n'


def fixture(tmp):
    item = {'pair_id': 'fixture'}
    for side in ('R', 'K'):
        target = {'title': 'Synthetic target ' + side, 'authors': [], 'journal': 'Synthetic Journal', 'year': 2025,
                  'doi': '10.9999/target-' + side.lower(), 'abstract': 'A health outcome was measured.',
                  'conclusion': 'The outcome increased.', 'retraction_date': '2026-07-01',
                  'retraction_doi': '10.9999/notice'}
        results = [dict(target, is_target=True)]
        for i in range(2, 6):
            results.append(dict(target, title='Synthetic result ' + str(i), doi='10.9999/result-' + str(i),
                                is_target=False))
        item[side] = {'target': target, 'results': results, 'target_position': 1, 'topic': 'health outcomes',
                      'forged': {'date': '2026-10-01', 'doi': '10.9999/forged'}}
    items = tmp / 'items.json'
    items.write_text(json.dumps([item]))
    registry = tmp / 'registry.csv'
    registry.write_text(REG_HEADER + '10.9999/target-r,1,7/1/2026 0:00,Retraction,+Concerns/Issues about Data;,10.9999/notice\n')
    return items, registry


def rows(path):
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix='robustness-', dir='/tmp')
        self.tmp = Path(self.dir.name)
        self.items, self.registry = fixture(self.tmp)

    def tearDown(self):
        self.dir.cleanup()

    def run_tests(self, logdir, models, mode, tests='R3,K3', expected=0, env=None):
        cmd = [sys.executable, '-I', 'code/run_tests.py', str(self.items), str(logdir), '--registry',
               str(self.registry), '--phase', 'pilot', '--models', models, '--tests', tests, '--dry', '--dry-mode', mode]
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return r

    def test_c1_final_turn_without_tools_where_none_is_unsupported(self):
        logdir = self.tmp / 'c1'
        self.run_tests(logdir, 'ERNIE,Hydrogen', 'tool-loop')
        runs = [r for r in rows(logdir / 'runs.jsonl') if r['terminal']]
        ernie = [r for r in runs if r['model_name'].startswith('ERNIE')]
        hydrogen = [r for r in runs if r['model_name'] == 'Gemini 4 Hydrogen']
        self.assertEqual(len(ernie), 2)
        for r in ernie:  # final request had no tools and no tool_choice; the answer is usable
            last = r['exchanges'][-1]
            self.assertEqual((last['tool_choice'], last['tools_sent']), (None, False))
            self.assertEqual((r['outcome'], r['usable']), ('complete', True))
        for r in hydrogen:  # unchanged for endpoints that accept tool_choice "none"
            last = r['exchanges'][-1]
            self.assertEqual((last['tool_choice'], last['tools_sent']), ('none', True))
        bodies = [h['body'] for h in rows(logdir / 'http.jsonl') if h['kind'] == 'request'
                  and h['model'].startswith('ERNIE')]
        self.assertTrue(all(b.get('tool_choice') != 'none' for b in bodies))

    def test_c2_tool_call_after_tools_off_is_not_usable(self):
        logdir = self.tmp / 'c2'
        self.run_tests(logdir, 'Hydrogen', 'ignore-none')
        runs = [r for r in rows(logdir / 'runs.jsonl') if r['terminal']]
        self.assertEqual(len(runs), 2)
        self.assertTrue(all((r['outcome'], r['usable']) == ('tool limit exhausted', False) for r in runs))

    def test_c3_intermittent_outage_is_retried_without_using_attempts(self):
        logdir = self.tmp / 'c3a'
        self.run_tests(logdir, 'Hydrogen,Luna', 'outage', tests='R1,R3,SQ')
        runs = rows(logdir / 'runs.jsonl')
        terminal = [r for r in runs if r['terminal']]
        self.assertEqual(len(terminal), 8)
        self.assertTrue(all(r['usable'] and r['attempt'] == 1 for r in terminal))
        events = rows(logdir / 'events.jsonl')
        self.assertTrue(any(e['event'] == 'provider unavailable' for e in events))
        self.assertFalse(any(r['outcome'] == 'API error' for r in runs))

    def test_c3_persistent_outage_stops_model_and_resume_finishes(self):
        logdir = self.tmp / 'c3b'
        self.run_tests(logdir, 'Hydrogen,Luna', 'outage-down', tests='R1,R3,SQ', expected=1)
        runs = rows(logdir / 'runs.jsonl')
        self.assertFalse(any(r['model_name'] == 'Gemini 4 Hydrogen' and r['terminal'] for r in runs))
        self.assertEqual(sum(r['terminal'] for r in runs if r['model_name'] == 'GPT-6 Luna'), 4)
        events = rows(logdir / 'events.jsonl')
        stops = [e for e in events if e['event'] == 'model stopped for this run (provider unavailable)']
        self.assertEqual([e['model'] for e in stops], ['Gemini 4 Hydrogen'])
        self.assertGreaterEqual(sum(e['event'] == 'provider unavailable' for e in events), 5)
        # Resume after the outage: the open jobs run, and none uses up an answer attempt.
        self.run_tests(logdir, 'Hydrogen,Luna', 'outage-down', tests='R1,R3,SQ', expected=1)  # same manifest
        self.run_tests(logdir, 'Hydrogen,Luna', 'outage-down', tests='R1,R3,SQ',
                       env={**os.environ, 'DRY_PROVIDER_BACK': '1'})  # provider back
        terminal = [r for r in rows(logdir / 'runs.jsonl') if r['terminal']]
        self.assertEqual(len(terminal), 8)
        self.assertTrue(all(r['usable'] and r['attempt'] == 1 for r in terminal))

    def test_c4_judge_outage_stops_judge_and_resume_finishes(self):
        logdir = self.tmp / 'c4'
        self.run_tests(logdir, 'Hydrogen', 'normal', tests='R1,SQ')
        judge = [sys.executable, '-I', 'code/judge.py', str(self.items), str(logdir), '--dry']
        r = subprocess.run(judge + ['--dry-outage'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        jd = logdir / 'judging-dry'
        first = rows(jd / 'judging.jsonl')
        self.assertTrue(first and len({j['judge'] for j in first}) == 1)  # only the second judge wrote forms
        self.assertTrue(any(e['event'] == 'judge stopped for this run (provider unavailable)'
                            for e in rows(jd / 'events.jsonl')))
        r = subprocess.run(judge, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        final = rows(jd / 'judging.jsonl')
        self.assertEqual(len(final), 6)
        self.assertTrue(all(j['valid'] and j['attempt'] == 1 for j in final))


class ClientTests(unittest.TestCase):
    def test_c3_classification(self):
        self.assertIsInstance(openrouter._classify(404, 'No endpoints found for x'), openrouter.Unavailable)
        e = openrouter._classify(400, 'bad request')
        self.assertIsInstance(e, openrouter.CallFailed)
        self.assertNotIsInstance(e, openrouter.Unavailable)
        self.assertIsNone(openrouter._classify(503, 'down'))


class RegistryTests(unittest.TestCase):
    def test_c5_notice_doi_returns_its_notice(self):
        with tempfile.TemporaryDirectory(prefix='robustness-', dir='/tmp') as d:
            _, reg = fixture(Path(d))
            R = M.Registry(str(reg))
            art = R.lookup('10.9999/target-r')
            self.assertEqual(art['notices'][0]['notice_doi'], '10.9999/notice')
            notice = R.lookup('https://doi.org/10.9999/NOTICE')
            self.assertEqual(notice['doi_is_notice_for'], ['10.9999/target-r'])
            self.assertEqual(notice['notices'][0]['notice_type'], 'Retraction')
            self.assertEqual(R.lookup('10.9999/forged')['notices'], [])

    def test_c5_lookup_subtypes(self):
        import score_mechanical as S
        with tempfile.TemporaryDirectory(prefix='robustness-', dir='/tmp') as d:
            items, _ = fixture(Path(d))
            side = json.loads(items.read_text())[0]['R']
        calls = [{'doi': x, 'valid': True, 'refused': False, 'output': '{"notices": []}', 'call_id': str(i)}
                 for i, x in enumerate(['10.9999/notice', '10.9999/forged', '10.9999/result-2'])]
        got = [c['doi_relation'] for c in S.lookup_fields(calls, side)['lookup_calls']]
        self.assertEqual(got, ['real notice DOI', 'forged notice DOI', 'supplied'])
        self.assertEqual(S.registry_status({'doi_is_notice_for': ['x'], 'notices': [{'notice_type': 'Retraction',
                                                                                     'date': '2026-01-01'}]}),
                         'not retracted')


class CleaningTests(unittest.TestCase):
    def test_c6_boilerplate_removed_content_kept(self):
        cases = {
            'Results were clear. Copyright © 2015 The Authors. Journal of Applied Toxicology published by John Wiley & Sons Ltd.':
                'Results were clear.',
            'We found an effect. J. Cell. Biochem. 117: 2719-2736, 2016. © 2016 Wiley Periodicals, Inc.':
                'We found an effect.',
            'It may serve as a target.(Fig. graphical abstract)': 'It may serve as a target.',
            'Text here. [Image: see text]': 'Text here.',
            'This article is protected by copyright. All rights reserved.': '',
        }
        for raw, want in cases.items():
            self.assertEqual(M.clean_abstract(raw)[0], want, raw)
        for keep in ('Patients (c) and controls (d) were compared over 2015-2016 in 3 groups.',
                     'The copyright of data was discussed; outcomes improved.',
                     'Published by Kare and colleagues, the scale was used.'):
            self.assertEqual(M.clean_abstract(keep), (keep, []))


if __name__ == '__main__':
    unittest.main()
