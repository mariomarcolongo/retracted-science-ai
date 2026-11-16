"""Full CLI offline pipeline with hand-written expected tables (paper sections 3.5–4).

Usage: python3 -I tests/run_all.py
Two synthetic pairs, two configurations (one per API), eight tests and both status
questions. Fake answers cite S1. Pair01 target=S1, pair02 target=S2. Fake judges say
no target use, no warning, no status assertion. Therefore all32 review outcomes are
Neither, all8 SQ outcomes uncertain; Table3c is16 Other +16 silent exclusions;
all primary differences0, mid-p1, all actual costs0. No result is empirical evidence.
"""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_items, base_form
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"code"))
from scoring_common import answer_id

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


class OfflinePipelineTests(unittest.TestCase):
    def test_main_and_pilot_to_required_tables(self):
        with tempfile.TemporaryDirectory(prefix="full-pipeline-", dir="/tmp") as temp:
            directory = Path(temp)
            make_items(directory)
            items, registry = directory/"items.json", directory/"registry.csv"
            def run(script, *args):
                command = [sys.executable, "-B", "-I", str(ROOT/"code"/script), *map(str,args)]
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=120,
                                        env={**os.environ, "OPENROUTER_API_KEY":""})
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                return result
            for phase in ("main", "pilot"):
                with self.subTest(phase=phase):
                    root = directory/phase
                    run_dir = root/"run"
                    run("run_tests.py", items,run_dir,"--registry",registry,"--phase",phase,"--dry",
                        "--models","GPT-6 Luna,Gemini 4 Hydrogen")
                    # These scripted answers contain exactly the one supplied citation; hand-expected extraction is empty.
                    references=root/"reference-fixture.csv"
                    run_records=[json.loads(line) for line in (run_dir/"runs.jsonl").read_text().splitlines()]
                    with references.open("w",newline="") as stream:
                        writer=csv.DictWriter(stream,fieldnames=["answer_id","complete","references_json"])
                        writer.writeheader()
                        writer.writerows({"answer_id":answer_id(r),"complete":"yes","references_json":"[]"} for r in run_records)
                    run("score_mechanical.py",items,run_dir,root/"mechanical","--registry",registry,"--offline","--references",references)
                    run("judge.py",items,run_dir,"--dry")
                    run("human_check.py","prepare",items,run_dir,root/"human",*["--pilot"]*(phase=="pilot"))
                    # Synthetic labels written explicitly for this fixture, never real author labels.
                    labels = root/"human/labels.csv"
                    rows = csv_rows(labels)
                    mapping = json.loads((root/"human/sample-map.json").read_text())["mapping"]
                    self.assertEqual(len(rows),48)
                    for row in rows:
                        row["form_json"] = json.dumps(base_form(mapping[row["code"]]["status_question"]))
                        row["seconds"] = "10"
                    with labels.open("w",newline="") as stream:
                        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
                    run("adjudicate.py",items,run_dir,root/"adjudication","--human-labels",labels)
                    settled=root/"adjudication/settled.jsonl"
                    run("outcomes.py",root/"mechanical/mechanical.jsonl",settled,root/"outcomes","--registry",registry,"--require-complete")
                    full=root/"outcomes/outcomes.jsonl"
                    records=[json.loads(line) for line in full.read_text().splitlines()]
                    self.assertEqual(len(records),48)
                    review=[r for r in records if r["test"]!="SQ"]
                    sq=[r for r in records if r["test"]=="SQ"]
                    self.assertEqual(len(review),40);self.assertEqual(len(sq),8)
                    self.assertTrue(all(r["table3_outcome"]=="Neither" and r["failure"] is False for r in review))
                    self.assertEqual(sum(r["reporting_category"]=="Other" for r in review),20)
                    self.assertEqual(sum(r["silent_exclusion"] for r in review),20)
                    self.assertTrue(all(r["status_question_outcome"]=="uncertain" for r in sq))
                    self.assertEqual(sum(r["target_cited"] for r in review),20)
                    run("human_check.py","compare",labels,settled,root/"human-agreement")
                    run("outcomes.py",root/"mechanical/mechanical.jsonl",root/"human-agreement/human_labels.jsonl",
                        root/"human-outcomes","--registry",registry)
                    human_outcomes=root/"human-outcomes/outcomes.jsonl"
                    run("human_check.py","compare",labels,settled,root/"human-agreement","--outcomes",full,"--human-outcomes",human_outcomes)
                    run("costs.py","--logs",run_dir,"--output",root/"costs","--snapshot",ROOT/"data/snapshots/openrouter_models_2026-11-13.json")
                    requests=csv_rows(root/"costs/requests.csv")
                    # 40 initial tested calls +24 tool continuations +80 judge calls.
                    self.assertEqual(len(requests),176)
                    self.assertTrue(all(float(r["cost_usd"])==0 for r in requests))
                    run("analysis.py",full,root/"analysis",*["--pilot"]*(phase=="pilot"),"--costs",root/"costs",
                        "--prices",ROOT/"data/snapshots/openrouter_models_2026-11-13.json",
                        "--judge-agreement",root/"adjudication/judges_agreement.csv",
                        "--human-agreement",root/"human-agreement/human_agreement.csv","--human-outcomes",human_outcomes)
                    paired=csv_rows(root/"analysis/paired_comparisons.csv")
                    primary=[r for r in paired if r["family"]=="primary"]
                    self.assertEqual(len(primary),4)
                    self.assertTrue(all(int(r["n"])==2 and float(r["difference"])==0 and float(r["p_value"])==1 for r in primary))
                    manifest=json.loads((root/"analysis/analysis_manifest.json").read_text())
                    self.assertEqual(manifest["answers"],48)
                    self.assertEqual(manifest["pilot"],phase=="pilot")
                    self.assertTrue(manifest["dry"])
                    for name in ("figure2.svg","table5_sensitivity.csv","table6_costs.csv","status_question.csv",
                                 "table3c_categories.csv","omissions.csv","appendix_h_examples.csv","appendix_i_environment.csv"):
                        self.assertTrue((root/"analysis"/name).exists(),name)
                    self.assertTrue(all(("PILOT" in r["analysis"])==(phase=="pilot") for r in primary))
                    # The dry labels never vary and the person agrees with the scoring on every answer: kappa is
                    # undefined but agreement is 100%, which counts as validated (D66); nothing is marked otherwise.
                    reliability=csv_rows(root/"analysis/reliability.csv")
                    self.assertTrue(all(r["status"]=="validated by the human check" for r in reliability
                                        if r["field"]=="failure"))
                    self.assertTrue(all(r["validation"]=="validated by the human check" for r in primary))
                    self.assertFalse((root/"analysis/paired_comparisons_human_scored.csv").exists())

    def test_all_operationally_missing_answers_still_export(self):
        with tempfile.TemporaryDirectory(prefix="missing-pipeline-",dir="/tmp") as temp:
            p=Path(temp);make_items(p,pairs=1)
            def run(script,*args):
                r=subprocess.run([sys.executable,"-B","-I",str(ROOT/"code"/script),*map(str,args)],
                                 capture_output=True,text=True,timeout=120,cwd=ROOT)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            run("run_tests.py",p/"items.json",p/"run","--registry",p/"registry.csv","--phase","pilot",
                "--dry","--dry-mode","empty","--models","GPT-6 Luna","--tests","R3,SQ")
            run("score_mechanical.py",p/"items.json",p/"run",p/"mechanical","--registry",p/"registry.csv","--offline")
            run("judge.py",p/"items.json",p/"run","--dry")
            run("adjudicate.py",p/"items.json",p/"run",p/"adjudication")
            run("outcomes.py",p/"mechanical/mechanical.jsonl",p/"adjudication/settled.jsonl",p/"outcomes","--registry",p/"registry.csv","--require-complete")
            rows=[json.loads(line) for line in (p/"outcomes/outcomes.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows),3)
            self.assertTrue(all(not r["usable"] and r["failure"] is None and r["silent_exclusion"] is None for r in rows))
            run("analysis.py",p/"outcomes/outcomes.jsonl",p/"analysis","--pilot")
            rates=csv_rows(p/"analysis/paired_comparisons.csv")
            self.assertTrue(all(r["n"]=="0" and not r["difference"] for r in rates))


if __name__ == "__main__":
    unittest.main()
