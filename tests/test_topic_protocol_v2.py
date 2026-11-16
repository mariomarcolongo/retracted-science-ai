"""Offline checks for frozen development requests, resumes, and review provenance."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import draft_topics_v2 as D
import openrouter


class TopicProtocolTests(unittest.TestCase):
    def fixture_package(self, root):
        package = root / "protocol"; package.mkdir()
        prompt = "Generate one neutral question from the supplied title and abstract.\n"
        (package / "PROMPT.txt").write_text(prompt)
        (package / "PROTOCOL.md").write_text("Offline fixture protocol.\n")
        cfg = {"model": "fixture", "provider": openrouter._provider("fixture"),
               "temperature": 0, "top_p": 1, "max_tokens": 4000}
        requests = []
        for i in range(6):
            body = {**cfg, "messages": [{"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps({"title": f"Fixture {i}", "abstract": "A source abstract."})}]}
            requests.append({"item_code": str(i), "body": body, "request_sha256": D.digest(body)})
        path = root / "requests.json"; path.write_text(json.dumps(requests))
        manifest = {"request_configuration": cfg, "prior_source_sha256": {},
                    "candidate_artifact_sha256": {str(p.relative_to(root)): D.file_hash(p)
                        for p in (package / "PROMPT.txt", package / "PROTOCOL.md", path)}}
        (package / "manifest.json").write_text(json.dumps(manifest))
        return package, path, requests, manifest

    def test_frozen_requests_are_isolated_and_uniform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); package, path, _, _ = self.fixture_package(root)
            with mock.patch.object(D, "ROOT", root):
                requests, manifest = D.prepared_requests(package, path)
                self.assertEqual(len(requests), 6)
                for r in requests:
                    self.assertEqual(set(json.loads(r["body"]["messages"][1]["content"])), {"title", "abstract"})
                    self.assertEqual(r["body"]["messages"][0]["content"], (package / "PROMPT.txt").read_text())
                    self.assertEqual(D.digest(r["body"]), r["request_sha256"])
                (package / "PROMPT.txt").write_text("changed")
                with self.assertRaisesRegex(SystemExit, "artifact changed"):
                    D.prepared_requests(package, path)

    def test_sampling_settings_only_added_when_requested(self):
        with mock.patch.object(openrouter, "_post", return_value=({}, 0)) as post:
            openrouter.chat("model", "provider", [], temperature=0, top_p=1)
            self.assertEqual(post.call_args.args[1]["temperature"], 0)
            self.assertEqual(post.call_args.args[1]["top_p"], 1)
            openrouter.chat("model", "provider", [])
            self.assertNotIn("temperature", post.call_args.args[1])
            self.assertNotIn("top_p", post.call_args.args[1])

    def test_format_is_not_scientific_approval(self):
        self.assertEqual(D.output_status("NEEDS_REVIEW", "stop"), "needs_review")
        self.assertEqual(D.output_status("A question?", "length"), "incomplete_or_unverified_finish")
        self.assertEqual(D.output_status("Explanation.\nA question?", "stop"), "format_requires_review")
        self.assertEqual(D.output_status("First? Second?", "stop"), "format_requires_review")
        self.assertEqual(D.output_status("What is the relationship?", "stop"), "pending_scientific_review")

    def test_completed_failures_not_rerolled_and_human_review_preserved(self):
        calls = []
        def chat(model, provider, messages, **kwargs):
            idx = len(calls); calls.append(messages)
            response = {"choices": [{"message": {"content": "NEEDS_REVIEW" if idx == 0 else "What is the effect?"},
                                      "finish_reason": "stop"}], "usage": {"cost": .01}}
            body = {"model": model, "provider": openrouter._provider(provider), "messages": messages,
                    **{k: kwargs[k] for k in ("temperature", "top_p", "max_tokens")}}
            kwargs["log"]({"kind": "request", "uid": str(idx), "utc": "fixture", "body": body})
            kwargs["log"]({"kind": "response", "uid": str(idx), "utc": "fixture", "http_status": 200, "body": response})
            return response, 0
        with tempfile.TemporaryDirectory() as fixtures, tempfile.TemporaryDirectory() as tmp:
            package, path, requests, manifest = self.fixture_package(Path(fixtures))
            with mock.patch.object(D, "PACKAGE", package), mock.patch.object(D, "REQUESTS", path), \
                 mock.patch.object(D, "prepared_requests", return_value=(requests, manifest)), \
                 mock.patch.object(openrouter, "chat", side_effect=chat):
                self.check_resume(tmp, calls)

    def check_resume(self, tmp, calls):
            result = D.run(tmp, 1)
            self.assertEqual(result["completed"], 6)
            self.assertAlmostEqual(result["known_cost_usd"], .06)
            path = Path(tmp) / "stage-a-review.csv"
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 36)
            rows[0]["decision"] = "uncertain"
            with path.open("w", newline="") as f:
                w=csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            old = path.read_bytes()
            D.run(tmp, 1)
            self.assertEqual(len(calls), 6)
            self.assertEqual(path.read_bytes(), old)
            with self.assertRaisesRegex(SystemExit, "manifest changed"):
                D.run(tmp, 1, dry=True)
            # Simulate crash after HTTP completion but before the draft was saved.
            drafts = Path(tmp) / "drafts.jsonl"
            lines = drafts.read_text().splitlines()
            drafts.write_text("\n".join(lines[:-1])+"\n")
            D.run(tmp, 1)
            self.assertEqual(len(calls), 6)
            restored = json.loads(drafts.read_text().splitlines()[-1])
            self.assertTrue(restored["recovered_from_http"])


if __name__ == "__main__":
    unittest.main()
