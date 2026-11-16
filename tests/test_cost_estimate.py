"""Offline accounting checks for the planning estimate (paper Appendix I).

Usage: python3 -m unittest discover -s tests -p 'test_cost_estimate.py'
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cost_estimate", ROOT/"code/cost_estimate.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CostEstimateTests(unittest.TestCase):
    def setUp(self):
        self.config = {"tested": [{"id": "m", "provider": "p"}],
                       "drafter": {"id": "d", "provider": "p"},
                       "judges": [{"id": "j1", "provider": "p"}, {"id": "j2", "provider": "p"}],
                       "backups": [{"id": "b1", "provider": "p"}, {"id": "b2", "provider": "p"}]}
        self.prices = {m: {"input": .001, "output": .002, "list_input": .003,
                           "list_output": .004, "source": "fixture"}
                       for m in ("m", "d", "j1", "j2", "b1", "b2")}

    def test_complete_answer_inventory(self):
        rows = [r for r in mod.estimate(self.config, self.prices, 10, 3) if r["scenario"] == "low"]
        tested = [r for r in rows if r["role"] == "tested model"]
        # Ten tests (D68). Main 100 + status 20; pilot 30 + status 6; stability 2 x 5 pairs x 6 tests = 60: 216.
        self.assertEqual(sum(r["answers"] for r in tested), 216)
        self.assertEqual(sum(r["answers"] for r in rows if r["phase"] == "knowledge check"), 130)
        for judge in ("j1", "j2"):
            self.assertEqual(sum(r["answers"] for r in rows if r["phase"] == "judging" and r["model_id"] == judge), 346)
        self.assertAlmostEqual(sum(r["answers"] for r in rows if r["phase"] == "drafting"), 28.6)

    def test_tool_reasoning_charged_each_round(self):
        rows = mod.estimate(self.config, self.prices, 10, 0)
        r = next(r for r in rows if r["scenario"] == "mid" and r["phase"] == "main run" and r["test"] == "R3")
        # Two rounds: input2300+2500, output700+2000+2000+200.
        self.assertAlmostEqual(r["input_tokens"], 49440)
        self.assertAlmostEqual(r["output_tokens"], 50470)
        self.assertAlmostEqual(r["estimate_usd"], 150.38)
        self.assertAlmostEqual(r["requests"], 20.6)

    def test_exact_endpoint_no_prefix_fallback(self):
        with tempfile.TemporaryDirectory(prefix="cost-fixture-", dir="/tmp") as directory:
            p = Path(directory)
            model_ids = list(self.prices)
            (p/"catalogue.json").write_text(json.dumps({"data": [{"id": m,"pricing": {"prompt":".1","completion":".2"}} for m in model_ids]}))
            for m in model_ids:
                (p/(m+".json")).write_text(json.dumps({"data":{"endpoints":[
                    {"tag":"p/flex","pricing":{"prompt":"0","completion":"0"}},
                    {"tag":"p","pricing":{"prompt":".3","completion":".4"}}]}}))
            prices = mod.load_prices(p/"catalogue.json", self.config, p)
            self.assertEqual(prices["m"]["input"], .3)
            (p/"m.json").write_text(json.dumps({"data":{"endpoints":[{"tag":"p/flex","pricing":{"prompt":"0","completion":"0"}}]}}))
            with self.assertRaises(ValueError):
                mod.load_prices(p/"catalogue.json", self.config, p)

    def test_real_pinned_price_provenance(self):
        config = json.loads((ROOT/"code/models.json").read_text())
        prices = mod.load_prices(ROOT/"data/snapshots/openrouter_models_2026-11-13.json", config, ROOT/"data/snapshots/endpoints")
        self.assertEqual(prices["z-ai/glm-5.2"]["input"], .0000014)
        self.assertEqual(prices["z-ai/glm-5.2"]["output"], .0000044)


if __name__ == "__main__":
    unittest.main()
