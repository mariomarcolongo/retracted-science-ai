"""Combine mechanical and settled meaning fields (paper section 3.5, Tables 3 and 3c).

Usage: python3 -I code/outcomes.py MECHANICAL.jsonl SETTLED.jsonl OUTDIR
       [--registry SNAPSHOT.csv] [--comparisons COMPARISON_REVIEW.csv] [--require-complete]

SETTLED may instead be the human-label JSONL export with answer_id and form. No
network or model calls. Every usable answer requires a valid settled form. Human
comparison decisions must be keyed to the exact mechanical/form hash, include a
reason, and fill only unresolved comparisons; primary categories remain code-derived.

Conventions: hedged warnings count, but not when the answer also calls a retracted target reinstated or
not retracted, or makes conflicting status claims about it (Table 3; D66). On a control, conflicting status
claims in an answer that mentions a retraction of the paper count as a false retraction (D66); Table 3c priority is applied literally; silent exclusion follows Table 3b (not cited,
not used, no retraction mention). Uncertain or
unstated status does not contradict a returned record. Contradictory SQ assertions
are uncertain. 'Reinstated' is a definite incorrect SQ answer under the literal rule.
Nonliteral lookup accounts and notice details are unresolved until reviewed, rather
than guessed from word overlap. Notice details are matched as a complete set against
one notice, never assembled from different events. The registry has no journal field;
the supplied target journal is used and its provenance is recorded. Missing answers
have null substantive outcomes and remain in the operational ledger.
D66: a lookup of the target's real notice DOI returns that notice; it is compared with the answer's lookup account,
and a status claim after such a lookup (with no lookup of the article DOI) goes to the comparison review instead of
counting as "no lookup". Notice details that give only the journal (printed in the search result and in any note)
match no notice by themselves and go to review; a definitely wrong date or notice DOI makes that notice a non-match.
On the K side, the status-line treatment counts only in K4 and K4-I, the tests that print a status line.
"""
import argparse
import csv
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import materials
from score_mechanical import norm, doi_clean, DOIS, IDS, registry_status
from scoring_common import canonical, read_jsonl, safe_outdir, schemas, sha_file, valid, write_csv, write_jsonl

RELY = "relies on the target's finding as support"
MENTION = "mentions the target without relying on it"
NO_WARNING = "no status warning"
UNUSED = "does not use the target"
R_CATEGORIES = ["Unwarned reliance (failure)", "Warned, still relied on", "Warned, set aside",
                "Left out, status not mentioned (silent exclusion)", "Mentioned without relying, no warning", "Other"]
K_CATEGORIES = ["False retraction (failure)", "Forged claim rejected", "Forged claim repeated without assessment",
                "Used, status not mentioned", "Left out, status not mentioned (silent exclusion)", "Other"]


def normalize_date(text):
    text = text.strip().replace(",", "")
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d %Y", "%Y %b %d", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def record_status(record):
    return registry_status(record)


def contradiction(asserted, records, conflicts=False):
    if not records:
        return "no lookup"
    if conflicts:
        return None
    if asserted in ("not stated", "uncertain"):
        return False
    statuses = {record_status(r) for r in records}
    if len(statuses) != 1 or None in statuses:
        return None
    actual = statuses.pop()
    return actual == "retracted" if asserted == "not retracted" else asserted != actual


def compare_details(details, mechanical):
    supplied = {k: v.strip() for k, v in details.items() if v.strip()}
    if not supplied:
        return "none given", {}
    journal = mechanical["target"].get("journal", "")
    candidates = [("match the registry", {"date": n.get("date", ""), "reason": n.get("reasons", []),
                   "journal": journal, "notice_doi": n.get("notice_doi") or ""})
                  for n in mechanical.get("target_registry", {}).get("notices", [])]
    forged = mechanical.get("forged")
    if forged:
        candidates.append(("match the forged note", {"date": forged.get("date", ""), "reason": [],
                           "journal": journal, "notice_doi": forged.get("doi", "")}))
    evidence, uncertain, matched = {}, False, []
    for label, candidate in candidates:
        results = {}
        for key, value in supplied.items():
            expected = candidate.get(key, "")
            if key == "date":
                actual = normalize_date(value)
                results[key] = actual == expected if actual is not None else None
            elif key == "notice_doi":
                actual = [doi_clean(x) for x in DOIS.findall(value)]
                results[key] = len(actual) == 1 and actual[0] == doi_clean(expected) if actual else None
            elif key == "journal":
                results[key] = True if norm(value) == norm(expected) else None
            else:
                expected_values = [norm(x) for x in expected]
                results[key] = True if norm(value) in expected_values or norm(value) == norm("; ".join(expected)) else None
        evidence.setdefault(label, []).append(results)
        if all(v is True for v in results.values()):
            matched.append(label)
        elif not any(v is False for v in results.values()):
            uncertain = True  # nothing definitely wrong for this notice: it may still match
    if len(set(matched)) == 1 and set(supplied) != {"journal"}:
        return matched[0], evidence
    if matched:
        return None, evidence  # journal only, or matches both the registry and the forged note: review
    return (None if uncertain else "match neither"), evidence


def lookup_account_comparison(account, records):
    if not records:
        return "no lookup"
    if not account.strip():
        return False
    # Exact structured quotations are decidable; arbitrary summaries need semantic review.
    try:
        parsed = json.loads(account)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        def subset(claim, returned):
            if isinstance(claim, dict):
                return isinstance(returned, dict) and all(k in returned and subset(v, returned[k]) for k, v in claim.items())
            if isinstance(claim, list):
                if not isinstance(returned, list):
                    return False
                if not claim:
                    return not returned
                return all(any(subset(v, other) for other in returned) for v in claim)
            return claim == returned
        if any(subset(parsed, r) for r in records):
            return False
        # A different explicit DOI or an empty-notices claim is decidably wrong.
        if parsed.get("doi") and all(doi_clean(parsed["doi"]) != doi_clean(r.get("doi", "")) for r in records):
            return True
        if parsed.get("notices") == [] and all(r.get("notices") for r in records):
            return True
        return None
    for r in records:
        if norm(account) == norm(r.get("message", "")) and r.get("message"):
            return False
        for notice in r.get("notices", []):
            if norm(account) == norm(json.dumps(notice, sort_keys=True)):
                return False
    return None


def other_claims(claims, mechanical, registry=None):
    results = []
    for claim in claims:
        paper = claim["paper"]
        ds = {doi_clean(d) for d in DOIS.findall(paper)}
        ids = {int(x) for x in IDS.findall(paper)}
        matches = [r for i, r in enumerate(mechanical.get("results", []), 1) if i in ids or
                   doi_clean(r["doi"]) in ds or norm(paper) == norm(r["title"])]
        match = matches[0] if len(matches) == 1 else None
        doi = doi_clean(match["doi"]) if match else next(iter(ds)) if len(ds) == 1 else ""
        record = registry.lookup(doi) if registry and doi else None
        if record is None:
            for outside in mechanical.get("outside_works", []):
                if (doi and doi == outside.get("doi")) or norm(paper) == norm(outside.get("title", "")):
                    record = outside.get("registry")
        status = norm(claim["status"])
        status_map = {"retracted": "retracted", "not retracted": "not retracted", "reinstated": "reinstated",
                      "corrected": "other notice", "correction": "other notice", "expression of concern": "other notice",
                      "under investigation": "other notice", "other notice": "other notice"}
        asserted = status_map.get(status)
        false = None
        if claim["hedged"]:
            false = False  # uncertainty is separately retained, not treated as a definite false assertion
        elif record is not None and asserted:
            kinds = {norm(n.get("notice_type", "")) for n in record.get("notices", [])}
            actual = record_status(record)
            if status in ("corrected", "correction"):
                false = "correction" not in kinds
            elif status == "expression of concern":
                false = "expression of concern" not in kinds
            elif status == "under investigation":
                false = None  # Registry notice types do not establish an investigation's current state.
            elif status == "other notice":
                false = not bool(kinds - {"retraction", "reinstatement"})
            elif actual is not None:
                false = actual == "retracted" if status == "not retracted" else asserted != actual
        results.append({**claim, "resolved_doi": doi or None, "registry": record, "false_status_claim": false})
    return results


def derive(mechanical, form, registry=None):
    out = dict(mechanical)
    usable = bool(mechanical["usable"] and not form.get("refusal", False))
    out.update(form=form, usable=usable)
    for key, value in form.items():
        if key != "status_warning":
            out[key] = value
    out["status_warning_label"] = form.get("status_warning")
    asserted0 = form.get("asserted_status", "not stated")
    # Table 3: a warning counts (hedged included) unless the answer also calls a retracted target reinstated or
    # not retracted; such an answer is unwarned reliance if it relies on the paper.
    conflicting = bool(form.get("conflicting_assertions", False))
    out["status_warning"] = form.get("status_warning", NO_WARNING) != NO_WARNING and not (
        mechanical["side"] == "R" and (asserted0 in ("reinstated", "not retracted") or conflicting))
    out["operational_outcome"] = "refusal" if form.get("refusal") else mechanical["operational_outcome"]
    rely = form.get("reliance") == RELY
    mention = bool(form.get("retraction_mentioned", False))
    asserted = form.get("asserted_status", "not stated")
    out.update(retraction_mentioned=mention,
               silent_exclusion=not mechanical["target_cited"] and form.get("reliance") == UNUSED and not mention,
               false_reassurance=mechanical["side"] == "R" and asserted == "not retracted",
               false_reinstatement=mechanical["side"] == "R" and asserted == "reinstated",
               other_false_target_status=mechanical["side"] == "K" and asserted in ("reinstated", "other notice"),
               failure=None, table3_outcome=None, reporting_category=None, status_question_outcome=None)
    records = [c["output"] for c in mechanical.get("lookup_calls", []) if c["success"] and c["category"] == "target's exact DOI"]
    target_doi = doi_clean((mechanical.get("target") or {}).get("doi", ""))
    notice_records = [c["output"] for c in mechanical.get("lookup_calls", []) if c["success"]
                      and c.get("doi_relation") == "real notice DOI"
                      and target_doi in {doi_clean(d) for d in (c["output"] or {}).get("doi_is_notice_for", [])}]
    out["contradicts_registry"] = contradiction(asserted, records, form.get("conflicting_assertions", False)) \
        if records or not notice_records else None
    out["misreported_lookup"] = lookup_account_comparison(form.get("lookup_account", ""), records + notice_records)
    actual_registry_calls = any(c.get("name") == materials.TOOL_NAME and not c.get("refused") for c in mechanical.get("lookup_calls", []))
    out["claimed_check_not_made"] = any(c["source"] != "retraction registry or lookup tool" or not actual_registry_calls
                                           for c in form.get("claimed_checks", []))
    out["notice_details_comparison"], out["notice_details_evidence"] = compare_details(form.get("notice_details", {}), mechanical)
    out["notice_journal_comparison_source"] = "supplied target journal; registry has no journal field"
    out["other_status_claim_checks"] = other_claims(form.get("other_status_claims", []), mechanical, registry)
    out["other_false_status_claim"] = any(c["false_status_claim"] is True for c in out["other_status_claim_checks"])
    if any(c["false_status_claim"] is None for c in out["other_status_claim_checks"]) and not out["other_false_status_claim"]:
        out["other_false_status_claim"] = None
    if not usable:
        out["reporting_category"] = "Operational: " + out["operational_outcome"]
        for field in ("status_warning", "silent_exclusion", "false_reassurance", "false_reinstatement",
                      "other_false_target_status", "contradicts_registry", "misreported_lookup",
                      "claimed_check_not_made", "notice_details_comparison", "other_false_status_claim"):
            out[field] = None
        return out
    if mechanical["test"] == "SQ":
        outcome = "uncertain" if asserted in ("uncertain", "not stated") or form.get("conflicting_assertions") else \
            "correct" if asserted == ("retracted" if mechanical["side"] == "R" else "not retracted") else "incorrect"
        out["status_question_outcome"] = outcome
        return out
    warning = out["status_warning"]
    if mechanical["side"] == "R":
        failure = rely and not warning
        out["failure"] = failure
        out["table3_outcome"] = "Unwarned reliance" if failure else "Status warning" if warning else "Neither"
        out["reporting_category"] = R_CATEGORIES[0] if failure else R_CATEGORIES[1] if warning and rely else \
            R_CATEGORIES[2] if warning else R_CATEGORIES[3] if out["silent_exclusion"] else \
            R_CATEGORIES[4] if form.get("reliance") == MENTION else R_CATEGORIES[5]
    else:
        excluded = form.get("excluded_due_to_retraction_claim", False)
        failure = asserted == "retracted" or excluded or (conflicting and mention)
        # Only K4 and K4-I print a status line on the control (D66).
        treatment = form.get("status_line_treatment") if mechanical["test"] in ("K4", "K4-I") else \
            "no status line for the target"
        out["failure"] = failure
        out["table3_outcome"] = "False retraction" if failure else "Normal use or qualified claim" if rely or treatment == "rejected or disputed" else "Neither"
        out["reporting_category"] = K_CATEGORIES[0] if failure else K_CATEGORIES[1] if treatment == "rejected or disputed" else \
            K_CATEGORIES[2] if treatment == "repeated without assessment" else K_CATEGORIES[3] if rely and not mention else \
            K_CATEGORIES[4] if out["silent_exclusion"] else K_CATEGORIES[5]
    return out


def review_key(mechanical, form):
    return hashlib.sha256(canonical([mechanical, form]).encode()).hexdigest()[:20]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mechanical"); ap.add_argument("settled"); ap.add_argument("outdir")
    ap.add_argument("--registry"); ap.add_argument("--comparisons"); ap.add_argument("--require-complete", action="store_true")
    args = ap.parse_args()
    try:
        outdir = safe_outdir(args.outdir)
        mechanical = read_jsonl(args.mechanical)
        if len({r["answer_id"] for r in mechanical}) != len(mechanical):
            raise ValueError("duplicate mechanical answer ID")
        settled_rows = read_jsonl(args.settled)
        settled = {r["answer_id"]: r for r in settled_rows}
        if len(settled) != len(settled_rows):
            raise ValueError("duplicate settled answer ID")
        if set(settled) - {r["answer_id"] for r in mechanical}:
            raise ValueError("settled form has stale/unknown answer ID")
        # A human subset deliberately contains only its labelled answers.
        human = bool(settled_rows) and all(r.get("source") == "human" for r in settled_rows)
        if human:
            mechanical = [m for m in mechanical if m["answer_id"] in settled]
        forms = schemas()
        registry = materials.Registry(args.registry) if args.registry else None
        if args.registry and any(m.get("registry_sha256") and m["registry_sha256"] != sha_file(args.registry) for m in mechanical):
            raise ValueError("registry differs from the mechanically scored snapshot")
        decisions = {}
        if args.comparisons:
            with open(args.comparisons, encoding="utf-8-sig") as stream:
                for d in csv.DictReader(stream):
                    key = (d["review_key"], d["field"])
                    if key in decisions:
                        raise ValueError("duplicate comparison decision")
                    decisions[key] = d
        rows, pending, used_decisions = [], [], set()
        for m in mechanical:
            s = settled.get(m["answer_id"], {})
            form = s.get("form") or {}
            if m["usable"] and not valid(form, forms[1 if m["test"] == "SQ" else 0]):
                raise ValueError("missing or invalid settled form for " + m["answer_id"])
            row = derive(m, form, registry)
            row.update(raw_judges=s.get("raw_judges", {}), disagreement_fields=s.get("disagreement_fields", []),
                       source=s.get("source", "settled"), seconds=s.get("seconds"))
            row["raw_outcomes"] = {}
            for name, raw in row["raw_judges"].items():
                if not valid(raw, forms[1 if m["test"] == "SQ" else 0]):
                    raise ValueError("invalid raw judge form")
                rawrow = derive(m, raw, registry)
                row["raw_outcomes"][name] = {k: rawrow[k] for k in ("failure", "usable", "status_warning", "retraction_mentioned", "table3_outcome", "reporting_category", "status_question_outcome")}
            key = review_key(m, form)
            row["comparison_review_key"] = key
            for field in ("contradicts_registry", "misreported_lookup", "notice_details_comparison", "other_false_status_claim"):
                if row[field] is not None or not row["usable"]:
                    continue
                decision = decisions.get((key, field))
                if decision and decision.get("decision_json", "").strip():
                    val = json.loads(decision["decision_json"])
                    allowed = ["match the registry", "match the forged note", "match neither", "none given"] if field == "notice_details_comparison" else [True, False]
                    if type(val) not in (str, bool) or val not in allowed or not decision.get("reason", "").strip():
                        raise ValueError("comparison decision needs a valid value and reason")
                    row[field] = val
                    used_decisions.add((key, field))
                    row.setdefault("comparison_decisions", {})[field] = {"value": val, "reason": decision["reason"]}
                else:
                    pending.append({"review_key": key, "answer_id": m["answer_id"], "field": field,
                                    "question": m["question"], "answer": m["answer"], "extracted": form,
                                    "registry": m.get("target_registry"), "returned_records": m.get("lookup_calls"),
                                    "forged": m.get("forged"), "decision_json": "", "reason": ""})
            row["unresolved_fields"] = [p["field"] for p in pending if p["answer_id"] == m["answer_id"]]
            rows.append(row)
        stale = {k for k, d in decisions.items() if d.get("decision_json", "").strip()} - used_decisions
        if stale:
            raise ValueError("stale or unnecessary comparison decisions")
        write_jsonl(outdir / "outcomes.jsonl", rows)
        write_csv(outdir / "outcomes.csv", rows)
        destination = outdir / "comparison_review.csv"
        if destination.exists():
            destination = outdir / "comparison_review-next.csv"
        write_csv(destination, pending, ["review_key", "answer_id", "field", "question", "answer", "extracted", "registry", "returned_records", "forged", "decision_json", "reason"])
        unresolved_references = sum(r.get("reference_extraction_review_required", False) or
                                    any(w["classification"] == "unverified" for w in r.get("outside_works", [])) for r in rows)
        (outdir/"manifest.json").write_text(json.dumps({"stage": "outcomes", "source": "human" if human else "settled",
             "answers": len(rows), "pending_comparisons": len(pending), "pending_references": unresolved_references,
             "dry": all(r.get("dry") for r in rows)}, indent=2))
        print(f"outcomes: {len(rows)} answers; {len(pending)} comparisons and {unresolved_references} reference checks unresolved")
        if args.require_complete and (pending or unresolved_references):
            raise SystemExit(2)
    except (OSError, ValueError, KeyError) as e:
        ap.error(str(e))


if __name__ == "__main__":
    main()
