"""Blind adjudication and raw judge agreement (paper section 3.5, steps 2–3).

Usage: python3 -I code/adjudicate.py ITEMS.json RUNDIR OUTDIR [--judging DIR]
       python3 -I code/adjudicate.py ITEMS.json RUNDIR OUTDIR --decisions OUTDIR/decisions.csv
       Add --human-labels CHECK/labels.csv before revealing sampled disagreements.

The sheet has one row per differing meaning field. Select 'judge 1', 'judge 2', or
enter a replacement value (JSON for objects/lists). Quotes are supporting evidence:
different evidence_quotes or exclusion_quote strings alone do not require settling.
Array order is ignored for comparisons of claim lists; all contents still must agree.
These two choices resolve unspecified details and are recorded for author approval.
Missing judgments and missing decisions stop output. No model calls are made.
A valid form from a judge's backup (D66) takes that judge's place for an answer the judge could not score; every
such substitution is listed in judge_substitutions.csv.
"""
import argparse, copy, csv, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring_common import (answer_id, canonical, checked_items, definitions, read_jsonl,
                            safe_outdir, schemas, sha_file, terminal_runs, valid, write_csv, write_jsonl)
from stats_common import agreement

SEED = 20261115
EVIDENCE_FIELDS = {"evidence_quotes", "exclusion_quote"}


def normalized(value):
    """Comparison form: list order ignored; the supporting quote of a claimed check is evidence, not meaning (D66)."""
    if isinstance(value, list):
        return sorted((normalized(v) for v in value), key=canonical)
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if not (k == "quote" and "source" in value)}
    return value


def meaning_fields(schema):
    return [k for k in schema["properties"] if k not in EVIDENCE_FIELDS]


def current_form_version():
    d = definitions()
    return hashlib.sha256(json.dumps([d["FORM_TEST"], d["FORM_SQ"], d["GUIDE_TEST"], d["GUIDE_SQ"]]).encode()).hexdigest()[:12]


def load_judgments(rundir, run_manifest, runs, judging=None):
    path = Path(judging) if judging else Path(rundir) / ("judging-dry" if run_manifest["dry"] else "judging")
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest.get("dry") != run_manifest["dry"] or manifest.get("items_sha256") != run_manifest["items_sha256"]:
        raise ValueError("judging manifest does not match run mode and items")
    if manifest.get("form_version") != current_form_version():
        raise ValueError("judging form version differs from the frozen form")
    judges = manifest["judges"]
    if len(judges) != 2 or len({j["name"] for j in judges}) != 2:
        raise ValueError("exactly two distinct judge configurations are required")
    names = [j["name"] for j in judges]
    configs = {j["name"]: hashlib.sha256(json.dumps([j["id"], j["provider"], manifest["form_version"]]).encode()).hexdigest()[:12]
               for j in judges}
    expected = {answer_id(r): r for r in runs if r["usable"]}
    test_schema, sq_schema = schemas()
    cfg = lambda j: hashlib.sha256(json.dumps([j["id"], j["provider"], manifest["form_version"]]).encode()).hexdigest()[:12]
    backups = {b["name"]: (cfg(b), b["backup_for"]) for b in manifest.get("backups", []) if b["backup_for"] in names}
    forms = {aid: {} for aid in expected}
    backup_forms = {}
    for j in (read_jsonl(path / "judging.jsonl") if expected else []):
        aid, name = j.get("answer_id"), j.get("judge")
        if aid in expected and j.get("valid") and name in backups and j.get("judge_cfg") == backups[name][0] \
                and j.get("replaces") == backups[name][1]:
            r = expected[aid]
            schema = sq_schema if r["test"] == "SQ" else test_schema
            if j.get("answer_key") != [r["model_name"], r["pair_id"], r["test"], r["side"], r["attempt"]] or \
                    not valid(j.get("form"), schema):
                raise ValueError("a backup judgment does not match its answer or the frozen schema")
            backup_forms.setdefault(aid, {})[backups[name][1]] = (name, j["form"])
            continue
        if aid not in expected or not j.get("valid") or j.get("judge_cfg") != configs.get(name):
            continue
        r = expected[aid]
        if j.get("answer_key") != [r["model_name"], r["pair_id"], r["test"], r["side"], r["attempt"]]:
            raise ValueError("judgment key does not match its answer")
        schema = sq_schema if r["test"] == "SQ" else test_schema
        if not valid(j.get("form"), schema):
            raise ValueError("a judgment marked valid does not satisfy the frozen schema")
        if name in forms[aid] and forms[aid][name] != j["form"]:
            raise ValueError("conflicting valid judgments for one answer and judge")
        forms[aid][name] = j["form"]
    substitutions = []
    for aid, slots in sorted(backup_forms.items()):
        for slot, (backup, form) in sorted(slots.items()):
            if slot not in forms[aid]:
                forms[aid][slot] = form
                substitutions.append({"answer_id": aid, "judge": slot, "backup": backup})
    missing = sum(set(values) != set(names) for values in forms.values())
    if missing:
        raise ValueError(f"{missing} usable answers lack two valid current judgments")
    return forms, names, manifest, substitutions


def decision_code(aid, field, values):
    return hashlib.sha256(canonical([SEED, aid, field, values]).encode()).hexdigest()[:12].upper()


def parse_decision(text, schema, values):
    text = text.strip()
    if text.lower() in ("judge 1", "judge 2"):
        value = copy.deepcopy(values[int(text[-1]) - 1])
    elif schema["type"] == "string":
        try:
            value = json.loads(text)
            if not isinstance(value, str): value = text
        except json.JSONDecodeError:
            value = text
    elif schema["type"] == "boolean" and text.lower() in ("yes", "no"):
        value = text.lower() == "yes"
    else:
        try: value = json.loads(text)
        except json.JSONDecodeError as e: raise ValueError("decision needs judge 1, judge 2, or a valid value") from e
    if not valid(value, schema):
        raise ValueError("decision is outside the frozen field's allowed values")
    return value


def evidence(form):
    quotes = list(form.get("evidence_quotes", []))
    if form.get("exclusion_quote"):
        quotes.append(form["exclusion_quote"])
    return list(dict.fromkeys(quotes))


def raw_agreement(runs, forms, names):
    test_schema, sq_schema = schemas()
    rows = []
    for kind, schema in (("review", test_schema), ("status question", sq_schema)):
        selected = [r for r in runs if r["usable"] and (r["test"] == "SQ") == (kind == "status question")]
        for field in meaning_fields(schema):
            left = [normalized(forms[answer_id(r)][names[0]][field]) for r in selected]
            right = [normalized(forms[answer_id(r)][names[1]][field]) for r in selected]
            a = agreement(left, right)
            rows.append({"form": kind, "field": field, "n": a["n"], "agreement": a["agreement"], "kappa": a["kappa"]})
    return rows


def adjudicate(items_path, rundir, outdir, judging=None, decisions=None, human_labels=None, human_map=None):
    items, manifest = checked_items(items_path, rundir)
    runs = terminal_runs(rundir)
    if str(manifest.get("phase", "")).lower() in ("main", "main run") and not manifest.get("dry") and manifest.get("roles") != "aux" and not human_labels:
        raise ValueError("main-run adjudication requires completed --human-labels before judge labels are revealed")
    forms, names, jm, substitutions = load_judgments(rundir, manifest, runs, judging)
    # Validate the independent labels before writing any judge values or agreement.
    if human_labels:
        from human_check import choose_sample, load_labels
        human = load_labels(human_labels, human_map)
        expected_human = {answer_id(r) for r in choose_sample(runs)[0]}
        actual_human = {h["answer_id"] for h in human}
        if actual_human != expected_human or len(human) != len(expected_human):
            raise ValueError("human labels must cover the complete seeded sample for this run")
    out = safe_outdir(outdir)
    identity = {"items_sha256": manifest["items_sha256"], "run_manifest": manifest, "judging_manifest": jm,
                "answers": sorted(forms), "forms_sha256": hashlib.sha256(canonical(forms).encode()).hexdigest()}
    binding = out / "adjudication_manifest.json"
    if binding.exists() and json.loads(binding.read_text()) != identity:
        raise ValueError("adjudication directory is bound to different answers or judgments")
    binding.write_text(json.dumps(identity, indent=2))
    # A rerun with incomplete decisions must not leave an older settled file usable.
    (out / "settled.jsonl").unlink(missing_ok=True)
    prior = {}
    decision_path = Path(decisions) if decisions else out / "decisions.csv"
    if decision_path.exists():
        with decision_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["code"] in prior:
                    raise ValueError("duplicate decision code")
                prior[row["code"]] = ((row.get("decision") or "").strip(), (row.get("reason") or "").strip())
    test_schema, sq_schema = schemas()
    sheet, settled, missing, codes = [], [], 0, set()
    for r in runs:
        aid = answer_id(r)
        if not r["usable"]:
            settled.append({"answer_id": aid, "form": None, "raw_judges": {}, "disagreement_fields": []})
            continue
        schema = sq_schema if r["test"] == "SQ" else test_schema
        left, right = [forms[aid][n] for n in names]
        result = copy.deepcopy(left)
        result["evidence_quotes"] = list(dict.fromkeys(left["evidence_quotes"] + right["evidence_quotes"]))
        side = items[r["pair_id"]][r["side"]]
        differences, reasons = [], {}
        for field in meaning_fields(schema):
            if normalized(left[field]) == normalized(right[field]):
                continue
            differences.append(field)
            values = [left[field], right[field]]
            code = decision_code(aid, field, values)
            codes.add(code)
            decision, reason = prior.get(code, ("", ""))
            sheet.append({"code": code, "question": r["user"], "answer": r["answer"],
                          "target": ("" if r["test"] == "SQ" else f"S{side['target_position']}: ") + side["target"]["title"], "target_conclusion": side["target"].get("conclusion", ""),
                          "field": field, "judge_1_value": values[0], "judge_2_value": values[1],
                          "judge_1_evidence": evidence(left), "judge_2_evidence": evidence(right), "decision": decision, "reason": reason})
            if decision:
                if not reason:
                    raise ValueError(f"{code}: a reason is required for every settled disagreement")
                result[field] = parse_decision(decision, schema["properties"][field], values)
                reasons[field] = reason
            else:
                missing += 1
        if "excluded_due_to_retraction_claim" in result:
            result["exclusion_quote"] = " | ".join(dict.fromkeys(x for x in (left["exclusion_quote"], right["exclusion_quote"]) if x)) \
                if result["excluded_due_to_retraction_claim"] else ""
        if not valid(result, schema):
            raise ValueError("settled form does not satisfy frozen schema")
        settled.append({"answer_id": aid, "form": result, "raw_judges": forms[aid], "disagreement_fields": differences,
                        "adjudication_reasons": reasons})
    if set(prior) - codes:
        raise ValueError("decision sheet contains unknown or stale codes")
    write_csv(out / "decisions.csv", sorted(sheet, key=lambda x: x["code"]),
              ["code", "question", "answer", "target", "target_conclusion", "field", "judge_1_value", "judge_2_value",
               "judge_1_evidence", "judge_2_evidence", "decision", "reason"])
    write_csv(out / "judges_agreement.csv", raw_agreement(runs, forms, names))
    write_csv(out / "judge_substitutions.csv", substitutions, ["answer_id", "judge", "backup"])
    (out / "instructions.txt").write_text("Fill decision with judge 1, judge 2, or a replacement field value, and give a reason.\n"
        "Keep quotations as evidence; judge the answer's meaning, not the paper's true status.\n"
        "Complete the separately sampled human labels before opening this sheet.\n"
        "The human-label gate is mandatory for live main runs; pilot, dry and auxiliary runs can proceed without it.\n")
    if missing:
        (out / "settled.jsonl").unlink(missing_ok=True)
        raise ValueError(f"{missing} field decisions remain; complete {out / 'decisions.csv'}")
    write_jsonl(out / "settled.jsonl", settled)
    return {"answers": len(settled), "disagreements": len(sheet), "backup_substitutions": len(substitutions)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items"); ap.add_argument("rundir"); ap.add_argument("outdir")
    ap.add_argument("--judging"); ap.add_argument("--decisions"); ap.add_argument("--human-labels"); ap.add_argument("--human-map")
    a = ap.parse_args()
    try:
        result = adjudicate(a.items, a.rundir, a.outdir, a.judging, a.decisions, a.human_labels, a.human_map)
    except (ValueError, KeyError, FileNotFoundError) as e:
        raise SystemExit(str(e))
    print("Settled answers:", result["answers"], "| differing fields:", result["disagreements"])


if __name__ == "__main__":
    main()
