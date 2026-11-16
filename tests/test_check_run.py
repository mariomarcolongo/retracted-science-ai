"""Offline checks of code/check_run.py, the check of a live run's logs (paper section 3.6, D68).

Usage: python3 -I tests/run_all.py   (or: python3 -m unittest discover -s tests -p 'test_check_run.py' -v)

Small run directories (manifest.json, plan.json, http.jsonl, runs.jsonl) and an endpoint snapshot are written by
hand: a clean live run, a flex tier, a half-price charge, a free endpoint, a request rejected after a tool call, a
model that never calls the tool, two providers, and a dry run. The real runner is also run in dry mode and checked.
Fixtures and logs are created only in temporary directories; no network is used.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_items
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
import check_run

CHAT = {'name': 'Model A', 'id': 'lab/model-a', 'provider': 'lab', 'api': 'chat'}
RESP = {'name': 'Model B', 'id': 'lab/model-b', 'provider': 'Lab/FP8', 'api': 'responses'}
FREE = {'name': 'Model F', 'id': 'lab/model-f:free', 'provider': 'lab', 'api': 'chat'}
PROMPT, COMPLETION = '0.000001', '0.000005'   # USD per token
FULL = 1000 * 0.000001 + 100 * 0.000005      # the expected charge of one fixture response


def response(m, cost=FULL, tier=None, provider='Lab'):
    """One logged HTTP response of model m: 1000 input tokens, 100 output tokens."""
    names = ('input_tokens', 'output_tokens') if m['api'] == 'responses' else ('prompt_tokens', 'completion_tokens')
    body = {'id': 'gen-1', 'model': m['id'] + '-20261101', 'provider': provider,
            'usage': {names[0]: 1000, names[1]: 100, 'cost': cost}}
    if tier != 'absent':
        body['service_tier'] = tier
    return {'uid': 'u1', 'kind': 'response', 'utc': '2026-11-16T10:00:00.000+00:00', 'http_status': 200, 'body': body,
            'model': m['name'], 'model_requested': m['id'], 'provider_requested': m['provider'], 'api': m['api'],
            'dry': False}


def answer(m, n, test='R3', called=True, outcome='complete', usable=True, error=None):
    """One terminal answer record of model m (pair n)."""
    calls = [{'n': 1, 'name': 'retraction_lookup', 'call_id': 'call_1', 'arguments': '{"doi": "10.9999/x"}',
              'valid': True, 'refused': False, 'doi': '10.9999/x', 'output': '{"notices": []}'}] if called else []
    return {'model_name': m['name'], 'pair_id': f'{n:02}', 'test': test, 'side': 'R', 'attempt': 1,
            'tools_offered': test not in ('R1', 'R2', 'SQ'), 'outcome': outcome, 'usable': usable, 'terminal': True,
            'tool_calls': calls, 'exchanges': [], 'error': error}


class CheckRunTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix='check-run-', dir='/tmp')
        self.tmp = Path(self.dir.name)
        self.endpoints = self.tmp / 'endpoints'
        self.endpoints.mkdir()
        tagged = lambda tag, p, c: {'tag': tag, 'service_tier': None, 'pricing': {'prompt': p, 'completion': c}}
        (self.endpoints / 'lab_model-a.json').write_text(json.dumps(   # the two snapshot layouts
            {'data': {'endpoints': [tagged('lab/flex', '0.0000005', '0.0000025'), tagged('lab', PROMPT, COMPLETION)]}}))
        (self.endpoints / 'lab_model-b.json').write_text(json.dumps({'endpoints': [tagged('lab/fp8', PROMPT, COMPLETION)]}))
        (self.endpoints / 'lab_model-f_free.json').write_text(json.dumps({'data': {'endpoints': [tagged('lab', '0', '0')]}}))

    def tearDown(self):
        self.dir.cleanup()

    def logdir(self, models, http, runs, dry=False, name='run'):
        d = self.tmp / name
        d.mkdir()
        (d / 'manifest.json').write_text(json.dumps({'phase': 'pilot', 'roles': 'tested', 'dry': dry, 'models': models,
                                                     'tests': ['R1', 'R3']}))
        (d / 'plan.json').write_text(json.dumps([[r['model_name'], r['pair_id'], r['test'], r['side']] for r in runs]))
        for file, records in (('http.jsonl', http), ('runs.jsonl', runs)):
            (d / file).write_text(''.join(json.dumps(r) + '\n' for r in records))
        return d

    def check(self, *a, **kw):
        lines, failures = check_run.check(str(self.logdir(*a, **kw)), str(self.endpoints))
        return '\n'.join(lines), failures

    def test_clean_live_run_passes(self):
        http = [response(CHAT), response(CHAT, tier='default'), response(RESP, tier='absent'), response(RESP)]
        runs = [answer(m, n) for m in (CHAT, RESP) for n in (1, 2)] + [answer(CHAT, 3, test='R1', called=False)]
        d = self.logdir([CHAT, RESP], http, runs)
        lines, failures = check_run.check(str(d), str(self.endpoints))
        text = '\n'.join(lines)
        self.assertEqual(failures, 0, text)
        self.assertEqual(text.count('PASS'), 4, text)   # price and tool calls; missing tier remains unverified
        self.assertIn('served tier not fully verified', text)
        self.assertIn('ratio 1.00', text)
        self.assertIn('called the tool in 2 of 2 conversations that offered it; 2 of those ended with a usable', text)
        self.assertIn('3 of 3 planned answers finished, 3 usable; outcomes: complete 3', text)
        cmd = [sys.executable, '-B', '-I', 'code/check_run.py', str(d), '--endpoints', str(self.endpoints)]
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('no failed checks; review NOTE entries', r.stdout.splitlines()[-1])
        self.assertEqual(sorted(p.name for p in d.iterdir()), ['http.jsonl', 'manifest.json', 'plan.json', 'runs.jsonl'])

    def test_flex_tier_fails(self):
        http = [response(CHAT), response(CHAT, tier='flex'), response(CHAT, tier='flex'), response(CHAT, tier='priority')]
        d = self.logdir([CHAT], http, [answer(CHAT, 1)])
        lines, failures = check_run.check(str(d), str(self.endpoints))
        self.assertEqual(failures, 1, lines)
        self.assertTrue(any('FAIL' in l and '3 of 4 responses' in l and 'flex 2, priority 1' in l for l in lines), lines)
        r = subprocess.run([sys.executable, '-B', '-I', 'code/check_run.py', str(d), '--endpoints', str(self.endpoints)],
                           cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(r.stdout.splitlines()[-1].startswith('RESULT: 1 check(s) FAILED — do not start'), r.stdout)

    def test_half_price_fails_and_free_endpoint_is_a_note(self):
        http = [response(CHAT, cost=FULL / 2), response(CHAT, cost=FULL / 2), response(FREE, cost=0)]
        text, failures = self.check([CHAT, FREE], http, [answer(CHAT, 1), answer(FREE, 1)])
        self.assertEqual(failures, 1, text)
        fail = [l for l in text.splitlines() if 'FAIL' in l]
        self.assertTrue('3 price' in fail[0] and 'ratio 0.50' in fail[0] and 'ached input tokens' in fail[0], text)
        self.assertIn('NOTE  3 price: free endpoint, not checked', text)

    def test_price_bounds_and_missing_data(self):
        for factor, expected in ((0.75, 0), (1.25, 0), (0.65, 1), (1.8, 1)):
            text, failures = self.check([CHAT], [response(CHAT, cost=FULL * factor)], [answer(CHAT, 1)],
                                        name=f'bound-{factor}')
            self.assertEqual(failures, expected, text)
        unknown = dict(CHAT, name='Unknown model', id='lab/unknown')
        text, failures = self.check([unknown, CHAT], [response(unknown), response(CHAT, cost=None)],
                                    [answer(unknown, 1), answer(CHAT, 1)], name='missing')
        self.assertEqual(failures, 0, text)
        self.assertIn('NOTE  3 price: no snapshot', text)
        self.assertIn('NOTE  3 price: no priced responses', text)

    def test_two_providers_fail(self):
        text, failures = self.check([CHAT], [response(CHAT), response(CHAT, provider='Other')], [answer(CHAT, 1)])
        self.assertEqual(failures, 1, text)
        self.assertIn('FAIL  2 provider and model: more than one provider answered (Lab 1, Other 1)', text)

    def test_missing_tier_is_not_evidence_of_standard_service(self):
        for body in ({}, {'service_tier': None}):
            status, message = check_run.tier_check([body])
            self.assertEqual(status, 'NOTE')
            self.assertIn('not fully verified', message)
        self.assertEqual(check_run.tier_check([{'service_tier': 'default'}])[0], 'PASS')

    def test_partial_prices_and_invalid_tools_remain_unverified(self):
        status, message = check_run.price_check(
            [response(CHAT)['body'], response(CHAT, cost=None)['body']], CHAT, self.endpoints)
        self.assertEqual(status, 'NOTE')
        self.assertIn('coverage is incomplete', message)
        row = answer(CHAT, 1)
        row['tool_calls'][0]['valid'] = False
        self.assertEqual(check_run.tool_check([row])[0], 'NOTE')

    def test_incomplete_or_duplicate_terminal_answers_fail(self):
        row = answer(CHAT, 1)
        self.assertEqual(check_run.summary([row], 2)[0], 'FAIL')
        self.assertEqual(check_run.summary([row, row], 1)[0], 'FAIL')

    def test_duplicate_model_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate model names'):
            self.check([CHAT, dict(CHAT, id='lab/other')], [], [])

    def test_api_error_after_tool_call_fails_with_its_text(self):
        error = 'request rejected (400): No tool call found for function call output ' + 'x' * 400
        runs = [answer(RESP, 1), answer(RESP, 2, outcome='API error', usable=False, error=error),
                answer(RESP, 3, called=False, outcome='API error', usable=False, error='rejected before any tool call')]
        text, failures = self.check([RESP], [response(RESP)], runs)
        self.assertEqual(failures, 1, text)
        fail = [l for l in text.splitlines() if 'FAIL' in l]
        self.assertTrue(fail[0].startswith('  FAIL  4 tool calls: 1 conversation(s)'), text)
        self.assertIn('First error: ' + error[:300], fail[0])
        self.assertNotIn(error[:301], fail[0])
        self.assertIn('API error 2, complete 1', text)

    def test_tool_calls_that_never_end_usable_fail(self):
        runs = [answer(CHAT, n, outcome='tool limit exhausted', usable=False) for n in (1, 2, 3)]
        text, failures = self.check([CHAT], [response(CHAT)], runs)
        self.assertEqual(failures, 1, text)
        self.assertIn('FAIL  4 tool calls: the model called the tool in 3 conversations and none', text)
        text, failures = self.check([CHAT], [response(CHAT)], runs[:2], name='two')   # too few to fail
        self.assertEqual(failures, 0, text)

    def test_model_that_never_calls_the_tool_is_a_note(self):
        runs = [answer(CHAT, n, called=False) for n in (1, 2, 3, 4)]
        text, failures = self.check([CHAT], [response(CHAT)], runs)
        self.assertEqual(failures, 0, text)
        self.assertIn('NOTE  4 tool calls: the model never called the tool in 4 conversations', text)

    def test_dry_run_skips_the_live_checks(self):
        http = [response(CHAT, tier='flex', cost=FULL / 2), response(CHAT, provider='Other')]   # would fail live
        text, failures = self.check([CHAT], http, [answer(CHAT, 1)], dry=True)
        self.assertEqual(failures, 0, text)
        self.assertIn('NOTE  checks 1-3 (service tier, provider, price) skipped', text)
        self.assertNotIn('1 service tier', text)
        self.assertIn('PASS  4 tool calls', text)
        self.assertIn('NOTE  5 summary: 1 of 1 planned', text)

    def test_missing_files_exit_2(self):
        d = self.logdir([CHAT], [response(CHAT)], [answer(CHAT, 1)])
        (d / 'runs.jsonl').unlink()
        r = subprocess.run([sys.executable, '-B', '-I', 'code/check_run.py', str(d)], cwd=ROOT, text=True,
                           capture_output=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('missing runs.jsonl', r.stdout)


class RealRunnerTests(unittest.TestCase):
    """The real runner in dry mode writes the logs; check_run must read them as they are."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix='check-run-', dir='/tmp')
        self.tmp = Path(self.dir.name)
        make_items(self.tmp, pairs=1)

    def tearDown(self):
        self.dir.cleanup()

    def run_dry(self, name, mode):
        logdir = self.tmp / name
        cmd = [sys.executable, '-B', '-I', 'code/run_tests.py', str(self.tmp / 'items.json'), str(logdir), '--registry',
               str(self.tmp / 'registry.csv'), '--phase', 'pilot', '--models', 'Hydrogen,Luna', '--tests', 'R1,R3,SQ',
               '--dry', '--dry-mode', mode]
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines, failures = check_run.check(str(logdir))
        return '\n'.join(lines), failures

    def test_real_dry_run_has_no_failure(self):
        text, failures = self.run_dry('normal', 'normal')
        self.assertEqual(failures, 0, text)
        self.assertEqual(text.count('PASS  4 tool calls: the model called the tool in 1 of 1 conversations'), 2, text)
        self.assertEqual(text.count('4 of 4 planned answers finished, 4 usable; outcomes: complete 4'), 2, text)
        self.assertEqual(text.count('skipped'), 2, text)

    def test_real_dry_run_with_rejected_tool_result_fails(self):
        text, failures = self.run_dry('rejected', 'error-after-tool')
        self.assertEqual(failures, 2, text)   # both models, chat and Responses API
        self.assertEqual(text.count('First error: dry: request rejected (400)'), 2, text)


if __name__ == '__main__':
    unittest.main()
