"""Hand-calculated statistical checks (paper section 3.6).

Usage: python3 -m unittest discover -s tests -p 'test_stats.py'
"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"code"))
import stats_common as s


class StatisticsTests(unittest.TestCase):
    def test_wilson_edges(self):
        self.assertEqual(s.wilson(0, 0), (None, None))
        self.assertAlmostEqual(s.wilson(0, 10)[1], .2775327999, places=8)
        self.assertAlmostEqual(s.wilson(10, 10)[0], .7224672001, places=8)

    def test_published_newcombe_method10(self):
        # Original Table III: e20,f12,g2,h16; method8 differs so this detects that mistake.
        lo, hi = s.newcombe(20, 12, 2, 16)
        self.assertAlmostEqual(lo, .0562, places=4)
        self.assertAlmostEqual(hi, .3292, places=4)
        self.assertEqual(s.newcombe(0, 0, 0, 0), (None, None))
        self.assertGreater(s.newcombe(0, 0, 0, 10)[1], 0)

    def test_midp_and_holm(self):
        self.assertEqual(s.mcnemar_midp(0, 0), 1)
        self.assertEqual(s.mcnemar_midp(5, 0), 1/32)
        self.assertEqual(s.mcnemar_midp(3, 3), 1-20/128)  # Fagerland tie case: 1 - P(X=3)/2, X ~ Bin(6, 1/2)
        self.assertAlmostEqual(s.mcnemar_midp(2, 7), 2*(1+9+36)/512-36/512)
        self.assertEqual(s.holm([.01, .04, .03]), [.03, .06, .06])
        self.assertEqual(s.holm([.01, None, .03]), [.03, None, .06])

    def test_agreement(self):
        a = s.agreement(["a", "a", "b", "b"], ["a", "b", "b", "b"])
        self.assertEqual(a["agreement"], .75)
        self.assertEqual(a["kappa"], .5)
        self.assertIsNone(s.agreement([True]*4, [True]*4)["kappa"])

    def test_topic_bootstrap(self):
        self.assertEqual(s.pooled([], resamples=10)["n"], 0)
        self.assertEqual(s.pooled([0, .5, -.25, 0], resamples=10)["nonzero"], 2)
        r = s.pooled([0, 0], resamples=100)
        self.assertEqual((r["mean"], r["ci_low"], r["ci_high"], r["p_value"]), (0,0,0,1))
        r = s.pooled([1, 1], resamples=10000)
        self.assertEqual((r["n"], r["mean"], r["ci_low"], r["ci_high"]), (2,1,1,1))
        self.assertGreater(r["p_value"], .45)
        self.assertLess(r["p_value"], .55)


if __name__ == "__main__":
    unittest.main()
