"""D68 regression checks: matched prompts and truthful registry despite forged status.

Synthetic fixtures only. The full scoring/analysis effect check is test_planted.py.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from fixtures import make_items
import materials as M


class LabelledForgeryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='d68-', dir='/tmp')
        self.items = make_items(self.tmp.name, pairs=5)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_forged_update_differs_at_every_target_position(self):
        for item in self.items:
            side = item['R']
            s2, u2, t2 = M.render('R2', side)
            s5, u5, t5 = M.render('R5', side)
            s6, u6, t6 = M.render('R6', side)
            self.assertEqual((s2, u2), (s5, u5))
            self.assertFalse(t2)
            self.assertTrue(t5 and t6)
            self.assertEqual(s5, s6)
            update = M.status_lines('R4', side)
            self.assertEqual(u6.count(update), 1)
            self.assertEqual(u6.replace(update, ''), u5)
            self.assertEqual(u6.count('Publication type: Retracted Publication'), 1)
            for test in ('R5', 'R6'):
                self.assertEqual(M.precheck(test, side, *M.render(test, side)), [])

    def test_missing_duplicate_and_cross_condition_notices_are_rejected(self):
        side = self.items[0]['R']
        system, user, tool = M.render('R6', side)
        label = M.status_lines('R5', side)
        update = M.status_lines('R4', side)
        for changed in (user.replace(label, ''), user.replace(update, ''), user + update):
            self.assertTrue(M.precheck('R6', side, system, changed, tool))
        self.assertTrue(M.precheck('R5', side, system, user, tool))
        self.assertTrue(M.precheck('R6', side, system, user, False))

    def test_forgery_does_not_change_registry_evidence(self):
        registry = M.Registry(Path(self.tmp.name) / 'registry.csv')
        side = self.items[0]['R']
        before = registry.lookup(side['target']['doi'])
        for test in ('R3', 'R4', 'R5', 'R6'):
            M.render(test, side)
            self.assertEqual(registry.lookup(side['target']['doi']), before)
        self.assertTrue(before['notices'])
        self.assertFalse(registry.lookup(side['forged']['doi'])['notices'])


if __name__ == '__main__':
    unittest.main()
