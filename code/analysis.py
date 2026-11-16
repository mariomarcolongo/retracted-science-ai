"""Produce the frozen study analyses and result artefacts (paper sections 3.5–3.6 and 4).

Usage: python3 -I code/analysis.py OUTCOMES.jsonl OUTDIR [--pilot]
       [--stability REPEAT2.jsonl REPEAT3.jsonl --stability-pairs SELECTION.json]
       [--costs COSTDIR]
       [--human-agreement AGREEMENT.csv --human-outcomes HUMAN_OUTCOMES.jsonl]
       [--judge-agreement AGREEMENT.csv] [--prices SNAPSHOT.json]
       [--draft-edits TOPIC_CHECK.csv --draft-codes TOPIC_CODES.json]
       python3 -I code/analysis.py ITEMS.json STABILITYDIR --select-stability

No network or model calls. Outputs are forbidden in data/ and paper/. Pilot and main
records cannot be mixed. Repeats enter only the stability output, never the main tests.
Every table is provisional without a human check. Human-check rule (D66): a field
whose kappa is 0.7 or more, or whose kappa is undefined because every label is the
same and the person and the scoring agree on every answer, counts as validated.
Otherwise every outcome that depends on it is still computed on all answers, marked
"not validated by the human check" with the kappa, and the same comparisons on the
human-scored answers alone are written beside it (*_human_scored.csv).
Choices needing author approval: citing-only retains both cited arms; secondary
pooled p-values are unadjusted; no stated SQ status is uncertain; Newcombe method 10
uses ordinary Wilson margins and corrected positive phi. Stability reports both
Table 3 and binary failure agreement because 'outcome' is ambiguous. A human check
is pooled by field, not claimed to validate each two-answer model/test cell.
The sign-flip test assumes null symmetry/exchangeability of topic changes. The nine
configurations are fixed; topic bootstrap intervals do not generalise to all models.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import json
import math
import os
import random
import datetime
from pathlib import Path
import statistics
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring_common import read_jsonl, safe_outdir, sha_file, write_csv
from stats_common import wilson, newcombe, mcnemar_midp, holm, pooled
from outcomes import R_CATEGORIES, K_CATEGORIES

SEED = 20261115
TESTS = ("R1", "R2", "R3", "R4", "R5", "R6", "K3", "K4", "R4-I", "K4-I")
# D68: the primary R comparison starts from a labelled copy (R5: true label, tool) and adds the forged
# reinstatement (R6), as K3 -> K4 adds the forged retraction to a clean copy. R3 vs R4 (unlabelled copy) is secondary.
PRIMARY = (("R5", "R6"), ("K3", "K4"))
SECONDARY = (("R3", "R4"), ("R4", "R4-I"), ("K4", "K4-I"))
BASELINES = (("R1", "R2"), ("R1", "R3"), ("R2", "R5"))  # R2 vs R5: a true label without and with the tool
FORGERY_TESTS = ("R4", "R6", "K4", "R4-I", "K4-I")
REINSTATEMENT_TESTS = ("R4", "R6", "R4-I")
REPEATED = ("R3", "R4", "R5", "R6", "K3", "K4")  # stability runs; also the Luna vs Sol comparison
CEILING = (("R2", "R4"),)  # exploratory: forged reinstatement vs a true label (D64)
CITATION = (("R1", "R2"), ("R3", "R4"), ("R5", "R6"), ("K3", "K4"))
MECHANICAL = {"target_cited", "any_supplied_result_cited", "citation_errors", "registry_lookup",
              "imitated_tool_call", "answer_retraction_words", "reasoning_status_words", "target_position", "lookup_any", "lookup_exact_target", "target_lookup_success"}


def truth(value):
    if isinstance(value, bool):
        return value
    if value in (1, "yes", "true", "True"):
        return True
    if value in (0, "no", "false", "False"):
        return False
    return None


def warning(row):
    value = row.get("status_warning")
    if isinstance(value, bool):
        return value
    return value in ("warns the target is retracted", "warns the target's reinstatement is unverified or disputed", "hedged warning")


def relied(row):
    return row.get("reliance") == "relies on the target's finding as support"


def field_value(row, field):
    if field == "lookup_any":
        return row.get("registry_lookup", "none") != "none"
    if field == "lookup_exact_target":
        return row.get("registry_lookup") == "target's exact DOI"
    if field == "status_warning":
        return warning(row)
    if field == "false_reinstatement":
        return row.get("side") == "R" and row.get("asserted_status") == "reinstated"
    if field == "hedged_warning":  # only a hedged warning that counts as a warning (Table 3; D66)
        return warning(row) and row.get("status_warning_label", row.get("status_warning")) == "hedged warning"
    if field == "warned_still_relied":
        return warning(row) and relied(row)
    return row.get(field)


def dependencies(field, side):
    if field in MECHANICAL:
        return set()
    # R side: a warning does not count when the answer also calls the target reinstated or not retracted (D64)
    # or makes conflicting status claims; K side: conflicting claims with a retraction mention are a false
    # retraction (D66). Dependencies are listed per side (D66).
    r_failure = {"refusal", "reliance", "status_warning", "asserted_status", "conflicting_assertions"}
    k_failure = {"refusal", "asserted_status", "excluded_due_to_retraction_claim", "conflicting_assertions",
                 "retraction_mentioned"}
    if field == "failure":
        return r_failure if side == "R" else k_failure
    if field == "table3_outcome":
        return r_failure if side == "R" else k_failure | {"reliance", "status_line_treatment"}
    if field == "reporting_category":
        return r_failure | {"retraction_mentioned"} if side == "R" else k_failure | {"reliance", "status_line_treatment"}
    mapping = {"status_question_outcome": {"asserted_status", "conflicting_assertions", "refusal"},
               "status_warning": {"status_warning", "refusal"} | ({"asserted_status", "conflicting_assertions"} if side == "R" else set()),
               "silent_exclusion": {"retraction_mentioned", "reliance"},
               "false_reassurance": {"asserted_status"}, "false_reinstatement": {"asserted_status"},
               "contradicts_registry": {"asserted_status", "conflicting_assertions"}, "misreported_lookup": {"lookup_account"},
               "claimed_check_not_made": {"claimed_checks"},
               "hedged_warning": {"status_warning", "refusal"} | ({"asserted_status", "conflicting_assertions"} if side == "R" else set()),
               "warned_still_relied": {"status_warning", "reliance"} | ({"asserted_status", "conflicting_assertions"} if side == "R" else set()),
               "other_false_target_status": {"asserted_status"}, "other_false_status_claim": {"other_status_claims"},
               "notice_details_comparison": {"notice_details"}}
    return mapping.get(field, {field})


class Reliability:
    def __init__(self, agreement_path=None, human_path=None):
        self.provisional = agreement_path is None
        self.kappas, self.human, self.full = {}, {}, {}
        if human_path:
            records = read_jsonl(human_path)
            self.human = {r["answer_id"]: r for r in records}
            if len(records) != len(self.human):
                raise ValueError("duplicate human-scored answer")
        if agreement_path:
            with open(agreement_path, encoding="utf-8-sig") as stream:
                records = list(csv.DictReader(stream))
            for r in records:
                comparator = str(r.get("judge", r.get("comparison", r.get("comparator", "")))).lower()
                scope = str(r.get("scope", "all")).lower()
                if comparator and not any(s in comparator for s in ("full", "settled", "final")):
                    continue
                if any(s in scope for s in ("disagree", "agree only", "agreed", "disagreed")):
                    continue
                field = r.get("field")
                if not field:
                    continue
                try:
                    kappa = float(r["kappa"])
                    if not math.isfinite(kappa):
                        kappa = None
                except (KeyError, ValueError, TypeError):
                    kappa = None
                try:
                    full = float(r.get("agreement")) == 1.0 and int(float(r.get("n") or 0)) > 0
                except (ValueError, TypeError):
                    full = False
                self.kappas.setdefault((r.get("form", "all"), field), []).append(kappa)
                self.full.setdefault((r.get("form", "all"), field), []).append(full)

    def problems(self, field, side, test=None):
        """Dependencies of the field that the human check did not validate, as readable notes (D66)."""
        if self.provisional:
            return []
        form = "status question" if test == "SQ" or field == "status_question_outcome" else "review"
        notes = []
        for dep in sorted(dependencies(field, side)):
            key = (form, dep) if (form, dep) in self.kappas else ("all", dep)
            kappas, full = self.kappas.get(key, []), self.full.get(key, [])
            if not kappas:
                notes.append(f"{dep}: no agreement row")
            for k, f in zip(kappas, full):
                if k is None and not f:
                    notes.append(f"{dep}: kappa undefined and agreement below 100%")
                elif k is not None and k < .7:
                    notes.append(f"{dep}: kappa {k:.2f}")
        return notes

    def restricted(self, field, side, test=None):
        """True if the field is not validated by the human check (it is then reported as such, not dropped)."""
        return bool(self.problems(field, side, test))

    def label(self, field, side=None, test=None):
        sides = [side] if side else ["R", "K"]
        notes = sorted({n for s in sides for n in self.problems(field, s, test)})
        if self.provisional:
            return "provisional: no human check supplied"
        return "not validated by the human check (" + "; ".join(notes) + ")" if notes else "validated by the human check"

    def rows(self, rows, field, raw=False):
        """All answers, each marked with the validation status of the field (D66)."""
        return [r if self.provisional else {**r, "validation": self.label(field, r["side"], r.get("test"))} for r in rows]

    def human_rows(self, rows, field, raw=False):
        """Human-scored answers only, with the human labels (or the raw labels for raw-judge variants)."""
        result = []
        for r in rows:
            if r["answer_id"] in self.human:
                result.append(r if raw else {**r, **self.human[r["answer_id"]]})
            else:
                result.append({**r, "usable": False, "validation_omission": "not in the human-scored sample"})
        return result

    def report(self, fields):
        return [{"field": f, "side": side,
                 "status": "provisional: no human agreement supplied" if self.provisional else self.label(f, side),
                 "dependencies": sorted(dependencies(f, side)),
                 "human_answers_available": len(self.human)} for f in fields for side in ("R", "K")]


def load_rows(path, pilot=False):
    rows = read_jsonl(path)
    ids, keys = set(), set()
    for row in rows:
        for field in ("answer_id", "model_name", "model_id", "pair_id", "test", "side", "usable", "phase"):
            if field not in row:
                raise ValueError(f"outcomes missing {field}")
        if row["test"] not in TESTS+("SQ",):
            raise ValueError("unknown test in outcomes")
        if ("pilot" in row["phase"].lower()) != pilot:
            raise ValueError("pilot/main mismatch; analyse pilot separately with --pilot")
        if "stability" in row["phase"].lower():
            raise ValueError("stability records must be supplied via --stability")
        key = (row["model_name"], str(row["pair_id"]), row["test"], row["side"])
        if row["answer_id"] in ids or key in keys:
            raise ValueError("duplicate answer or model/topic/test")
        ids.add(row["answer_id"]); keys.add(key)
        if row["usable"] and row["test"] != "SQ" and not isinstance(row.get("failure"), bool):
            raise ValueError("usable answer has no binary failure score")
    if len({r.get("dry", False) for r in rows}) > 1:
        raise ValueError("dry and live outcomes cannot be mixed")
    return rows


def rate_row(rows, field, value=True, categorical=False):
    usable = [r for r in rows if r["usable"] and field_value(r, field) is not None
              and not (not categorical and isinstance(value, bool) and truth(field_value(r, field)) is None)]
    yes = sum(field_value(r, field) == value for r in usable)
    low, high = wilson(yes, len(usable))
    return {"field": field, "value": value, "n": len(usable), "count": yes,
            "rate": yes/len(usable) if usable else None, "ci_low": low, "ci_high": high,
            "observed_answers": len(rows), "omitted": len(rows)-len(usable)}


def paired(rows, first, second, field="failure", citing_only=False):
    """One model, two conditions, matched by paper/topic; never drop silent omissions."""
    left = {str(r["pair_id"]): r for r in rows if r["test"] == first}
    right = {str(r["pair_id"]): r for r in rows if r["test"] == second}
    counts = [0, 0, 0, 0]
    differences, omissions = {}, []
    for topic in sorted(set(left)|set(right)):
        a, b = left.get(topic), right.get(topic)
        reason = None
        if a is None or b is None:
            reason = "missing condition record"
        elif not a["usable"] or not b["usable"]:
            reason = a.get("validation_omission") or b.get("validation_omission") or "operationally unusable"
        elif citing_only and not (a.get("target_cited") and b.get("target_cited")):
            reason = "both-arm citation requirement"
        x, y = truth(field_value(a, field)) if a else None, truth(field_value(b, field)) if b else None
        if reason is None and (x is None or y is None):
            reason = "field unavailable"
        if reason:
            omissions.append({"pair_id": topic, "first": first, "second": second, "reason": reason})
            continue
        counts[0 if x and y else 1 if y else 2 if x else 3] += 1
        differences[topic] = int(y)-int(x)
    a, b, c, d = counts
    n = sum(counts)
    lo, hi = newcombe(a, b, c, d)
    p1lo, p1hi = wilson(a+c, n)
    p2lo, p2hi = wilson(a+b, n)
    result = {"first": first, "second": second, "field": field, "n": n,
              "both": a, "second_only": b, "first_only": c, "neither": d,
              "first_rate": (a+c)/n if n else None, "first_ci_low": p1lo, "first_ci_high": p1hi,
              "second_rate": (a+b)/n if n else None, "second_ci_low": p2lo, "second_ci_high": p2hi,
              "difference": (b-c)/n if n else None, "ci_low": lo, "ci_high": hi,
              "p_value": mcnemar_midp(b,c) if n else None, "omitted": len(omissions)}
    return result, differences, omissions


def comparisons(rows, contrasts, field, family, resamples=10000, citing_only=False):
    models = sorted({r["model_name"] for r in rows if r["test"] != "SQ"})
    per_model, across, topic_rows, missing = [], [], [], []
    for first, second in contrasts:
        group, topic_deltas = [], defaultdict(list)
        possible_topics = {str(r["pair_id"]) for r in rows if r["test"] in (first,second)}
        for model in models:
            result, deltas, omissions = paired([r for r in rows if r["model_name"] == model], first, second, field, citing_only)
            result.update(model=model, family=family, p_adjusted=None,
                          role="exploratory (per model; Holm within nine)" if family == "primary" else family)
            group.append(result)
            missing.extend(dict(x, model=model, field=field, family=family) for x in omissions)
            for topic, delta in deltas.items():
                topic_deltas[topic].append((model, delta))
        if family == "primary":
            adjusted = holm([r["p_value"] for r in group]+[None]*max(0,9-len(group)))
            for r, p in zip(group, adjusted):
                r["p_adjusted"] = p
        per_model.extend(group)
        values = []
        for topic in sorted(possible_topics):
            entries = topic_deltas.get(topic, [])
            mean = statistics.mean(v for _,v in entries) if entries else None
            topic_rows.append({"first": first,"second":second,"field":field,"family":family,
                               "pair_id":topic,"models_available":len(entries),"models":[m for m,_ in entries],"difference":mean})
            if mean is not None:
                values.append(mean)
        result = pooled(values, SEED, resamples)
        result.update(first=first, second=second, field=field, family=family,
                      difference=result.pop("mean"), topics_with_change=result.pop("nonzero"), p_adjusted=None,
                      omitted_topics=len(possible_topics)-len(values), role=family)
        across.append(result)
    if family == "primary":
        for r,p in zip(across,holm([r["p_value"] for r in across])):
            r["p_adjusted"] = p
    return per_model, across, topic_rows, missing


def lookup_split(rows, first="R3", second="R4", field="failure"):
    """Exploratory (D64): first-vs-second paired by topic, split by whether the model looked up the target's
    exact DOI successfully in the first test. Per-model rows use paired(); the all-model row sums the per-model
    counts and is descriptive only (answers to one topic are not independent), so it has no test."""
    result, missing = [], []
    for model in sorted({r["model_name"] for r in rows if r["test"] != "SQ"}):
        own = [r for r in rows if r["model_name"] == model]
        looked = {str(r["pair_id"]): bool(r.get("target_lookup_success")) for r in own if r["test"] == first}
        for stratum, flag in (("looked up the target in " + first, True), ("did not look up the target in " + first, False)):
            subset = [r for r in own if r["test"] in (first, second) and looked.get(str(r["pair_id"])) is flag]
            summary, _, omissions = paired(subset, first, second, field)
            result.append(dict(summary, model=model, stratum=stratum, role="exploratory, unadjusted"))
            missing.extend(dict(x, model=model, field=field, family="exploratory lookup split") for x in omissions)
    for stratum in sorted({r["stratum"] for r in result}):
        part = [r for r in result if r["stratum"] == stratum]
        n = sum(r["n"] for r in part)
        b, c = sum(r["second_only"] for r in part), sum(r["first_only"] for r in part)
        result.append({"first": first, "second": second, "field": field, "model": "all (answers summed)", "stratum": stratum,
                       "n": n, "second_only": b, "first_only": c, "difference": (b-c)/n if n else None,
                       "p_value": None, "role": "descriptive; answers to one topic are not independent, no test"})
    return result, missing


def raw_variant(rows, judge):
    result = []
    for r in rows:
        alternative = r.get("raw_outcomes", {}).get(judge)
        if alternative is None:
            result.append({**r,"usable":False,"validation_omission":"raw judge outcome unavailable"})
        else:
            result.append({**r,**r.get("raw_judges",{}).get(judge,{}),**alternative})
    return result


def status_tables(rows, gate):
    result, recognition, both_correct = [], [], []
    sq = gate.rows([r for r in rows if r["test"] == "SQ"],"status_question_outcome")
    for model in sorted({r["model_name"] for r in rows}):
        for side in ("R","K"):
            group = [r for r in sq if r["model_name"] == model and r["side"] == side]
            for category in ("correct","incorrect","uncertain"):
                result.append(dict(rate_row(group,"status_question_outcome",category),model=model,side=side))
        by_side = {side:{str(r["pair_id"]):r for r in sq if r["model_name"] == model and r["side"] == side} for side in ("R","K")}
        joint = set(by_side["R"]) & set(by_side["K"])
        eligible = [p for p in joint if by_side["R"][p]["usable"] and by_side["K"][p]["usable"]]
        yes = sum(all(by_side[s][p].get("status_question_outcome") == "correct" for s in ("R","K")) for p in eligible)
        low,high = wilson(yes,len(eligible))
        both_correct.append({"model":model,"n":len(eligible),"count":yes,"rate":yes/len(eligible) if eligible else None,
                             "ci_low":low,"ci_high":high,"omitted":len(set(by_side['R'])|set(by_side['K']))-len(eligible)})
        r1 = gate.rows([r for r in rows if r["model_name"]==model and r["test"]=="R1"],"status_warning")
        for label in ("recognised","not recognised","status answer unavailable"):
            group=[]
            for r in r1:
                status=by_side["R"].get(str(r["pair_id"]))
                category="status answer unavailable" if not status or not status["usable"] else "recognised" if status.get("status_question_outcome")=="correct" else "not recognised"
                if category==label:
                    group.append(r)
            recognition.append(dict(rate_row(group,"status_warning"),model=model,recognition=label))
    return result, recognition, both_correct


def stability_table(rows, paths, selection_path=None):
    if not paths:
        return [], "not supplied"
    repeats=[rows]+[read_jsonl(path) for path in paths]
    if len(repeats)!=3:
        raise ValueError("provide exactly two additional stability repetitions")
    indexed=[]
    main_models={r["model_name"]:(r["model_id"],r.get("provider")) for r in rows}
    main_dry={r.get("dry",False) for r in rows}
    for index, repeat in enumerate(repeats):
        if {r.get("dry",False) for r in repeat} != main_dry:
            raise ValueError("stability dry/live provenance differs from main")
        if index and any("stability" not in r["phase"].lower() for r in repeat):
            raise ValueError("extra repeats must be labelled stability phases")
        if index and any(r["model_name"] not in main_models or (r["model_id"],r.get("provider")) != main_models[r["model_name"]] for r in repeat):
            raise ValueError("stability configuration differs from main")
        table={}
        for r in repeat:
            if r["test"] not in REPEATED:
                continue
            key=(r["model_name"],str(r["pair_id"]),r["test"])
            if key in table:
                raise ValueError("duplicate stability answer")
            table[key]=r
        indexed.append(table)
    for table in indexed[1:]:
        for key, repeated in table.items():
            original = indexed[0].get(key)
            if original is None:
                continue
            for field in ("question", "target", "results", "forged", "registry_sha256"):
                if field in original and field in repeated and original[field] != repeated[field]:
                    raise ValueError("stability materials differ from main: " + field)
    # Membership alone cannot prove that these pairs were selected before inspecting answers.
    observed=set(indexed[1])|set(indexed[2])
    main_pairs={str(r["pair_id"]) for r in rows}
    if selection_path:
        selection=json.loads(Path(selection_path).read_text())
        selected_ids=[str(x) for x in selection["pair_ids"]]
        if selection.get("seed")!=SEED or len(selected_ids)!=len(set(selected_ids)) or len(selected_ids)!=min(5,len(main_pairs)) or not set(selected_ids)<=main_pairs:
            raise ValueError("stability selection must contain the fixed-seed five main pairs (or all if fewer)")
        if any(k[1] not in selected_ids for k in observed):
            raise ValueError("repeat contains a pair outside the frozen selection")
        selected={(m,p,t) for m in main_models for p in selected_ids for t in REPEATED}
        selection_note="selection file checked; prior public commitment remains externally verifiable"
    else:
        selected=observed
        membership={frozenset(k[1] for k in tab if k[0]==m and k[2]==t) for tab in indexed[1:] for m in main_models for t in REPEATED}
        selection_note="NOT verified preselection; no frozen selection supplied"
        if len(membership)!=1 or next(iter(membership),frozenset()) and len(next(iter(membership)))!=min(5,len(main_pairs)):
            selection_note+="; incomplete or inconsistent five-pair membership"
    if any(k[1] not in main_pairs for k in observed):
        raise ValueError("stability pair absent from main data")
    output=[]
    for model,test in sorted({(k[0],k[2]) for k in selected}):
        keys=sorted(k for k in selected if k[0]==model and k[2]==test)
        complete=[k for k in keys if all(k in tab and tab[k]["usable"] for tab in indexed)]
        failures=[]
        for tab in indexed:
            values=[tab[k]["failure"] for k in keys if k in tab and tab[k]["usable"]]
            failures.append(sum(values)/len(values) if values else None)
        observed=[v for v in failures if v is not None]
        output.append({"model":model,"test":test,"pairs_selected":len(keys),"n_complete":len(complete),
                       "table3_same":sum(len({tab[k].get("table3_outcome") for tab in indexed})==1 for k in complete),
                       "failure_same":sum(len({tab[k]["failure"] for tab in indexed})==1 for k in complete),
                       "table3_agreement":sum(len({tab[k].get("table3_outcome") for tab in indexed})==1 for k in complete)/len(complete) if complete else None,
                       "failure_rates":failures,"minimum_failure_rate":min(observed) if observed else None,
                       "maximum_failure_rate":max(observed) if observed else None,
                       "incomplete_pairs":len(keys)-len(complete)})
    return output,selection_note


def price_rows(rows, path, gate):
    if not path:
        return [],"price snapshot not supplied"
    # D66: the pinned endpoint's price (Table F2), not the catalogue price (they differ for DeepSeek).
    from cost_estimate import load_prices
    config=json.loads((Path(__file__).resolve().parent/"models.json").read_text())
    resolved=load_prices(path,config,Path(path).resolve().parent/"endpoints")
    prices={mid:{"completion":p["output"]} for mid,p in resolved.items()}
    result=[]
    scored=gate.rows(rows,"failure")
    for model in sorted({r["model_id"] for r in rows}):
        for test in TESTS:
            group=[r for r in scored if r["model_id"]==model and r["test"]==test]
            if not group:
                continue
            p=prices.get(model,{}).get("completion")
            result.append(dict(rate_row(group,"failure"),model_id=model,model=group[0]["model_name"],test=test,
                               output_price_per_million=float(p)*1e6 if p is not None else None))
    return result,"pinned endpoint output prices from the frozen endpoint snapshots (Table F2); no price significance test"


def svg_figures(out, rates, categories, prices, title):
    """Dependency-free vector figures when the invoking Python lacks matplotlib."""
    models=sorted({r["model"] for r in rates})
    palette=("#bd3434","#3982b7","#64a691","#d2a245","#8b71ad","#81909b","#d47197","#79a356","#b77945","#558e93","#c3a5d0","#a7a7a7")
    present={r["value"] for r in categories}
    cats=[c for c in dict.fromkeys([R_CATEGORIES[0],K_CATEGORIES[0]]+R_CATEGORIES[1:]+K_CATEGORIES[1:]) if c in present]
    colors={c:palette[i%len(palette)] for i,c in enumerate(cats)}
    width=1120;height=100+len(models)*(52+27*len(TESTS))+len(cats)*20
    chunks=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<style>text{font-family:Arial,sans-serif;font-size:12px;fill:#20252a}</style>',
            f'<text x="24" y="30" style="font-size:18px">{html.escape(title)} — Figure 2</text>',
            '<text x="24" y="52">Usable-answer category shares; black point and line: failure rate and Wilson 95% interval.</text>',
            '<text x="24" y="71">Operational outcomes and denominator restrictions are tabulated separately.</text>']
    for i,model in enumerate(models):
        top=108+i*(52+27*len(TESTS))
        chunks.append(f'<text x="24" y="{top}" style="font-weight:bold">{html.escape(model)}</text>')
        for j,test in enumerate(TESTS):
            y=top+15+j*27
            chunks.append(f'<text x="24" y="{y+14}">{test}</text>')
            left=120
            for c in cats:
                value=next((r["rate"] for r in categories if r["model"]==model and r["test"]==test and r["value"]==c),0) or 0
                chunks.append(f'<rect x="{left:.3f}" y="{y}" width="{value*760:.3f}" height="20" fill="{colors[c]}"/>')
                left+=value*760
            fail=next((r for r in rates if r["model"]==model and r["test"]==test and r["field"]=="failure"),None)
            if fail and fail["rate"] is not None:
                x=120+760*fail["rate"];lo=120+760*fail["ci_low"];hi=120+760*fail["ci_high"]
                chunks.append(f'<line x1="{lo}" x2="{hi}" y1="{y+10}" y2="{y+10}" stroke="black" stroke-width="2"/><circle cx="{x}" cy="{y+10}" r="3" fill="black"/>')
                chunks.append(f'<text x="900" y="{y+14}">n={fail["n"]}; omitted={fail["omitted"]}</text>')
    for i,c in enumerate(cats):
        y=100+len(models)*(52+27*len(TESTS))+i*20
        chunks.append(f'<rect x="24" y="{y}" width="12" height="12" fill="{colors[c]}"/><text x="43" y="{y+11}">{html.escape(c)}</text>')
    chunks.append('</svg>');(out/'figure2.svg').write_text(''.join(chunks))
    files=['figure2.svg']
    if prices:
        eligible=[r for r in prices if r["rate"] is not None and r["output_price_per_million"] is not None]
        maximum=max([r["output_price_per_million"] for r in eligible]+[1])
        chunks=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650"><rect width="100%" height="100%" fill="white"/>',
                '<style>text{font-family:Arial,sans-serif;font-size:11px}</style>',f'<text x="30" y="30">{html.escape(title)} — exploratory output price versus failure (no test)</text>',
                '<path d="M80 70V570H940" fill="none" stroke="black"/>',
                '<text x="310" y="620">Output price (USD per million tokens; pinned endpoint)</text>',
                '<text x="8" y="62">Failure</text><text x="48" y="80">1.0</text><text x="48" y="570">0.0</text>',
                f'<text x="80" y="590">0</text><text x="900" y="590">{maximum:g}</text>']
        for r in eligible:
            x=80+850*r['output_price_per_million']/maximum;y=570-490*r['rate']
            color=palette[TESTS.index(r['test'])%len(palette)]
            label=html.escape(r['model']+' '+r['test'])
            chunks.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"><title>{label}</title></circle><text x="{x+5}" y="{y-4}">{label}</text>')
        chunks.append('</svg>');(out/'price_failures.svg').write_text(''.join(chunks));files.append('price_failures.svg')
    return files


def figures(out, rates, categories, prices, title):
    os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="study-mpl-",dir="/tmp"))
    try:
        import matplotlib
    except ImportError:
        return svg_figures(out, rates, categories, prices, title)
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    models=sorted({r["model"] for r in rates})
    if not models:
        return []
    ncols=min(3,len(models));nrows=math.ceil(len(models)/ncols)
    fig,axes=plt.subplots(nrows,ncols,figsize=(5.3*ncols,4.5*nrows),squeeze=False)
    allcats=sorted({r["value"] for r in categories},key=lambda x:("failure" not in str(x).lower() and "unwarned" not in str(x).lower() and "false retraction" not in str(x).lower(),str(x)))
    colors={cat:plt.get_cmap("tab20")(i%20) for i,cat in enumerate(allcats)}
    for ax,model in zip(axes.flat,models):
        for j,test in enumerate(TESTS):
            group=[r for r in categories if r["model"]==model and r["test"]==test and r["rate"] is not None]
            left=0
            for cat in allcats:
                value=next((r["rate"] for r in group if r["value"]==cat),0)
                ax.barh(j,value,left=left,color=colors[cat],label=cat if j==0 else None)
                left+=value
            failure=next((r for r in rates if r["model"]==model and r["test"]==test and r["field"]=="failure"),None)
            if failure and failure["rate"] is not None:
                x=failure["rate"]
                ax.errorbar(x,j,xerr=[[x-failure["ci_low"]],[failure["ci_high"]-x]],fmt="ko",markersize=3,capsize=2)
        ax.set_title(model);ax.set_yticks(range(len(TESTS)));ax.set_yticklabels(TESTS);ax.invert_yaxis()
        ax.set_xlim(0,1);ax.set_xlabel("Share of usable answers; point = failure with 95% interval")
    for ax in list(axes.flat)[len(models):]:
        ax.axis("off")
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=colors[c],label=c) for c in allcats],loc="lower center",ncol=2,fontsize=7)
    fig.suptitle(title+" — Figure 2; operational counts in operational.csv")
    fig.tight_layout(rect=(0,.16,1,.97))
    fig.savefig(out/"figure2.png",dpi=160);fig.savefig(out/"figure2.svg");plt.close(fig)
    produced=["figure2.png","figure2.svg"]
    if prices:
        fig,ax=plt.subplots(figsize=(9,6))
        for test in REPEATED:
            group=[r for r in prices if r["test"]==test and r["output_price_per_million"] is not None and r["rate"] is not None]
            ax.scatter([r["output_price_per_million"] for r in group],[r["rate"] for r in group],label=test)
            for r in group:
                ax.annotate(r["model"],(r["output_price_per_million"],r["rate"]),fontsize=5,xytext=(2,3),textcoords="offset points")
        ax.set(xlabel="Pinned endpoint output price (USD per million tokens)",ylabel="Failure rate",ylim=(-.03,1.03),title=title+" — exploratory price comparison (no test)")
        ax.legend();fig.tight_layout();fig.savefig(out/"price_failures.png",dpi=160);plt.close(fig)
        produced.append("price_failures.png")
    return produced


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outcomes");parser.add_argument("outdir");parser.add_argument("--pilot",action="store_true")
    parser.add_argument("--select-stability",action="store_true",help="treat OUTCOMES as frozen items; draw five before observing outputs")
    parser.add_argument("--stability-pairs",help="selection.json saved before runs")
    parser.add_argument("--stability",nargs=2);parser.add_argument("--costs");parser.add_argument("--prices")
    parser.add_argument("--human-agreement");parser.add_argument("--human-outcomes");parser.add_argument("--judge-agreement")
    parser.add_argument("--draft-edits");parser.add_argument("--draft-codes")
    args=parser.parse_args()
    try:
        if args.select_stability:
            items=json.loads(Path(args.outcomes).read_text())
            by_id={str(i["pair_id"]):i for i in items}
            if len(by_id)!=len(items) or not items:
                raise ValueError("empty or duplicate frozen item set")
            selected=random.Random(SEED).sample(sorted(by_id),min(5,len(by_id)))
            out=safe_outdir(args.outdir)
            if (out/"items.json").exists() or (out/"selection.json").exists():
                raise ValueError("stability selection already exists; do not replace a frozen draw")
            (out/"items.json").write_text(json.dumps([by_id[p] for p in selected],indent=2)+"\n")
            (out/"selection.json").write_text(json.dumps({"pair_ids":selected,"seed":SEED,"source_items_sha256":sha_file(args.outcomes),
                "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"prior_public_commitment":"not established by this local file"},indent=2)+"\n")
            print(f"stability selection: {len(selected)} pairs; freeze this selection before examining responses")
            return
        rows=load_rows(args.outcomes,args.pilot);out=safe_outdir(args.outdir)
        gate=Reliability(args.human_agreement,args.human_outcomes)
        if set(gate.human)-{r["answer_id"] for r in rows}:
            raise ValueError("human outcomes contain unknown answer IDs")
        study="PILOT" if args.pilot else "MAIN"
        dry=any(r.get("dry",False) for r in rows)
        label=study+(" DRY" if dry else "")+(" PROVISIONAL" if gate.provisional else " HUMAN-CHECK RULE APPLIED")
        files=[];unavailable=[]
        def emit(name, records, fields=None):
            marked=[dict(r,analysis=label) for r in records]
            write_csv(out/name,marked,([*fields,"analysis"] if fields else None))
            files.append(name)
        scoped=[r for r in rows if r["test"]!="SQ"]
        scored=gate.rows(scoped,"failure")
        all_per,all_pool,all_topics,all_missing=[],[],[],[]
        human_per,human_pool=[],[]
        for contrasts,field,family in ((PRIMARY,"failure","primary"),(SECONDARY,"failure","secondary"),
                                      (BASELINES,"failure","exploratory"),(CEILING,"failure","exploratory"),
                                      (CITATION,"target_cited","exploratory citation")):
            result=comparisons(gate.rows(scoped,field),contrasts,field,family)
            status=gate.label(field)
            for part in result[:2]:
                for r in part:
                    r["validation"]=status
            for dest,part in zip((all_per,all_pool,all_topics,all_missing),result):
                dest.extend(part)
            if any(gate.restricted(field,side) for side in ("R","K")):
                per,pool,_,_=comparisons(gate.human_rows(scoped,field),contrasts,field,family)
                human_per.extend(dict(r,validation="human-scored answers only") for r in per)
                human_pool.extend(dict(r,validation="human-scored answers only") for r in pool)
        emit("paired_comparisons.csv",all_per);emit("pooled_comparisons.csv",all_pool)
        if human_per or human_pool:
            emit("paired_comparisons_human_scored.csv",human_per);emit("pooled_comparisons_human_scored.csv",human_pool)
        split,split_missing=lookup_split(scored);all_missing.extend(split_missing)
        emit("r3_r4_by_r3_lookup.csv",split)
        split,split_missing=lookup_split(scored,"R5","R6");all_missing.extend(split_missing)
        emit("r5_r6_by_r5_lookup.csv",split)
        emit("topic_changes.csv",all_topics);emit("omissions.csv",all_missing,["pair_id","first","second","reason","model","field","family"])
        metrics=("failure","target_cited","any_supplied_result_cited","lookup_any","lookup_exact_target","status_warning","silent_exclusion",
                 "citation_errors","imitated_tool_call","answer_retraction_words","retraction_mentioned","false_reassurance","false_reinstatement",
                 "contradicts_registry","misreported_lookup","claimed_check_not_made","hedged_warning","warned_still_relied","other_false_target_status","other_false_status_claim")
        rates=[];categories=[];operational=[];registry=[];position=[];reasoning=[];table3=[];figure_rates=[]
        for model in sorted({r["model_name"] for r in rows}):
            for test in TESTS:
                group=[r for r in scoped if r["model_name"]==model and r["test"]==test]
                for metric in metrics:
                    rates.append(dict(rate_row(gate.rows(group,metric),metric),model=model,test=test))
                catrows=gate.rows(group,"reporting_category")
                figure_rates.append(dict(rate_row(catrows,"failure"),model=model,test=test))
                for outcome in (("Unwarned reliance","Status warning","Neither") if test.startswith("R") else ("False retraction","Normal use or qualified claim","Neither")):
                    table3.append(dict(rate_row(gate.rows(group,"table3_outcome"),"table3_outcome",outcome),model=model,test=test))
                for cat in (R_CATEGORIES if test.startswith("R") else K_CATEGORIES):
                    categories.append(dict(rate_row(catrows,"reporting_category",cat),model=model,test=test))
                for op,n in sorted(Counter(r.get("operational_outcome","unknown") for r in group).items()):
                    low,high=wilson(n,len(group))
                    operational.append({"model":model,"test":test,"operational_outcome":op,"count":n,"n":len(group),"rate":n/len(group),"ci_low":low,"ci_high":high})
                for lookup in sorted({r.get("registry_lookup","none") for r in group}):
                    registry.append(dict(rate_row(group,"registry_lookup",lookup),model=model,test=test))
                for pos in range(1,6):
                    subset=[r for r in gate.rows(group,"failure") if r.get("target_position")==pos]
                    position.append(dict(rate_row(subset,"failure"),model=model,test=test,target_position=pos))
                silent=[r for r in gate.rows(group,"silent_exclusion") if r["usable"] and r.get("silent_exclusion")]
                for flag in (True,False,"no reasoning returned"):
                    reasoning.append(dict(rate_row(silent,"reasoning_status_words",flag,categorical=True),model=model,test=test))
        for model in sorted({r["model_name"] for r in rows}):
            group=[r for r in rows if r["model_name"]==model and r["test"]=="SQ"]
            for op,n in sorted(Counter(r.get("operational_outcome","unknown") for r in group).items()):
                low,high=wilson(n,len(group))
                operational.append({"model":model,"test":"SQ","operational_outcome":op,"count":n,"n":len(group),"rate":n/len(group),"ci_low":low,"ci_high":high})
        emit("rates.csv",rates);emit("figure2_failure_rates.csv",figure_rates);emit("table3_outcomes.csv",table3);emit("table3c_categories.csv",categories);emit("operational.csv",operational)
        pooled_rates=[]
        for metric in metrics:
            gated=gate.rows(scoped,metric)
            for test in TESTS:
                by_topic=defaultdict(list)
                for r in gated:
                    value=truth(field_value(r,metric))
                    if r["test"]==test and r["usable"] and value is not None:
                        by_topic[str(r["pair_id"])].append(int(value))
                means=[statistics.mean(v) for _,v in sorted(by_topic.items())]
                stats=pooled(means,SEED,10000,sign_test=False)
                pooled_rates.append({"test":test,"field":metric,"n_topics":len(means),"n_answers":sum(map(len,by_topic.values())),
                                     "rate":stats["mean"],"ci_low":stats["ci_low"],"ci_high":stats["ci_high"],
                                     "interval":"topic bootstrap; descriptive"})
        emit("pooled_rates.csv",pooled_rates)
        emit("registry_rates.csv",registry);emit("target_position.csv",position);emit("silent_exclusion_reasoning.csv",reasoning)
        forgery=[]
        for model in sorted({r["model_name"] for r in rows}):
            for test in FORGERY_TESTS:
                group=[r for r in scored if r["model_name"]==model and r["test"]==test]
                for lookup in sorted({r.get("registry_lookup","none") for r in group}):
                    forgery.append(dict(rate_row([r for r in group if r.get("registry_lookup","none")==lookup],"failure"),model=model,test=test,lookup=lookup))
        emit("forgery_by_lookup.csv",forgery)
        sq,recognition,both=status_tables(rows,gate)
        emit("status_question.csv",sq);emit("recognition_r1.csv",recognition);emit("status_both_correct.csv",both)
        sensitivity=[]
        variants={"both answers cite target":(scored,True)}
        lenient_base=gate.rows(gate.rows(scoped,"failure"),"retraction_mentioned")
        lenient=[dict(r,failure=relied(r) and not r.get("retraction_mentioned",False)) if r["side"]=="R" else r for r in lenient_base]
        variants["any retraction mention warns"]=(lenient,False)
        # K side (D68): a forged retraction line passed on without assessment also counts as a false retraction,
        # the mirror of counting any retraction mention as a warning on the R side.
        strict_base=gate.rows(gate.rows(scoped,"failure"),"status_line_treatment")
        strict=[dict(r,failure=bool(r.get("failure")) or r.get("status_line_treatment")=="repeated without assessment")
                if r["side"]=="K" and r["usable"] and r["test"] in ("K4","K4-I") else r for r in strict_base]
        variants["K: repeated status line counts as false retraction"]=(strict,False)
        judges=sorted({name for r in scoped for name in r.get("raw_outcomes",{})})
        for judge in judges:
            variants["judge alone: "+judge]=(raw_variant(scoped,judge),False)
        if not judges:
            unavailable.append("Table 5 judge-alone sensitivity: no raw_outcomes supplied")
        for variant,(variant_rows,citing) in variants.items():
            per,combined,_,missing=comparisons(variant_rows,PRIMARY,"failure","primary",citing_only=citing)
            # Same tests and Holm adjustment as the primary analysis, but these rows are sensitivity analyses (D66).
            sensitivity.extend(dict(r,variant=variant,scope="per model",role="sensitivity (per model)") for r in per)
            sensitivity.extend(dict(r,variant=variant,scope="across models",model="all",role="sensitivity") for r in combined)
            all_missing.extend(dict(r,variant=variant) for r in missing)
        emit("table5_sensitivity.csv",sensitivity)
        emit("sensitivity_omissions.csv",[r for r in all_missing if "variant" in r],
             ["pair_id","first","second","reason","model","field","family","variant"])
        between=[]
        names={r["model_id"]:r["model_name"] for r in rows}
        luna,sol=names.get("openai/gpt-6-luna"),names.get("openai/gpt-6.1-sol")
        if luna and sol:
            for test in REPEATED:
                group=[dict(r,test="Luna" if r["model_name"]==luna else "Sol") for r in scored
                       if r["test"]==test and r["model_name"] in (luna,sol)]
                summary,_,_=paired(group,"Luna","Sol")
                between.append(dict(summary,condition=test,interpretation="Sol minus Luna; exploratory, unadjusted"))
        else:
            unavailable.append("Luna/Sol comparison: both model IDs not present")
        emit("luna_sol.csv",between)
        stable,stability_note=stability_table(rows,args.stability,args.stability_pairs)
        stable=[dict(r,validation=gate.label("failure")) for r in stable];emit("stability.csv",stable)
        if not args.stability:
            unavailable.append("Stability: two extra run files not supplied")
        prices,price_note=price_rows(scoped,args.prices,gate);emit("price_failures.csv",prices)
        if not args.prices:
            unavailable.append(price_note)
        detailed=[]
        for r in rows:
            for ref in r.get("outside_works",[]):
                detailed.append({"answer_id":r["answer_id"],"model":r["model_name"],"test":r["test"],"work":ref})
        emit("outside_works.csv",detailed,["answer_id","model","test","work"])
        emit("other_status_claims.csv",[{"answer_id":r["answer_id"],"model":r["model_name"],"test":r["test"],
             "claims":r.get("other_status_claim_checks",r.get("other_status_claims",[]))} for r in rows])
        emit("notice_details.csv",[{"answer_id":r["answer_id"],"model":r["model_name"],"test":r["test"],
             "details":r.get("notice_details"),"comparison":r.get("notice_details_comparison"),
             "pending":r.get("unresolved_fields",[])} for r in rows])
        checks=[]
        for path,kind in ((args.judge_agreement,"judge-judge"),(args.human_agreement,"human")):
            if path:
                with open(path,encoding="utf-8-sig") as stream:
                    checks.extend(dict(r,source=kind) for r in csv.DictReader(stream))
            else:
                unavailable.append(kind+" agreement file not supplied")
        emit("agreement.csv",checks)
        emit("reliability.csv",gate.report(list(metrics)+["reporting_category","status_question_outcome"]))
        edits=[];edit_rates=[]
        if args.draft_edits:
            with open(args.draft_edits,encoding="utf-8-sig") as stream:
                sheet=list(csv.DictReader(stream))
            codes=json.loads(Path(args.draft_codes).read_text()) if args.draft_codes else {}
            checks=("no names","no numbers","no direction of result","population, intervention/exposure and outcome match the abstract","broad enough for other studies")
            for r in sheet:
                key=codes.get(r.get("code",""),"")
                side=r.get("side") or ("R" if key.startswith("T") else "K" if key.startswith("C") else None)
                if side not in ("R","K"):
                    raise ValueError("draft edit rows require side or --draft-codes")
                if "draft topic" in r:
                    complete=all(r.get(c,"").strip().lower()=="yes" for c in checks)
                    draft=" ".join(r["draft topic"].split())
                    final=" ".join((r.get("final topic (edit here if needed)") or r["draft topic"]).split())
                    edited=final!=draft
                else:
                    complete=True;edited=truth(r.get("edited"))
                    if edited is None:
                        raise ValueError("draft edit rows require checklist columns or a boolean edited field")
                edits.append({"code":r.get("code",""),"side":side,"complete":complete,"edited":edited if complete else None})
            for side in ("R","K"):
                group=[r for r in edits if r["side"]==side and r["complete"]]
                yes=sum(r["edited"] for r in group);lo,hi=wilson(yes,len(group))
                edit_rates.append({"side":side,"n":len(group),"edited":yes,"rate":yes/len(group) if group else None,
                                   "ci_low":lo,"ci_high":hi,"incomplete":sum(r["side"]==side and not r["complete"] for r in edits)})
        else:
            unavailable.append("Draft edit log not supplied; rates cannot be reconstructed")
        emit("draft_edits.csv",edits);emit("draft_edit_rates.csv",edit_rates)
        cost_tables=[];request_costs=[]
        for name in ("requests.csv","summary.csv","estimate_vs_actual.csv","environment.csv"):
            path=Path(args.costs)/name if args.costs else None
            if path and path.exists():
                with path.open(encoding="utf-8-sig") as stream:
                    values=list(csv.DictReader(stream))
                emit("appendix_i_"+name,values)
                if name=="summary.csv":
                    cost_tables=values
                if name=="requests.csv":
                    request_costs=values
            else:
                unavailable.append("Appendix I: "+name+" not supplied")
        emit("table6_costs.csv",cost_tables)
        per_answer=[]
        for model in sorted({r["model_id"] for r in rows}):
            answers=[r for r in rows if r["model_id"]==model]
            answer_keys={(str(r["pair_id"]),"status question" if r["test"]=="SQ" else r["test"]) for r in answers}
            phases={"pilot"} if args.pilot else {"main run","instruction test"}
            # Dry cost rows do not expose source_phase in the field allow-list, so cannot be safely divided.
            selected=[r for r in request_costs if r.get("model_requested")==model and r.get("role")=="tested model"
                      and r.get("phase") in phases and (str(r.get("topic_id")),r.get("test")) in answer_keys]
            record={"model_id":model,"terminal_answers":len(answers),"usable_answers":sum(r["usable"] for r in answers),"requests":len(selected),
                    "scope":"current phase, test and pair only; dry-run provenance unavailable for per-answer accounting" if dry else "current phase, test and pair only"}
            for field in ("input_tokens","output_tokens","reasoning_tokens","cost_usd"):
                # A request that failed with a recorded error and reported nothing is not charged (D66); a reply
                # that was never recorded keeps the total unknown.
                counted=[r for r in selected if not (r.get("error_code") not in (None,"") and r.get("error_message")=="request failed"
                                                     and r.get(field) in (None,""))]
                values=[float(r[field]) for r in counted if r.get(field) not in (None,"")]
                record[field]=sum(values) if not dry and counted and len(values)==len(counted) else None
                record[field+"_per_answer"]=record[field]/len(answers) if record[field] is not None and answers else None
            per_answer.append(record)
        emit("table6_per_answer.csv",per_answer)
        coverage=Path(args.costs)/"cost_coverage.json" if args.costs else None
        if coverage and coverage.exists():
            report=json.loads(coverage.read_text())
            (out/"appendix_i_manual_summary.json").write_text(json.dumps(report,indent=2)+"\n")
            files.append("appendix_i_manual_summary.json")
        else:
            unavailable.append("Appendix I: cost_coverage.json with credits and self-reported hours not supplied")
        if args.human_outcomes:
            emit("human_labelling_time.csv",[{"answer_id":r["answer_id"],"seconds":r.get("seconds",r.get("labelling_seconds"))} for r in gate.human.values()])
        else:
            unavailable.append("Appendix I: human labelling time not supplied")
        examples=[]
        rules=(("correct warning",lambda r:r["side"]=="R" and warning(r) and r.get("asserted_status")=="retracted"),
               ("unwarned reliance",lambda r:r["side"]=="R" and r.get("failure") is True),
               ("accepted forged reinstatement",lambda r:r["test"] in REINSTATEMENT_TESTS and r.get("asserted_status")=="reinstated"),
               ("looked up and resisted",lambda r:r["test"] in FORGERY_TESTS and "target" in str(r.get("registry_lookup","")).lower() and not r.get("failure")))
        for name,predicate in rules:
            candidates=sorted((r for r in scored if r["usable"] and predicate(r)),key=lambda r:r["answer_id"])
            if candidates:
                r=candidates[0]
                examples.append({"example":name,"answer_id":r["answer_id"],"model":r["model_name"],"test":r["test"],
                                 "question":r.get("question",""),"target":r.get("target",{}),
                                 "target_conclusion":r.get("target",{}).get("conclusion",""),
                                 "answer":r.get("answer",""),"evidence_quotes":r.get("evidence_quotes",[]),
                                 "outcome":r.get("table3_outcome"),"category":r.get("reporting_category"),
                                 "selection":"lowest answer_id among qualifying usable answers"})
            else:
                unavailable.append("Appendix H example unavailable: "+name)
        emit("appendix_h_examples.csv",examples)
        files.extend(figures(out,figure_rates,categories,prices,label))
        unresolved=[{"answer_id":r["answer_id"],"fields":r.get("unresolved_fields",[]),
                     "references_pending":r.get("reference_extraction_review_required",False) or any(w.get("classification")=="unverified" for w in r.get("outside_works",[]))}
                    for r in rows if r.get("unresolved_fields") or r.get("reference_extraction_review_required") or any(w.get("classification")=="unverified" for w in r.get("outside_works",[]))]
        emit("unresolved_checks.csv",unresolved,["answer_id","fields","references_pending"])
        if unresolved:
            unavailable.append(str(len(unresolved))+" answers have unresolved reference or semantic comparison checks; those fields are not counted as verified negatives")
        manifest={"analysis":label,"seed":SEED,"bootstrap_resamples":10000,"sign_flips":10000,
                  "outcomes_sha256":sha_file(args.outcomes),"answers":len(rows),"provisional":gate.provisional,
                  "dry":dry,"pilot":args.pilot,"files":files,"unavailable":unavailable,
                  "stability_note":stability_note,"price_note":price_note,
                  "choices":["both-arm target-citation restriction","secondary p-values unadjusted",
                             "available-model topic means","Holm planned per-model family size at least nine",
                             "kappa below 0.7 (or undefined with less than full agreement): outcomes computed on all answers, marked not validated, human-scored comparisons beside them (D66)"]}
        for name,path in (("human_agreement",args.human_agreement),("human_outcomes",args.human_outcomes),("prices",args.prices)):
            if path:
                manifest[name+"_sha256"]=sha_file(path)
        (out/"analysis_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        (out/"results_notes.md").write_text("# "+label+"\n\n"+
            "Differences are second condition minus first. Missing responses are omitted only from affected paired comparisons.\n\n"+
            "Bootstrap units are topics, with all available models retained together. The two across-model comparisons are primary and their p-values use Holm together. Per-model rows of the primary comparisons are exploratory and use Holm within each nine-model family. Secondary and exploratory p-values are unadjusted.\n\n"+
            ("Human agreement was not supplied: these outputs are provisional, not validated final results.\n\n" if gate.provisional else "See reliability.csv for the fields the human check did not validate; comparisons on those fields are marked in their validation column, and the same comparisons on the human-scored answers alone are in *_human_scored.csv.\n\n")+
            "Unavailable inputs or examples:\n"+"\n".join("- "+x for x in unavailable)+"\n")
        print(f"{label}: {len(rows)} answers; {len(files)} result artefacts; {len(unavailable)} unavailable inputs/examples recorded")
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.error(str(error))


if __name__=="__main__":
    main()
