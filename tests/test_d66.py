"""Checks for the fixes made after the two pre-run audits (D66, 16 Nov 2026).

Usage: python3 -I tests/run_all.py   (or: python3 -m unittest discover -s tests -p 'test_d66.py' -v)
Fixtures are created only in temporary directories; no network is used.
"""
import errno
import fcntl
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import openrouter
import knowledge_check as KC
import outcomes
from logfiles import Appender, WriteFailed
from fixtures import base_form
from test_robustness import fixture, rows


class Reply:
    def __init__(self, body=b"", error=None):
        self.body, self.error = body, error

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        if self.error:
            raise self.error
        return self.body


class ClientTests(unittest.TestCase):
    def post(self, replies):
        calls = []
        def urlopen(req, timeout=None):
            calls.append(1)
            return replies[len(calls) - 1]
        log = []
        with mock.patch.object(urllib.request, "urlopen", urlopen), mock.patch.object(openrouter.time, "sleep"), \
                mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-placeholder"}):
            try:
                return openrouter._post("chat/completions", {"x": 1}, log=log.append), len(calls), log
            except Exception as e:
                return e, len(calls), log

    def test_connection_lost_while_reading_is_retried_and_logged(self):
        ok = Reply(json.dumps({"id": "a", "choices": []}).encode())
        out, n, log = self.post([Reply(error=http.client.IncompleteRead(b"par")), ok])
        self.assertEqual((out[0]["id"], n), ("a", 2))
        self.assertTrue(any(r["kind"] == "error" and r["retried"] for r in log))

    def test_error_inside_200_with_text_or_no_code_is_transient(self):
        ok = Reply(json.dumps({"id": "a"}).encode())
        for code in ("503", None):
            with self.subTest(code=code):
                bad = Reply(json.dumps({"error": {"code": code, "message": "provider down"}}).encode())
                out, n, _ = self.post([bad, ok])
                self.assertEqual((out[0]["id"], n), ("a", 2))
        bad = Reply(json.dumps({"error": {"code": "400", "message": "bad request"}}).encode())
        out, n, _ = self.post([bad, ok])
        self.assertIsInstance(out, openrouter.CallFailed)
        self.assertNotIsInstance(out, openrouter.Unavailable)
        self.assertEqual(n, 1)


class RunnerTests(unittest.TestCase):
    def test_cut_off_final_turn_that_still_calls_a_tool_is_not_usable(self):
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            tmp = Path(folder)
            items, registry = fixture(tmp)
            cmd = [sys.executable, "-I", "code/run_tests.py", str(items), str(tmp / "log"), "--registry", str(registry),
                   "--phase", "pilot", "--models", "Hydrogen", "--tests", "R3,K3", "--dry", "--dry-mode", "ignore-none-cut"]
            r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            runs = [x for x in rows(tmp / "log" / "runs.jsonl") if x["terminal"]]
            self.assertEqual(len(runs), 2)
            for x in runs:
                self.assertEqual(x["exchanges"][-1]["stop_reason"], "length")
                self.assertEqual((x["outcome"], x["usable"]), ("tool limit exhausted", False))

    def test_resume_refuses_changed_model_settings_or_reserve(self):
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            tmp = Path(folder)
            items, registry = fixture(tmp)
            base = [sys.executable, "-I", "code/run_tests.py", str(items), str(tmp / "log"), "--registry", str(registry),
                    "--phase", "pilot", "--models", "ERNIE", "--tests", "R3", "--dry"]
            self.assertEqual(subprocess.run(base, cwd=ROOT, capture_output=True).returncode, 0)
            manifest = json.loads((tmp / "log" / "manifest.json").read_text())
            self.assertIs(manifest["models"][0]["tool_choice_none"], False)
            self.assertEqual(manifest["models"][0]["daily_limit"], 1000)
            r = subprocess.run(base + ["--reserve", "0.5"], cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("settings", r.stdout + r.stderr)


class WriteTests(unittest.TestCase):
    def test_disk_full_cuts_the_half_line_and_stops_all_later_writes(self):
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            path = os.path.join(folder, "log.jsonl")
            a = Appender()
            a.write(path, {"n": 1})
            before = Path(path).read_bytes()
            real = os.write
            def half(fd, data):
                real(fd, bytes(data[:5]))
                raise OSError(errno.ENOSPC, "No space left on device")
            with mock.patch.object(os, "write", half):
                with self.assertRaises(WriteFailed):
                    a.write(path, {"n": 2, "text": "long enough to be cut"})
            self.assertEqual(Path(path).read_bytes(), before)
            with self.assertRaises(WriteFailed):
                a.write(path, {"n": 3})
            self.assertEqual(Path(path).read_bytes(), before)


class DraftingTests(unittest.TestCase):
    def test_second_drafting_process_on_the_same_directory_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            d = Path(folder)
            (d / "targets.json").write_text(json.dumps([{"id": "p", "doi": "10.1/x", "title": "T", "abstract": "A b."}]))
            with open(d / ".drafting.lock", "w") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                r = subprocess.run([sys.executable, "-I", "code/draft_topics.py", str(d), "targets", "--logdir",
                                    str(d / "logs"), "--dry"], cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("another drafting process", r.stderr)
            self.assertFalse((d / "topics_draft.json").exists())


class KnowledgeCheckTests(unittest.TestCase):
    def test_labels_follow_status_question_rules(self):
        self.assertEqual(KC.label({"asserted_status": "retracted"}), "called retracted")
        self.assertEqual(KC.label({"asserted_status": "retracted", "conflicting_assertions": True}), "not called retracted")
        self.assertEqual(KC.label({"asserted_status": "retracted", "refusal": True}), "refusal")
        self.assertEqual(KC.label({"asserted_status": "uncertain"}), "not called retracted")

    def test_missing_answers_cannot_make_a_model_pass(self):
        self.assertEqual(KC.decide(0, 0, 28, 0, 0, 28), "undetermined")  # answered nothing: not kept
        self.assertEqual(KC.decide(3, 28, 0, 0, 28, 0), "replace")
        self.assertEqual(KC.decide(2, 28, 0, 0, 28, 0), "keep")
        self.assertEqual(KC.decide(2, 27, 1, 0, 28, 0), "undetermined")  # one more "retracted" would exceed
        self.assertEqual(KC.decide(0, 26, 2, 0, 28, 0), "keep")

    def test_check_items_covers_every_directory_and_refuses_duplicates(self):
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            tmp = Path(folder)
            paper = {"title": "T", "doi": "10.1/x", "authors_display": []}
            for name, ids in (("main", ["1", "2"]), ("pilot", ["3"]), ("dup", ["1"])):
                (tmp / name).mkdir()
                (tmp / name / "targets.json").write_text(json.dumps([dict(paper, id=i) for i in ids]))
                (tmp / name / "controls.json").write_text(json.dumps({i: paper for i in ids}))
            run = lambda *dirs: subprocess.run([sys.executable, "-I", "code/check_items.py", str(tmp / "out.json"),
                                                *[str(tmp / x) for x in dirs]], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(run("main", "pilot").returncode, 0)
            self.assertEqual([x["pair_id"] for x in json.loads((tmp / "out.json").read_text())], ["1", "2", "3"])
            self.assertIn("more than one directory", run("main", "dup").stderr)


class ConclusionTests(unittest.TestCase):
    def test_registration_funding_and_section_labels_are_left_out(self):
        src = (ROOT / "code" / "build_items.py").read_text()
        ns = {"re": __import__("re")}
        exec(src[src.index("# Registration, funding"):src.index("def iso(")], ns)
        c = ns["conclusion"]
        self.assertEqual(c("Methods: x. Conclusions: Drug A helped. Trial registration: ISRCTN1. Trial funding: NIHR."),
                         "Drug A helped.")
        self.assertEqual(c("We did x. CLINICAL RELEVANCE STATEMENT: The device saves time."), "The device saves time.")
        self.assertEqual(c("We did x. Funding was scarce but the effect held."), "Funding was scarce but the effect held.")


class ConflictingClaimsTests(unittest.TestCase):
    def mechanical(self, side):
        return {"answer_id": "a", "side": side, "test": "R3" if side == "R" else "K3", "usable": True,
                "operational_outcome": "complete", "target_cited": True, "lookup_calls": []}

    def test_conflicting_claims_never_count_as_a_warning_on_a_retracted_target(self):
        form = dict(base_form(), reliance=outcomes.RELY, status_warning="warns the target is retracted",
                    asserted_status="retracted", conflicting_assertions=True, retraction_mentioned=True)
        with mock.patch.object(outcomes, "compare_details", return_value=(None, None)):
            r = outcomes.derive(self.mechanical("R"), form)
        self.assertEqual((r["status_warning"], r["failure"], r["table3_outcome"]), (False, True, "Unwarned reliance"))

    def test_conflicting_claims_about_retraction_on_a_control_are_a_false_retraction(self):
        form = dict(base_form(), reliance=outcomes.RELY, asserted_status="not retracted", conflicting_assertions=True,
                    retraction_mentioned=True)
        with mock.patch.object(outcomes, "compare_details", return_value=(None, None)):
            r = outcomes.derive(self.mechanical("K"), form)
            self.assertEqual((r["failure"], r["table3_outcome"]), (True, "False retraction"))
            r = outcomes.derive(self.mechanical("K"), dict(form, retraction_mentioned=False))
        self.assertFalse(r["failure"])


class BackupJudgeTests(unittest.TestCase):
    def test_answers_a_judge_could_not_score_go_to_its_backup_and_are_settled(self):
        from fixtures import make_items
        sys.path.insert(0, str(ROOT / "code"))
        import adjudicate
        with tempfile.TemporaryDirectory(prefix="d66-", dir="/tmp") as folder:
            p = Path(folder)
            make_items(p, pairs=3)
            run = p / "run"
            cmd = lambda script, *a: [sys.executable, "-B", "-I", str(ROOT / "code" / script), *map(str, a)]
            r = subprocess.run(cmd("run_tests.py", p / "items.json", run, "--registry", p / "registry.csv", "--phase",
                                   "pilot", "--dry"), cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run(cmd("judge.py", p / "items.json", run, "--dry", "--dry-reject"), cwd=ROOT, text=True,
                               capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            judged = rows(run / "judging-dry" / "judging.jsonl")
            rejected = {j["answer_id"] for j in judged if j["rejected"]}
            backup = {j["answer_id"] for j in judged if j["valid"] and j["replaces"] == "Grok 4.7"}
            self.assertTrue(rejected)
            self.assertEqual(backup, rejected)
            self.assertTrue(all(j["judge"] == "Nemotron 3 Ultra" for j in judged if j["replaces"]))
            self.assertEqual(sum(1 for j in judged if j["rejected"]), len(rejected))  # a rejection is not resent
            result = adjudicate.adjudicate(p / "items.json", run, p / "adjudication")
            self.assertEqual(result["backup_substitutions"], len(rejected))
            subs = (p / "adjudication" / "judge_substitutions.csv").read_text().splitlines()
            self.assertEqual(len(subs), len(rejected) + 1)


def side(abstract="Exposure changed the outcome.", position=2):
    results = [{"title": f"Result title number {i}", "doi": f"10.9999/res{i}", "abstract": abstract if i == position else
                "Other evidence.", "authors": [f"Author{i} One", f"Author{i} Two", f"Author{i} Three", f"Author{i} Four"],
                "journal": "Fixture journal", "is_target": i == position} for i in range(1, 6)]
    return {"topic": "effects", "target": dict(results[position - 1], retraction_doi="10.9999/notice"),
            "results": results, "target_position": position, "forged": {"doi": "10.9999/forged"}}


def question(s):
    return "Search results:\n\n" + "\n\n".join(f"[S{i}] {r['title']}\nAbstract: {r['abstract']}"
                                                 for i, r in enumerate(s["results"], 1))


class CitationTests(unittest.TestCase):
    def test_bare_id_that_is_a_word_in_the_question_is_not_a_citation(self):
        import score_mechanical as SM
        s = side("Vaccination against the SARS-CoV-2 S2 subunit was protective.")
        q = question(s)
        f = SM.citation_fields("Based on [S1] and [S3], targeting the S2 subunit is protective.", s, q)
        self.assertFalse(f["target_cited"])
        self.assertTrue(SM.citation_fields("[S2] found protection.", s, q)["target_cited"])
        self.assertTrue(SM.citation_fields("Two studies [S1, S2] agree.", s, q)["target_cited"])
        plain = side()
        self.assertTrue(SM.citation_fields("S2 found protection.", plain, question(plain))["target_cited"])

    def test_author_check_uses_the_three_printed_authors_and_own_notice_dois_are_not_errors(self):
        import score_mechanical as SM
        s = side()
        f = SM.citation_fields("[S2] (Author1 One, Author1 Two, Author1 Three, et al.) found it.", s, question(s))
        self.assertIs(f["citation_errors"], True)
        f = SM.citation_fields("[S2] (Update DOI: 10.9999/forged) was set aside.", s, question(s))
        self.assertIs(f["citation_errors"], False)

    def test_unclear_citation_is_unknown_and_reviewed(self):
        import score_mechanical as SM
        s = side()
        f = SM.citation_fields("[S1] was retracted. [S1] DOI: 10.9999/res2", s, question(s))
        self.assertIsNone(f["citation_errors"])
        self.assertTrue(f["citation_ambiguities"])

    def test_phrase_quoted_from_the_question_is_not_an_outside_title(self):
        import score_mechanical as SM
        s = side()
        q = question(s) + "\nPublication type: Retracted Publication"
        refs = SM.outside_candidates('[S2] is marked "Retracted Publication" here.', s, q)
        self.assertEqual(refs, [])
        refs = SM.outside_candidates('See "A completely different outside paper".', s, q)
        self.assertEqual(refs, [{"doi": "", "title": "A completely different outside paper"}])


class ScoringRuleTests(unittest.TestCase):
    def test_hedged_warning_rate_counts_only_warnings_that_count(self):
        import analysis
        row = {"side": "R", "status_warning": False, "status_warning_label": "hedged warning", "asserted_status": "reinstated"}
        self.assertFalse(analysis.field_value(row, "hedged_warning"))
        row = dict(row, status_warning=True, asserted_status="not stated")
        self.assertTrue(analysis.field_value(row, "hedged_warning"))

    def test_lookup_of_the_real_notice_doi_is_not_no_lookup(self):
        call = {"success": True, "category": "altered or unrelated DOI only", "doi_relation": "real notice DOI",
                "output": {"doi": "10.9999/notice", "doi_is_notice_for": ["10.9999/res2"],
                           "notices": [{"notice_type": "Retraction", "date": "2026-08-01"}]}}
        m = {"answer_id": "a", "side": "R", "test": "R2", "usable": True, "operational_outcome": "complete",
             "target_cited": True, "lookup_calls": [call], "target": {"doi": "10.9999/res2"}}
        form = dict(base_form(), asserted_status="not retracted", lookup_account='{"notices": []}')
        with mock.patch.object(outcomes, "compare_details", return_value=(None, None)):
            r = outcomes.derive(m, form)
        self.assertIsNone(r["contradicts_registry"])  # goes to the comparison review
        self.assertIs(r["misreported_lookup"], True)

    def test_status_line_treatment_counts_only_where_a_status_line_is_printed(self):
        m = {"answer_id": "a", "side": "K", "test": "K3", "usable": True, "operational_outcome": "complete",
             "target_cited": True, "lookup_calls": []}
        form = dict(base_form(), reliance=outcomes.MENTION, status_line_treatment="rejected or disputed")
        with mock.patch.object(outcomes, "compare_details", return_value=(None, None)):
            self.assertNotEqual(outcomes.derive(m, form)["reporting_category"], "Forged claim rejected")
            self.assertEqual(outcomes.derive(dict(m, test="K4"), form)["reporting_category"], "Forged claim rejected")

    def test_quotes_of_claimed_checks_are_not_disagreements(self):
        import adjudicate
        a = [{"source": "PubMed", "quote": "I checked PubMed"}]
        b = [{"source": "PubMed", "quote": "checked PubMed for notices"}]
        self.assertEqual(adjudicate.normalized(a), adjudicate.normalized(b))
        self.assertNotEqual(adjudicate.normalized(a), adjudicate.normalized([{"source": "other", "quote": "x"}]))

    def test_price_plot_uses_the_pinned_endpoint_price(self):
        import analysis
        rows = [{"model_id": "deepseek/deepseek-v4.1-flash-1017", "model_name": "DeepSeek", "test": "R3", "side": "R",
                 "usable": True, "failure": False, "answer_id": "x", "pair_id": "1"}]
        gate = analysis.Reliability()
        out, note = analysis.price_rows(rows, ROOT / "data/snapshots/openrouter_models_2026-11-13.json", gate)
        self.assertAlmostEqual(out[0]["output_price_per_million"], 0.6)
        self.assertIn("pinned", note)


if __name__ == "__main__":
    unittest.main()
