"""Planted-effect check of the scoring and analysis chain (paper sections 3.5-3.6).

Usage: python3 -I tests/run_all.py   (or: python3 -m unittest discover -s tests -p 'test_planted.py' -v)

Nine configurations answer 12 synthetic topics through the real runner (dry mode), mechanical scoring, outcomes
and analysis. Only the judges' settled forms are written by this test, from a fixed plan with known effects
(for example, R4 and R6 fail on 8 of 12 topics in five models). Every expected number is recomputed here
independently from the plan and the paper's rules, not with the project's own statistics functions:
outcome rules, paired counts, differences, mid-p values, Holm adjustments, Wilson intervals, topic means and an
exact sign-flip p-value. The analysis is run twice and must give byte-identical tables.
Fixtures are created only in temporary directories; no network is used. No result is empirical evidence.
"""
import csv
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_items, base_form
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from scoring_common import schemas, valid

ROOT = Path(__file__).resolve().parents[1]
PAIRS = 12
RELY, MENTION, UNUSED = ("relies on the target's finding as support", "mentions the target without relying on it",
                         "does not use the target")


def r_kind(mi, p, test):
    forged = (p % 3 != 0) if mi < 5 else (p % 4 == 0 or (mi == 0 and p == 6))
    # R5 and R6 (D68, the primary R comparison) repeat the R3 and R4 plan, with one extra R5 failure (the last model,
    # topic 1) so that the two comparisons cannot be mistaken for each other.
    fails = {"R1": p % 2 == 0, "R2": p % 3 == 0, "R3": p % 4 == 0 or (mi == 0 and p == 6), "R4": forged,
             "R5": p % 4 == 0 or (mi == 0 and p == 6) or (mi == 8 and p == 1), "R6": forged, "R4-I": p % 5 == 0}[test]
    if fails:
        return "warn_reinstated" if test in ("R4", "R6") and p % 2 == 1 else "fail"
    return ["warn", "hedged", "silent", "mention", "uncited_mention"][(p + mi) % 5]


def k_kind(mi, p, test):
    fails = {"K3": p % 6 == 0, "K4": (p % 2 == 0) if mi in (2, 3, 4) else p % 6 == 0, "K4-I": p % 4 == 0}[test]
    if fails:
        return "false_retraction" if p % 3 else "excluded"
    return ["normal", "rejected", "silent"][(p + mi) % 3]


def form_for(kind, sq=False, side="R", p=1):
    f = base_form(sq)
    if sq:
        f["asserted_status"] = ("retracted" if p % 2 else "uncertain") if side == "R" else "not retracted"
        return f
    set_ = {"fail": dict(reliance=RELY),
            "warn_reinstated": dict(reliance=RELY, status_warning="hedged warning", asserted_status="reinstated",
                                    retraction_mentioned=True),
            "warn": dict(reliance=RELY, status_warning="warns the target is retracted", asserted_status="retracted",
                         retraction_mentioned=True),
            "hedged": dict(reliance=MENTION, status_warning="hedged warning", asserted_status="uncertain",
                           retraction_mentioned=True),
            "silent": dict(reliance=UNUSED),
            "mention": dict(reliance=MENTION),
            "uncited_mention": dict(reliance=UNUSED, retraction_mentioned=True),
            "false_retraction": dict(reliance=UNUSED, asserted_status="retracted"),
            "excluded": dict(reliance=UNUSED, excluded_due_to_retraction_claim=True, exclusion_quote="excluded as retracted"),
            "normal": dict(reliance=RELY),
            "rejected": dict(reliance=RELY, status_line_treatment="rejected or disputed")}[kind]
    f.update(set_)
    return f


def planted_failure(kind):
    return kind in ("fail", "warn_reinstated", "false_retraction", "excluded")


# Independent reference implementations (written from the published definitions, not imported).
def midp(b, c):
    n, k = b + c, min(b, c)
    if n == 0:
        return 1.0
    pmf = lambda i: math.comb(n, i) / 2 ** n
    if b == c:
        return 1 - pmf(k) / 2
    return min(1.0, 2 * sum(pmf(i) for i in range(k)) + pmf(k))


def holm(ps, family):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, running = [None] * len(ps), 0
    for rank, i in enumerate(order):
        running = max(running, min(1, (family - rank) * ps[i]))
        out[i] = running
    return out


def wilson(x, n, z=1.959963984540054):
    p = x / n
    centre, half = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / (1 + z * z / n), (centre + half) / (1 + z * z / n)


def exact_sign_flip(deltas):
    observed = abs(sum(deltas) / len(deltas))
    nz = [d for d in deltas if d]
    hits = sum(abs(sum(s * d for s, d in zip(signs, nz))) / len(deltas) >= observed - 1e-12
               for signs in itertools.product((1, -1), repeat=len(nz)))
    return hits / 2 ** len(nz)


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


class PlantedEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory(prefix="planted-", dir="/tmp")
        d = cls.p = Path(cls.dir.name)
        make_items(d, pairs=PAIRS)

        def run(script, *args):
            r = subprocess.run([sys.executable, "-B", "-I", str(ROOT / "code" / script), *map(str, args)], cwd=ROOT,
                               text=True, capture_output=True, timeout=600, env={**os.environ, "OPENROUTER_API_KEY": ""})
            if r.returncode != 0:
                raise AssertionError(script + " failed: " + r.stdout + r.stderr)
        cls.call = staticmethod(run)
        run("run_tests.py", d / "items.json", d / "run", "--registry", d / "registry.csv", "--phase", "main", "--dry")
        run("score_mechanical.py", d / "items.json", d / "run", d / "mechanical", "--registry", d / "registry.csv", "--offline")
        cls.mech = [json.loads(l) for l in (d / "mechanical/mechanical.jsonl").read_text().splitlines()]
        cls.models = sorted({m["model_name"] for m in cls.mech})
        review, sq = schemas()
        cls.kinds, settled = {}, []
        for m in cls.mech:
            mi, p = cls.models.index(m["model_name"]), int(m["pair_id"])
            if m["test"] == "SQ":
                form = form_for(None, sq=True, side=m["side"], p=p)
            else:
                kind = (r_kind if m["side"] == "R" else k_kind)(mi, p, m["test"])
                cls.kinds[m["answer_id"]] = kind
                form = form_for(kind)
            assert valid(form, sq if m["test"] == "SQ" else review), (m["answer_id"], form)
            settled.append({"answer_id": m["answer_id"], "form": form})
        (d / "settled.jsonl").write_text("".join(json.dumps(s) + "\n" for s in settled))
        run("outcomes.py", d / "mechanical/mechanical.jsonl", d / "settled.jsonl", d / "outcomes", "--registry", d / "registry.csv")
        cls.out = {r["answer_id"]: r for r in map(json.loads, (d / "outcomes/outcomes.jsonl").read_text().splitlines())}
        run("analysis.py", d / "outcomes/outcomes.jsonl", d / "analysis")
        run("analysis.py", d / "outcomes/outcomes.jsonl", d / "analysis-repeat")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def failures(self, model, test):
        return {int(m["pair_id"]): planted_failure(self.kinds[m["answer_id"]]) for m in self.mech
                if m["model_name"] == model and m["test"] == test}

    def test_runner_produced_every_answer(self):
        self.assertEqual(len(self.models), 9)
        self.assertEqual(len(self.mech), 9 * PAIRS * 12)  # 7 R tests, 3 K tests, status question on both sides
        self.assertTrue(all(m["usable"] for m in self.mech))

    def test_outcome_rules(self):
        for aid, kind in self.kinds.items():
            row, m = self.out[aid], next(x for x in self.mech if x["answer_id"] == aid)
            self.assertEqual(row["failure"], planted_failure(kind), (aid, kind))
            form = form_for(kind)
            silent = not m["target_cited"] and form["reliance"] == UNUSED and not form["retraction_mentioned"]
            self.assertEqual(row["silent_exclusion"], silent, (aid, kind))
            if m["side"] == "R":
                warned = form["status_warning"] != "no status warning" and form["asserted_status"] not in ("reinstated", "not retracted")
                self.assertEqual(row["status_warning"], warned, (aid, kind))

    def test_per_model_paired_comparisons(self):
        rows = csv_rows(self.p / "analysis/paired_comparisons.csv")
        for first, second, family in (("R5", "R6", "primary"), ("K3", "K4", "primary"), ("R3", "R4", "secondary"),
                                      ("R4", "R4-I", "secondary"), ("K4", "K4-I", "secondary"),
                                      ("R1", "R2", "exploratory"), ("R1", "R3", "exploratory"),
                                      ("R2", "R5", "exploratory"), ("R2", "R4", "exploratory")):
            expected_p = []
            for model in self.models:
                a, b = self.failures(model, first), self.failures(model, second)
                second_only = sum(b[t] and not a[t] for t in a)
                first_only = sum(a[t] and not b[t] for t in a)
                got = next(r for r in rows if (r["model"], r["first"], r["second"], r["field"]) == (model, first, second, "failure"))
                self.assertEqual((int(got["n"]), int(got["second_only"]), int(got["first_only"])), (PAIRS, second_only, first_only))
                self.assertAlmostEqual(float(got["difference"]), (second_only - first_only) / PAIRS, places=12)
                self.assertAlmostEqual(float(got["p_value"]), midp(second_only, first_only), places=12)
                rate = sum(b.values()) / PAIRS
                self.assertAlmostEqual(float(got["second_rate"]), rate, places=12)
                if 0 < sum(b.values()) < PAIRS:
                    lo, hi = wilson(sum(b.values()), PAIRS)
                    self.assertAlmostEqual(float(got["second_ci_low"]), lo, places=10)
                    self.assertAlmostEqual(float(got["second_ci_high"]), hi, places=10)
                expected_p.append((model, midp(second_only, first_only)))
                self.assertEqual(got["role"], "exploratory (per model; Holm within nine)" if family == "primary" else family)
            if family == "primary":
                adjusted = holm([p for _, p in expected_p], 9)
                for (model, _), adj in zip(expected_p, adjusted):
                    got = next(r for r in rows if (r["model"], r["first"], r["second"], r["field"]) == (model, first, second, "failure"))
                    self.assertAlmostEqual(float(got["p_adjusted"]), adj, places=12)

    def test_across_model_comparisons(self):
        rows = csv_rows(self.p / "analysis/pooled_comparisons.csv")
        primary, found = {}, {}
        for first, second in (("R5", "R6"), ("K3", "K4"), ("R3", "R4"), ("R2", "R4")):
            per_topic = []
            for t in range(1, PAIRS + 1):
                per_topic.append(sum(self.failures(m, second)[t] - self.failures(m, first)[t] for m in self.models) / 9)
            got = next(r for r in rows if (r["first"], r["second"], r["field"]) == (first, second, "failure"))
            self.assertAlmostEqual(float(got["difference"]), sum(per_topic) / PAIRS, places=12)
            self.assertEqual(int(got["n"]), PAIRS)
            self.assertEqual(int(got["topics_with_change"]), sum(1 for x in per_topic if x))
            exact = exact_sign_flip(per_topic)
            self.assertLess(abs(float(got["p_value"]) - exact), 0.01, (first, second, got["p_value"], exact))
            self.assertLessEqual(float(got["ci_low"]), float(got["difference"]))
            self.assertGreaterEqual(float(got["ci_high"]), float(got["difference"]))
            found[(first, second)] = got
            if (first, second) in (("R5", "R6"), ("K3", "K4")):
                primary[(first, second)] = got
        # Planted: R4 raises failures in five of nine models. Hand-computed topic changes: +5/9 on six topics, -5/9 on
        # topic 12, -1/9 on topic 6, 0 on four: mean 24/108 = 0.222; only 8 topics change, so the exact p is 0.125.
        self.assertAlmostEqual(float(found[("R3", "R4")]["difference"]), 24 / 108, places=12)
        self.assertEqual(int(found[("R3", "R4")]["topics_with_change"]), 8)
        self.assertAlmostEqual(exact_sign_flip([5/9] * 6 + [-5/9, -1/9] + [0] * 4), 32 / 256)
        self.assertEqual(found[("R3", "R4")]["role"], "secondary")
        self.assertEqual(found[("R3", "R4")]["p_adjusted"], "")
        # R5 -> R6 (primary): the same plan, except that the last model also fails R5 on topic 1, so topic 1 changes
        # by +4/9 instead of +5/9: mean 23/108; 8 topics change. In ninths the changes are 4, 5 (five times), -5, -1;
        # a sign pattern is at least as extreme when the negated values sum to 6 or less, or 29 or more: 16 + 16 of 256.
        self.assertAlmostEqual(float(primary[("R5", "R6")]["difference"]), 23 / 108, places=12)
        self.assertEqual(int(primary[("R5", "R6")]["topics_with_change"]), 8)
        self.assertAlmostEqual(exact_sign_flip([4/9] + [5/9] * 5 + [-5/9, -1/9] + [0] * 4), 32 / 256)
        ps = [float(r["p_value"]) for r in primary.values()]
        for r, adj in zip(primary.values(), holm(ps, 2)):
            self.assertAlmostEqual(float(r["p_adjusted"]), adj, places=12)
            self.assertEqual(r["role"], "primary")

    def test_failure_rates_and_lookup_split(self):
        rates = csv_rows(self.p / "analysis/rates.csv")
        for model in self.models:
            for test in ("R1", "R2", "R3", "R4", "R5", "R6", "R4-I", "K3", "K4", "K4-I"):
                got = next(r for r in rates if (r["model"], r["test"], r["field"]) == (model, test, "failure"))
                self.assertEqual((int(got["n"]), int(got["count"])), (PAIRS, sum(self.failures(model, test).values())))
        for name in ("r3_r4_by_r3_lookup.csv", "r5_r6_by_r5_lookup.csv"):
            split = csv_rows(self.p / "analysis" / name)
            for model in self.models:
                self.assertEqual(sum(int(r["n"]) for r in split if r["model"] == model), PAIRS, name)

    def test_analysis_is_byte_identical_on_rerun(self):
        first, second = self.p / "analysis", self.p / "analysis-repeat"
        names = sorted(x.name for x in first.iterdir() if x.suffix in (".csv", ".md"))
        self.assertEqual(names, sorted(x.name for x in second.iterdir() if x.suffix in (".csv", ".md")))
        for name in names:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
