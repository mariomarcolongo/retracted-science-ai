import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import review_material_candidates as C


class CandidateReviewTests(unittest.TestCase):
    def assess(self, assessments):
        source = {"question": "What is the evidence?", "candidates": [
            {"candidate_id": "a", "title": "First study", "abstract": "Animal training was investigated."},
            {"candidate_id": "b", "title": "Second study", "abstract": "Cells were studied in vitro."}]}
        request = {"item_code": "fixture", "task_id": "fixture-judge", "request_sha256": "fixture",
                   "body": {"model": "fixture", "messages": [{"role": "system", "content": "fixture"},
                             {"role": "user", "content": json.dumps(source)}]}}
        response = {"choices": [{"message": {"content": json.dumps({"assessments": assessments})}, "finish_reason": "stop"}]}
        return C.interpret("candidate-review", request, response, "fixture", 0)

    def entry(self, quote):
        return {**{k:"pass" for k in C.CRITERIA}, "evidence": quote, "reason": "Direct contribution."}

    def test_quote_must_belong_to_own_candidate(self):
        r = self.assess({"a": self.entry("Animal training"), "b": self.entry("Animal training")})
        self.assertTrue(r["assessments"]["a"]["provisional_pass"])
        self.assertFalse(r["assessments"]["b"]["provisional_pass"])

    def test_missing_candidate_never_approved(self):
        self.assertEqual(self.assess({"a": self.entry("First study")})["status"], "needs_review")

    def test_one_failed_criterion_cannot_be_outvoted(self):
        entry = self.entry("First study"); entry["B2_scope"] = "fail"
        r = self.assess({"a": entry, "b": self.entry("Second study")})
        self.assertFalse(r["assessments"]["a"]["provisional_pass"])
        self.assertTrue(r["assessments"]["a"]["evidence_and_schema_valid"])


if __name__ == "__main__": unittest.main()
