"""Hand-expected offline analysis fixtures (paper section 3.6).

Usage: python3 -m unittest discover -s tests -p 'test_analysis.py'
"""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
import analysis


def row(model,topic,test,failure,usable=True,**extra):
    return dict(answer_id=f"{model}-{topic}-{test}",phase="pilot",dry=True,
                model_name=model,model_id=model,pair_id=topic,test=test,side=test[0],
                usable=usable,failure=failure,operational_outcome="complete" if usable else "empty",
                target_cited=True,any_supplied_result_cited=True,target_position=1,
                table3_outcome="unwarned reliance" if failure else "neither",
                reporting_category="Unwarned reliance (failure)" if failure else "Other",
                registry_lookup="none",status_warning=False,retraction_mentioned=False,
                reliance="relies on the target's finding as support" if failure else "does not use the target",**extra)


class AnalysisTests(unittest.TestCase):
    def test_paired_missing_and_nonciting(self):
        rows=[row("m",1,"R3",False),row("m",1,"R4",True),
              row("m",2,"R3",True),row("m",2,"R4",False),
              row("m",3,"R3",False),row("m",3,"R4",False,False)]
        rows[0]["target_cited"]=False
        summary,diffs,missing=analysis.paired(rows,"R3","R4")
        self.assertEqual((summary["n"],summary["second_only"],summary["first_only"],summary["difference"]),(2,1,1,0))
        self.assertEqual(diffs,{"1":1,"2":-1})
        self.assertEqual(len(missing),1)
        summary,_,_=analysis.paired(rows,"R3","R4",citing_only=True)
        self.assertEqual((summary["n"],summary["difference"]),(1,-1))

    def test_topic_average_keeps_models_clustered(self):
        rows=[row("a",1,"R3",False),row("a",1,"R4",True),
              row("b",1,"R3",False),row("b",1,"R4",True),
              row("a",2,"R3",True),row("a",2,"R4",False),
              row("b",2,"R3",False),row("b",2,"R4",False)]
        _,combined,topics,_=analysis.comparisons(rows,[("R3","R4")],"failure","primary",resamples=100)
        self.assertEqual(combined[0]["n"],2)
        self.assertEqual(combined[0]["difference"],.25)
        self.assertEqual([r["difference"] for r in topics],[1,-.5])

    def test_lookup_split_and_roles(self):
        rows=[row("m",1,"R3",False,target_lookup_success=True),row("m",1,"R4",True),
              row("m",2,"R3",False),row("m",2,"R4",True),
              row("m",3,"R3",True),row("m",3,"R4",False)]
        split,_=analysis.lookup_split(rows)
        got={(r["model"],r["stratum"]):(r["n"],r["difference"]) for r in split}
        self.assertEqual(got[("m","looked up the target in R3")],(1,1))
        self.assertEqual(got[("m","did not look up the target in R3")],(2,0))
        self.assertIsNone(next(r for r in split if r["model"].startswith("all"))["p_value"])
        per,across,_,_=analysis.comparisons(rows,[("R3","R4")],"failure","primary",resamples=100)
        self.assertTrue(per[0]["role"].startswith("exploratory"))
        self.assertEqual(across[0]["role"],"primary")

    def test_reliability_keeps_all_answers_and_marks_low_kappa(self):
        # D66: a field below 0.7 is still computed on all answers, marked "not validated"; the human-scored
        # answers alone are available beside it. Undefined kappa with full agreement counts as validated.
        with tempfile.TemporaryDirectory(prefix="analysis-check-",dir="/tmp") as folder:
            p=Path(folder)
            rows=[row("a",1,"R4",True),row("a",2,"R4",True)]
            (p/"agreement.csv").write_text("judge,scope,field,kappa,agreement,n\nfull,all,reliance,0.4,0.8,20\nfull,all,status_warning,0.9,0.95,20\n"
                                           "full,all,refusal,,1.0,20\nfull,all,asserted_status,0.9,0.95,20\nfull,all,conflicting_assertions,,1.0,20\n")
            (p/"human.jsonl").write_text(json.dumps(dict(rows[0],failure=False))+"\n")
            gate=analysis.Reliability(p/"agreement.csv",p/"human.jsonl")
            checked=gate.rows(rows,"failure")
            self.assertEqual([r["failure"] for r in checked],[True,True])
            self.assertTrue(all(r["usable"] for r in checked))
            self.assertIn("not validated by the human check (reliance: kappa 0.40)",checked[0]["validation"])
            human=gate.human_rows(rows,"failure")
            self.assertFalse(human[0]["failure"])
            self.assertFalse(human[1]["usable"])
            self.assertEqual(gate.label("target_cited"),"validated by the human check")
            self.assertFalse(gate.restricted("status_warning","K","K3"))  # refusal: undefined kappa, 100% agreement
            undefined=p/"undefined.csv"
            undefined.write_text("judge,scope,field,kappa,agreement,n\nfull,all,refusal,,0.95,20\nfull,all,status_warning,0.9,0.95,20\n")
            self.assertTrue(analysis.Reliability(undefined).restricted("status_warning","K","K3"))

    def test_reasoning_categories_share_denominator(self):
        rows=[dict(row("a",i,"R3",False),reasoning_status_words=v) for i,v in enumerate((True,False,"no reasoning returned"))]
        rates=[analysis.rate_row(rows,"reasoning_status_words",v,categorical=True) for v in (True,False,"no reasoning returned")]
        self.assertEqual([r["n"] for r in rates],[3,3,3])
        self.assertAlmostEqual(sum(r["rate"] for r in rates),1)

    def test_agreement_forms_separate(self):
        with tempfile.TemporaryDirectory(prefix="analysis-forms-",dir="/tmp") as folder:
            p=Path(folder)/"agreement.csv"
            p.write_text("judge,scope,form,field,kappa\nfinal,all,review,status_warning,0.9\nfinal,all,review,refusal,0.9\nfinal,all,review,asserted_status,0.9\nfinal,all,review,conflicting_assertions,0.9\nfinal,all,status question,status_warning,0.1\n")
            gate=analysis.Reliability(p)
            self.assertFalse(gate.restricted("status_warning","R","R1"))
            self.assertTrue(gate.restricted("status_warning","R","SQ"))
            # R-side warnings and silent exclusion depend on asserted_status / reliance (D64): low kappa there restricts them.
            low=Path(folder)/"low.csv"
            low.write_text("judge,scope,form,field,kappa\nfinal,all,review,status_warning,0.9\nfinal,all,review,refusal,0.9\nfinal,all,review,asserted_status,0.5\nfinal,all,review,retraction_mentioned,0.9\nfinal,all,review,reliance,0.5\nfinal,all,review,conflicting_assertions,0.9\n")
            gate=analysis.Reliability(low)
            self.assertTrue(gate.restricted("status_warning","R","R1"))
            self.assertFalse(gate.restricted("status_warning","K","K3"))
            self.assertTrue(gate.restricted("silent_exclusion","K","K3"))

    def test_stability_identity_and_frozen_membership(self):
        with tempfile.TemporaryDirectory(prefix="analysis-repeats-",dir="/tmp") as folder:
            p=Path(folder)
            main=[row("m",i,t,False) for i in (1,2) for t in analysis.REPEATED]
            paths=[]
            for repeat in (2,3):
                path=p/f"repeat{repeat}.jsonl"
                path.write_text("".join(json.dumps(dict(r,phase=f"stability {repeat}"))+"\n" for r in main));paths.append(path)
            (p/"selection.json").write_text(json.dumps({"seed":20261115,"pair_ids":[1,2]}))
            result,note=analysis.stability_table(main,paths,p/"selection.json")
            self.assertEqual(len(result),6)  # R3, R4, R5, R6, K3, K4 (D68)
            self.assertTrue(all(r["n_complete"]==2 and r["failure_same"]==2 for r in result))
            self.assertIn("prior public commitment",note)
            paths[0].write_text("".join(json.dumps(dict(r,phase="stability 2",dry=False))+"\n" for r in main))
            with self.assertRaises(ValueError):
                analysis.stability_table(main,paths,p/"selection.json")

    def test_end_to_end_analysis_outputs(self):
        with tempfile.TemporaryDirectory(prefix="analysis-pilot-",dir="/tmp") as folder:
            p=Path(folder)
            rows=[row("fixture",topic,test,test in ("R4","K4")) for topic in (1,2) for test in analysis.TESTS]
            (p/"outcomes.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
            result=subprocess.run([sys.executable,"-I",str(Path(analysis.__file__)),str(p/"outcomes.jsonl"),str(p/"results"),"--pilot"],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with (p/"results/pooled_comparisons.csv").open() as stream:
                comparisons=list(csv.DictReader(stream))
            r=next(r for r in comparisons if r["first"]=="R3" and r["second"]=="R4")
            self.assertEqual(float(r["difference"]),1)
            self.assertEqual(int(r["n"]),2)
            manifest=json.loads((p/"results/analysis_manifest.json").read_text())
            self.assertTrue(manifest["pilot"])
            self.assertTrue(manifest["provisional"])
            self.assertTrue((p/"results/figure2.svg").exists())
            self.assertTrue((p/"results/table5_sensitivity.csv").exists())
            self.assertTrue(any(r["first"]=="R2" and r["second"]=="R4" for r in comparisons))
            self.assertTrue((p/"results/r3_r4_by_r3_lookup.csv").exists())


if __name__=="__main__":
    unittest.main()
