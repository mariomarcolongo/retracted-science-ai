"""Offline tests for blind adjudication and human checking (paper section 3.5).

Usage: python3 -m unittest discover -s tests -p test_adjudication.py -v
All fixture items, logs and sheets are created under /tmp; model runners use --dry.
"""
import copy, csv, json, pathlib, subprocess, sys, tempfile, unittest
from unittest import mock
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import adjudicate as A
import human_check as H
from scoring_common import answer_id, read_jsonl, schemas, terminal_runs, write_csv, write_jsonl


def filled(schema):
    if schema["type"] == "object": return {k: filled(v) for k, v in schema["properties"].items()}
    if schema.get("enum"): return schema["enum"][-1]
    return {"string": "", "boolean": False, "array": []}[schema["type"]]


def make_run(folder):
    items = []
    for n in range(2):
        item = {"pair_id": f"pair{n}"}
        for side in ("R", "K"):
            target = {"title": f"Fixture target {n}{1 if side == 'R' else 2}", "authors": [], "journal": "Fixture Journal",
                      "year": 2025, "doi": f"10.9999/target{n}{side.lower()}", "abstract": "The outcome increased.",
                      "conclusion": "The outcome increased.", "retraction_date": "2026-07-01", "retraction_doi": "10.9999/notice"}
            results = [dict(target, is_target=True)] + [dict(target, title=f"Fixture evidence {i}", doi=f"10.9999/evidence{i}",
                                                           is_target=False) for i in range(2, 6)]
            item[side] = {"target": target, "results": results, "target_position": 1, "topic": "health outcomes",
                          "forged": {"date": "2026-10-01", "doi": "10.9999/forged"}}
        items.append(item)
    ip = folder / "items.json"; ip.write_text(json.dumps(items))
    registry = folder / "registry.csv"; registry.write_text("OriginalPaperDOI,Record ID,RetractionDate,RetractionNature,Reason,RetractionDOI\n")
    rundir = folder / "run"
    for args in (["code/run_tests.py", str(ip), str(rundir), "--registry", str(registry), "--phase", "pilot", "--models", "Hydrogen", "--dry"],
                 ["code/judge.py", str(ip), str(rundir), "--dry"]):
        result = subprocess.run([sys.executable, "-I"] + args, cwd=ROOT, capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stdout + result.stderr)
    return ip, rundir


class AdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="adjudication-test-", dir="/tmp")
        self.path = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_decision_values_and_evidence(self):
        schema = schemas()[0]
        self.assertTrue(A.parse_decision("yes", schema["properties"]["refusal"], [False, True]))
        self.assertFalse(A.parse_decision("judge 1", schema["properties"]["refusal"], [False, True]))
        with self.assertRaises(ValueError):
            A.parse_decision("unknown value", schema["properties"]["asserted_status"], ["uncertain", "retracted"])
        self.assertEqual(A.normalized([{"paper": "b"}, {"paper": "a"}]), A.normalized([{"paper": "a"}, {"paper": "b"}]))
        self.assertNotIn("evidence_quotes", A.meaning_fields(schema))

    def test_full_dry_labelling_disagreement_and_import(self):
        items, rundir = make_run(self.path)
        human = self.path / "human"
        sample = H.prepare(items, rundir, human, pilot=True)
        self.assertEqual(sample, {"sampled": 24, "shortfall": 0})  # two per test (ten tests) and four status answers
        mapping = json.loads((human / "sample-map.json").read_text())["mapping"]
        rows = list(csv.DictReader((human / "labels.csv").open()))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            H.load_labels(human / "labels.csv")
        out = self.path / "adjudicated"
        with self.assertRaisesRegex(ValueError, "incomplete"):
            A.adjudicate(items, rundir, out, human_labels=human / "labels.csv")
        self.assertFalse((out / "decisions.csv").exists())
        test, sq = schemas()
        for row in rows:
            row["form_json"] = json.dumps(filled(sq if mapping[row["code"]]["status_question"] else test))
            row["seconds"] = "12.5"
        write_csv(human / "labels.csv", rows, H.COLUMNS)
        H.prepare(items, rundir, human, pilot=True)  # completed labels are preserved
        self.assertEqual(H.load_labels(human / "labels.csv")[0]["seconds"], 12.5)
        empty_map = self.path / "empty-map.json"; empty_map.write_text(json.dumps({"mapping": {}}))
        write_csv(self.path / "empty-labels.csv", [], H.COLUMNS)
        with self.assertRaisesRegex(ValueError, "complete seeded sample"):
            A.adjudicate(items, rundir, out, human_labels=self.path / "empty-labels.csv", human_map=empty_map)
        jp = rundir / "judging-dry" / "judging.jsonl"
        judgments = read_jsonl(jp)
        changed = judgments[0]["answer_id"]
        judgments[0]["form"]["asserted_status"] = "retracted"
        judgments[0]["form"]["evidence_quotes"] = ["quotation one"]
        write_jsonl(jp, judgments)
        with self.assertRaisesRegex(ValueError, "1 field decisions remain"):
            A.adjudicate(items, rundir, out, human_labels=human / "labels.csv")
        self.assertFalse((out / "settled.jsonl").exists())
        decisions = list(csv.DictReader((out / "decisions.csv").open()))
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["field"], "asserted_status")
        self.assertNotIn("Gemini", json.dumps(decisions))
        self.assertFalse({"test", "model", "true_status", "side"} & set(decisions[0]))
        decisions[0]["decision"] = "judge 1"
        write_csv(out / "decisions.csv", decisions)
        with self.assertRaisesRegex(ValueError, "reason is required"):
            A.adjudicate(items, rundir, out, human_labels=human / "labels.csv")
        decisions[0]["reason"] = "The answer states the selected status."
        write_csv(out / "decisions.csv", decisions)
        self.assertEqual(A.adjudicate(items, rundir, out, human_labels=human / "labels.csv"), {"answers": 24, "disagreements": 1, "backup_substitutions": 0})
        settled = read_jsonl(out / "settled.jsonl")
        self.assertEqual(next(r for r in settled if r["answer_id"] == changed)["disagreement_fields"], ["asserted_status"])
        compared = self.path / "compared"
        self.assertEqual(H.compare(human / "labels.csv", out / "settled.jsonl", compared), 24)
        self.assertEqual(len(read_jsonl(compared / "human_labels.jsonl")), 24)
        agreements = list(csv.DictReader((compared / "human_agreement.csv").open()))
        final = [r for r in agreements if r["field"] == "asserted_status" and r["scope"] == "all" and r["judge"] == "final"]
        self.assertEqual(sorted(int(r["n"]) for r in final), [4, 20])
        self.assertAlmostEqual(sum(float(r["agreement"]) * int(r["n"]) for r in final), 23)
        human_forms = read_jsonl(compared / "human_labels.jsonl")
        outputs = [{"answer_id": r["answer_id"], "answer": "Metadata must not become a field", "provider": "fixture-provider",
                    "failure": False, "status_question_outcome": "uncertain", "operational_outcome": "complete"} for r in human_forms]
        write_jsonl(self.path / "full-outcomes.jsonl", outputs); write_jsonl(self.path / "human-outcomes.jsonl", outputs)
        H.compare(human / "labels.csv", out / "settled.jsonl", compared,
                  outcomes=self.path / "full-outcomes.jsonl", human_outcomes=self.path / "human-outcomes.jsonl")
        derived = [r for r in csv.DictReader((compared / "human_agreement.csv").open()) if r["scope"] == "derived outcomes"]
        self.assertFalse({"answer", "provider"} & {r["field"] for r in derived})
        self.assertEqual({r["form"] for r in derived}, {"review", "status question"})
        self.assertFalse(json.loads((compared / "labels_receipt.json").read_text())["mechanical_fields_independently_validated"])
        # Reordering input rows does not change seeded selection.
        runs = terminal_runs(rundir)
        first = [answer_id(r) for r in H.choose_sample(runs)[0]]
        second = [answer_id(r) for r in H.choose_sample(list(reversed(runs)))[0]]
        self.assertEqual(first, second)
        page = (human / "label.html").read_text()
        self.assertIn("performance.now()", page)
        self.assertNotIn("Gemini", page)
        # Changed context and duplicate codes are rejected instead of silently joined.
        rows[0]["answer"] += " changed"
        write_csv(human / "labels.csv", rows, H.COLUMNS)
        with self.assertRaisesRegex(ValueError, "context changed"):
            H.load_labels(human / "labels.csv")

    def test_short_cells_are_reported(self):
        runs = []
        for i, usable in enumerate([True, False]):
            runs.append({"model_name": "fixture", "model_id": "fixture", "provider_requested": "fixture",
                         "pair_id": str(i), "test": "R3", "side": "R", "usable": usable, "manifest_sha256": "hash",
                         "attempt": 1, "tools_offered": True, "system": "system", "user": "question", "answer": "answer"})
        chosen, counts = H.choose_sample(runs)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(counts[0]["shortfall"], 1)

    def test_live_main_requires_independent_labels_before_reveal(self):
        with mock.patch.object(A, "checked_items", return_value=({}, {"phase": "main", "dry": False, "roles": "tested"})), \
                mock.patch.object(A, "terminal_runs", return_value=[]):
            with self.assertRaisesRegex(ValueError, "requires completed --human-labels"):
                A.adjudicate("items", "run", self.path / "out")
        self.assertFalse((self.path / "out").exists())


if __name__ == "__main__":
    unittest.main()
