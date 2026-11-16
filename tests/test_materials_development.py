"""Development provenance, isolation and completion recovery without network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import materials_development as M
from generate_search_queries import compile_query
import openrouter


class DevelopmentTests(unittest.TestCase):
    def fixture(self, directory):
        path = Path(directory) / "source.jsonl"
        rows = []
        for i in range(6):
            row = {"item_code": str(i), "source": {"title": f"Source {i}", "abstract": "Observed animal model performance."},
                   "raw_text": "How do animal models perform?", "request_sha256": str(i), "dry": False,
                   "draft": "How do animal models perform?", "status": "pending_scientific_review"}
            row["content_sha256"] = M.digest({"request_sha256": row["request_sha256"], "raw_text": row["raw_text"]})
            rows.append(row)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return path

    def test_task_inputs_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.fixture(tmp)
            for phase, fields, count in [("topics", {"title", "abstract"}, 6),
                                          ("question-review", {"title", "abstract", "question"}, 12),
                                          ("queries", {"question"}, 6)]:
                requests = M.requests_for(phase, source)
                self.assertEqual(len(requests), count)
                for r in requests:
                    self.assertEqual(len(r["body"]["messages"]), 2)
                    self.assertEqual(set(json.loads(r["body"]["messages"][1]["content"])), fields)

    def test_synonyms_versioned_and_syntax_safe(self):
        groups = {"context": ["microsurgery", "supermicrosurgery"], "focus": ["training", "simulation"]}
        with self.assertRaises(ValueError):
            compile_query(groups, "Does training help microsurgery?")
        self.assertIn("OR", compile_query(groups, "Does training help microsurgery?", "search-query-v2"))
        for bad in ['training) OR (anything', 'training OR anything', 'train*', 'a']:
            with self.assertRaises(ValueError):
                compile_query({**groups, "focus": [bad]}, "question", "search-query-v2")

    def test_invalid_evidence_does_not_pass(self):
        review = {"criteria": {f"A{i}": {"decision": "pass", "evidence": "Observed", "reason": "Supported"}
                               for i in range(1,7)}, "summary": "Provisional."}
        M.review_check(review, {"abstract": "Observed animal performance."})
        review["criteria"]["A1"]["evidence"] = "invented evidence"
        with self.assertRaisesRegex(ValueError, "substring"):
            M.review_check(review, {"abstract": "Observed animal performance."})

    def test_anchor_query_binds_meaning_to_question_text(self):
        groups = {"context": {"anchor": "microsurgery", "alternatives": ["supermicrosurgery"]},
                  "focus": {"anchor": "training", "alternatives": []}}
        query = compile_query(groups, "What evidence is available on microsurgery training?", "search-query-v3")
        self.assertIn("supermicrosurgery", query)
        groups["context"]["anchor"] = "another disease"
        with self.assertRaisesRegex(ValueError, "verbatim"):
            compile_query(groups, "What evidence is available on microsurgery training?", "search-query-v3")

    def test_v4_schema_and_uniform_neutral_stem(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(M, "PACKAGE", M.ROOT / "protocol/materials-development-v4"):
            source = self.fixture(tmp)
            requests = M.requests_for("question-review", source)
            self.assertTrue(all(r["body"]["response_format"]["json_schema"]["strict"] for r in requests))
            r = M.requests_for("topics", source)[0]
            response = {"choices": [{"message": {"content": "How useful is a model?"}, "finish_reason": "stop"}]}
            self.assertEqual(M.interpret("topics", r, response, "fixture", 0)["status"], "format_requires_review")

    def test_first_completed_failure_retained_and_http_recovered(self):
        calls = []
        def fake_chat(model, provider, messages, **kwargs):
            i = len(calls); calls.append(messages)
            response = {"choices": [{"message": {"content": "NEEDS_REVIEW" if i == 0 else "How do animal models perform?"},
                                      "finish_reason": "stop"}], "usage": {"cost": .01}}
            body = {"model": model, "provider": openrouter._provider(provider), "messages": messages,
                    **{k: kwargs[k] for k in ("temperature", "top_p", "max_tokens")}}
            kwargs["log"]({"kind": "request", "uid": str(i), "utc": "fixture", "body": body})
            kwargs["log"]({"kind": "response", "uid": str(i), "utc": "fixture", "http_status": 200, "body": response})
            return response, 0
        with tempfile.TemporaryDirectory() as tmp:
            source = self.fixture(tmp); log = Path(tmp) / "run"
            with self.assertRaisesRegex(ValueError, "prepare exact"):
                M.run("topics", source, log, 1)
            M.run("topics", source, log, prepare_only=True)
            with mock.patch.object(openrouter, "chat", side_effect=fake_chat):
                M.run("topics", source, log, 1)
                lines = (log / "drafts.jsonl").read_text().splitlines()
                self.assertEqual(json.loads(lines[0])["status"], "needs_review")
                (log / "drafts.jsonl").write_text("\n".join(lines[:-1]) + "\n")
                M.run("topics", source, log, 1)
                self.assertEqual(len(calls), 6)
                self.assertTrue(json.loads((log / "drafts.jsonl").read_text().splitlines()[-1])["recovered_from_http"])
                self.assertAlmostEqual(json.loads((log / "summary.json").read_text())["known_cost_usd"], .06)
                source.write_text(source.read_text().replace("Source 0", "Changed source 0"))
                with self.assertRaisesRegex(ValueError, "manifest changed"):
                    M.run("topics", source, log, 1)


if __name__ == "__main__":
    unittest.main()
