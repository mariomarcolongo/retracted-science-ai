"""Break-and-resume checks (D65): hard kills of the runner and the judges, half-written log lines, and a crash
while an output file is being written.

Usage: python3 -I tests/run_all.py   (or: python3 -m unittest discover -s tests -p 'test_breaks.py' -v)
Fixtures and logs are created only in temporary directories; dry mode only, no network.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_items
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import scoring_common
from logfiles import read_log

ROOT = Path(__file__).resolve().parents[1]
PAIRS = 6
HALF = b'{"model_name": "Gemini 4 Hydrogen", "pair_id": "01", "te'


def lines(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()] if Path(path).exists() else []


class BreakTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="breaks-", dir="/tmp")
        self.p = Path(self.dir.name)
        make_items(self.p, pairs=PAIRS)

    def tearDown(self):
        self.dir.cleanup()

    def cmd(self, script, *args):
        return [sys.executable, "-B", "-I", str(ROOT / "code" / script), *map(str, args)]

    def runner(self, logdir):
        return self.cmd("run_tests.py", self.p / "items.json", logdir, "--registry", self.p / "registry.csv",
                        "--phase", "main", "--dry")

    def kill_when(self, command, path, count):
        proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 120
        while time.time() < deadline and proc.poll() is None:
            if len(Path(path).read_bytes().splitlines()) >= count if Path(path).exists() else False:
                break
            time.sleep(0.01)
        self.assertIsNone(proc.poll(), "the step finished before it could be killed; raise PAIRS")
        proc.send_signal(signal.SIGKILL)
        proc.wait()

    def ok(self, command):
        r = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_runner_killed_and_half_line_then_resume_matches_clean_run(self):
        clean, broken = self.p / "clean", self.p / "broken"
        self.ok(self.runner(clean))
        self.kill_when(self.runner(broken), broken / "runs.jsonl", 40)
        for name in ("runs.jsonl", "http.jsonl", "events.jsonl"):
            with open(broken / name, "ab") as f:
                f.write(HALF)  # what a crash in the middle of a write leaves
        self.ok(self.runner(broken))
        repaired = [e for e in lines(broken / "events.jsonl") if e["event"] == "log repaired at start"]
        self.assertEqual(sorted(e["log"] for e in repaired), ["events.jsonl", "http.jsonl", "runs.jsonl"])
        self.assertEqual(len(list(broken.glob("runs.jsonl.partial-*"))), 1)
        key = lambda r: (r["model_name"], r["pair_id"], r["test"], r["side"])
        done = [key(r) for r in lines(broken / "runs.jsonl") if r["terminal"]]
        expected = sorted(key(r) for r in lines(clean / "runs.jsonl") if r["terminal"])
        self.assertEqual(len(done), len(set(done)), "an answer was recorded twice")
        self.assertEqual(sorted(done), expected, "an answer was lost or added")
        self.assertTrue(all(r["usable"] and r["attempt"] == 1 for r in lines(broken / "runs.jsonl") if r["terminal"]))

    def test_judges_killed_and_half_line_then_resume_completes(self):
        run = self.p / "run"
        self.ok(self.runner(run))
        judge = self.cmd("judge.py", self.p / "items.json", run, "--dry")
        jd = run / "judging-dry"
        self.kill_when(judge, jd / "judging.jsonl", 30)
        with open(jd / "judging.jsonl", "ab") as f:
            f.write(b'{"answer_id": "abc", "judge_c')
        self.ok(judge)
        answers = [r for r in lines(run / "runs.jsonl") if r["terminal"] and r["usable"]]
        valid = [(j["answer_id"], j["judge_cfg"]) for j in lines(jd / "judging.jsonl") if j["valid"]]
        self.assertEqual(len(valid), len(set(valid)), "a judgment was recorded twice")
        self.assertEqual(len(set(valid)), 2 * len(answers))
        self.assertTrue(any(e["event"] == "log repaired at start" for e in lines(jd / "events.jsonl")))

    def test_judges_refuse_a_run_log_with_a_half_line(self):
        run = self.p / "run"
        self.ok(self.runner(run))
        with open(run / "runs.jsonl", "ab") as f:
            f.write(HALF)
        r = subprocess.run(self.cmd("judge.py", self.p / "items.json", run, "--dry"), cwd=ROOT, text=True,
                           capture_output=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("resume the test run", r.stdout + r.stderr)

    def test_damaged_line_in_the_middle_is_not_repaired(self):
        path = self.p / "log.jsonl"
        path.write_bytes(b'{"a": 1}\n{"a": \n{"a": 3}\n')
        with self.assertRaises(SystemExit):
            read_log(str(path))
        self.assertEqual(path.read_bytes(), b'{"a": 1}\n{"a": \n{"a": 3}\n')

    def test_crash_while_writing_an_output_keeps_the_old_file(self):
        out = self.p / "out" / "rows.jsonl"
        scoring_common.write_jsonl(out, [{"a": 1}, {"a": 2}])
        before = out.read_bytes()
        with self.assertRaises(ValueError):  # NaN is refused in the middle of writing, like a crash mid-file
            scoring_common.write_jsonl(out, [{"a": 1}, {"a": float("nan")}, {"a": 3}])
        self.assertEqual(out.read_bytes(), before)
        scoring_common.write_csv(out.with_suffix(".csv"), [{"a": 1}])
        self.assertEqual(out.with_suffix(".csv").read_text(), "a\n1\n")


if __name__ == "__main__":
    unittest.main()
