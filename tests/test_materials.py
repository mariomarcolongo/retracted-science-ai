"""Offline regression fixtures for the material and knowledge-check safeguards.

Usage: python3 -m unittest discover -s tests -p test_materials.py -v
Implements checks of paper sections 3.4–3.5 and Appendix F. All writes use /tmp.
"""
import contextlib, csv, hashlib, importlib.util, io, json, pathlib, runpy, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
sys.path.insert(0, str(CODE))
import knowledge_check as KC
import draft_topics as DT


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def sheet(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def script(name, args):
    with mock.patch.object(sys, "argv", [name] + list(map(str, args))), contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(CODE / name), run_name="__main__")


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="materials-tests-", dir="/tmp")
        self.d = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_ten_point_boundary(self):
        self.assertFalse(KC.exceeds_threshold(4, 10, 3, 10))
        self.assertTrue(KC.exceeds_threshold(5, 10, 3, 10))
        self.assertFalse(KC.exceeds_threshold(0, 10, 2, 10))
        with self.assertRaises(ValueError): KC.exceeds_threshold(0, 1, 0, 0)

    def test_incomplete_knowledge_run_refused(self):
        manifest = {"roles": "aux", "tests": ["SQ"], "models": [{"name": "fixture", "id": "fixture", "provider": "fixture"}]}
        dump(self.d / "manifest.json", manifest)
        dump(self.d / "plan.json", [["fixture", "p", "SQ", "R"], ["fixture", "p", "SQ", "K"]])
        (self.d / "runs.jsonl").write_text(json.dumps({"model_name": "fixture", "pair_id": "p", "test": "SQ",
                                                   "side": "R", "terminal": True, "model_id": "fixture", "provider_requested": "fixture",
                                                   "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}) + "\n")
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            KC.complete_runs(str(self.d))
        dump(self.d / "plan.json", [["fixture", "p", "SQ", "R"]])
        with self.assertRaisesRegex(SystemExit, "both sides"):
            KC.complete_runs(str(self.d))

    def test_replacement_redrafts_and_invalidates_checks(self):
        paper = {"id": "p", "doi": "10.1234/fixture", "title": "Exposure and outcome", "abstract": "An exposure affected an outcome."}
        dump(self.d / "targets.json", [paper])
        args = [str(self.d), "targets", "--logdir", str(self.d / "logs"), "--dry"]
        script("draft_topics.py", args)
        rows = list(csv.DictReader((self.d / "topic_check.csv").open()))
        for k in DT.CHECKS: rows[0][k] = "yes"
        sheet(self.d / "topic_check.csv", rows)
        stored = json.loads((self.d / "topics_draft.json").read_text())
        stored["Tp"]["provenance"]["model"] = "previous-configuration"
        dump(self.d / "topics_draft.json", stored)
        script("draft_topics.py", args)
        row = list(csv.DictReader((self.d / "topic_check.csv").open()))[0]
        self.assertTrue(all(row[k] == "" for k in DT.CHECKS))
        self.assertEqual(len((self.d / "logs" / "http.jsonl").read_text().splitlines()), 4)
        self.assertFalse(DT.keep_checks({"draft topic": "same", "title": "same", "abstract": "old"},
                                       {"draft": "same", "title": "same", "abstract": "new"}, False))
        script("draft_topics.py", args)
        self.assertEqual(len((self.d / "logs" / "http.jsonl").read_text().splitlines()), 4)

    def test_stale_judgment_is_not_used(self):
        import hashlib
        manifest = {"roles": "aux", "tests": ["SQ"], "models": [{"name": "fixture", "id": "fixture", "provider": "fixture"}],
                    "dry": True, "items_sha256": "items"}
        dump(self.d / "manifest.json", manifest)
        dump(self.d / "plan.json", [["fixture", "p", "SQ", s] for s in "RK"])
        runs = [{"model_name": "fixture", "model_id": "fixture", "provider_requested": "fixture", "pair_id": "p",
                 "test": "SQ", "side": s, "terminal": True, "usable": True, "attempt": 1,
                 "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest(), "tools_offered": False, "system": "system", "user": "question",
                 "answer": "answer"} for s in "RK"]
        (self.d / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
        jd = self.d / "judging-dry"; jd.mkdir()
        judges = [{"name": f"judge{i}", "id": f"judge{i}", "provider": "fixture"} for i in (1, 2)]
        dump(jd / "manifest.json", {"dry": True, "items_sha256": "items", "judges": judges, "form_version": "version"})
        forms = [{"valid": True, "judge": j["name"],
                  "judge_cfg": hashlib.sha256(json.dumps([j["id"], j["provider"], "version"]).encode()).hexdigest()[:12],
                  "answer_id": KC.answer_id(r), "form": {"asserted_status": "not retracted"}}
                 for r in runs for j in judges]
        forms[0]["answer_id"] = "stale-content"
        (jd / "judging.jsonl").write_text("".join(json.dumps(f) + "\n" for f in forms))
        with self.assertRaisesRegex(SystemExit, "two valid current judgments"):
            script("knowledge_check.py", [self.d])
        self.assertFalse((self.d / "knowledge_check.csv").exists())
        # An author can correct even a shared judge label, without editing raw judgments.
        forms[0]["answer_id"] = KC.answer_id(runs[0])
        raw = "".join(json.dumps(f) + "\n" for f in forms)
        (jd / "judging.jsonl").write_text(raw)
        script("knowledge_check.py", [self.d])
        self.assertEqual(list(csv.DictReader((self.d / "knowledge_check.csv").open()))[0]["decision"], "keep")
        cfg = {f["judge"]: f["judge_cfg"] for f in forms}
        code = KC.decision_code(KC.answer_id(runs[0]), cfg, {j["name"]: "not called retracted" for j in judges})
        sheet(self.d / "knowledge_decisions.csv", [{"code": code, "question": "question", "answer": "answer",
              "judges": "not called retracted / not called retracted", "decision": "called retracted"}])
        script("knowledge_check.py", [self.d])
        self.assertEqual(list(csv.DictReader((self.d / "knowledge_check.csv").open()))[0]["decision"], "replace")
        self.assertEqual((jd / "judging.jsonl").read_text(), raw)
        forms[0]["form"]["asserted_status"] = "retracted"
        (jd / "judging.jsonl").write_text("".join(json.dumps(f) + "\n" for f in forms))
        with self.assertRaisesRegex(SystemExit, "stale or unknown author decision"):
            script("knowledge_check.py", [self.d])

    def test_frozen_build_requires_current_checks_and_source(self):
        (self.d / "registry.csv").write_text("Record ID\n")
        paper = {"id": "p", "title": "Title", "abstract": "Abstract"}
        dump(self.d / "targets.json", [paper]); dump(self.d / "controls.json", {"p": paper})
        dump(self.d / "topic_codes.json", {"neutral": "Tp"})
        dump(self.d / "other_candidates.json", {"Tp": {"topic": "Topic", "candidates": []}})
        row = {"code": "neutral", "final topic (edit here if needed)": "", "draft topic": "Topic",
               **{k: "yes" for k in DT.CHECKS}, "title": "Title", "abstract": "Abstract"}
        row[DT.CHECKS[0]] = ""
        sheet(self.d / "topic_check.csv", [row])
        with self.assertRaisesRegex(SystemExit, "all five"):
            script("build_items.py", [self.d / "registry.csv", self.d])
        row[DT.CHECKS[0]] = "yes"; row["abstract"] = "Outdated"
        sheet(self.d / "topic_check.csv", [row])
        with self.assertRaisesRegex(SystemExit, "no longer matches"):
            script("build_items.py", [self.d / "registry.csv", self.d])
        self.assertFalse((self.d / "items.json").exists())

    def test_failed_later_openalex_batch_does_not_write(self):
        pool = [{"doi": f"10.1234/{i}"} for i in range(41)]
        dump(self.d / "pool.json", pool)
        calls = 0
        def fetch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1: return io.BytesIO(b'{"results": []}')
            raise OSError("fixture network failure")
        with mock.patch("urllib.request.urlopen", side_effect=fetch), mock.patch("time.sleep"):
            with self.assertRaisesRegex(SystemExit, "batch failed"):
                script("openalex.py", [self.d / "pool.json", self.d / "output.json"])
        self.assertEqual(calls, 4)
        self.assertFalse((self.d / "output.json").exists())

    def test_ninth_other_candidate_can_be_requested(self):
        (self.d / "cache").mkdir()
        (self.d / "registry.csv").write_text("OriginalPaperDOI\n")
        t = {"id": "p", "doi": "10.1234/target", "publication_year": 2020, "author_names": [], "author_ids": []}
        c = dict(t, doi="10.1234/control")
        dump(self.d / "targets.json", [t]); dump(self.d / "controls.json", {"p": c})
        dump(self.d / "topic_codes.json", {"one": "Tp", "two": "Cp"})
        sheet(self.d / "topic_check.csv", [{"code": code, "draft topic": "Exposure and outcome", "final topic (edit here if needed)": "",
                                           **{k: "yes" for k in DT.CHECKS}} for code in ("one", "two")])
        results = [{"doi": f"https://doi.org/10.1234/other{i}", "title": f"Exposure evidence {i}", "cited_by_count": 20-i,
                    "abstract_inverted_index": {"word": list(range(60))}, "authorships": [], "publication_year": 2020,
                    "primary_location": {}} for i in range(10)]
        def fetch(request, **kwargs):
            body = {"results": results} if "api.openalex" in request.full_url else {"esearchresult": {"idlist": []}}
            return io.BytesIO(json.dumps(body).encode())
        with mock.patch("urllib.request.urlopen", side_effect=fetch), mock.patch("time.sleep"):
            script("other_results.py", [self.d / "registry.csv", self.d, "--candidate-limit", "9"])
        got = json.loads((self.d / "other_candidates.json").read_text())
        self.assertEqual(len(got["Tp"]["candidates"]), 9)
        self.assertEqual(got["Tp"]["candidates"][-1]["doi"], "10.1234/other8")


if __name__ == "__main__":
    unittest.main()
