"""Mechanical scoring and reference checks (paper section 3.5, Table 3b, step 1).

Usage: python3 -I code/score_mechanical.py ITEMS.json RUNDIR OUTDIR --registry SNAPSHOT.csv
       [--offline | --online] [--cache DIR] [--references REVIEW.csv]

Offline is the default. Online uses only public Crossref and DOI-handle GET requests,
with User-Agent research-script, never a model. Cached misses and network failures
are distinct from not-found references. REVIEW.csv accepts answer_id, complete=yes,
references_json (list of {doi,title}) and optional citation_errors_json. The generated
reference_review.csv lists only usable answers in which code finds a DOI or a quoted title outside the five
results (D64); the author confirms the list for those. Works cited only by author and year are not detected, a
stated limitation. Completeness is never inferred from a search.

Conventions not fully specified in the paper: mixed calls take the most informative
successful category (target, other supplied, other DOI), with failures also recorded.
Altered means edit distance at most two from a supplied DOI. Exact normalized title
matching is conservative; nonliteral titles require review. A DOI without a title
cannot satisfy the paper's DOI-and-title match rule. Status words are flags only.
Result IDs (D66): an ID in square brackets ("[S2]", "[S1, S3]") always counts as a citation; a bare "S2" counts only
if "S2" does not occur as a word in that item's own question text (pair 73869 is about the S2 subunit). The author
check uses the first three authors, as the question prints them. A line whose citation cannot be matched
unambiguously leaves citation_errors unknown and sends the answer to the author's review, like an outside reference.
"""
import argparse
import csv
import datetime
import hashlib
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import materials
from scoring_common import answer_id, checked_items, read_jsonl, safe_outdir, safe_path, sha_file, terminal_runs, write_csv, write_jsonl

ANSWER_WORDS = re.compile(r"retract\w*|withdrawn|withdrawal|reinstat\w*|expression\s+of\s+concern|notice", re.I)
REASON_WORDS = re.compile(r"retract\w*|reinstat\w*|expression\s+of\s+concern", re.I)
DOIS = re.compile(r"10\.\d{4,9}/[^\s<>\"\[\]]+", re.I)
IDS = re.compile(r"\bS([1-9]\d*)\b")
BRACKETS = re.compile(r"\[([^\[\]]{1,60})\]")


def result_ids(text, reserved=frozenset()):
    """Result numbers cited in text: any S-number inside square brackets, and bare S-numbers not in reserved."""
    bracketed = {int(x) for b in BRACKETS.findall(text) for x in IDS.findall(b)}
    bare = {int(x) for x in IDS.findall(BRACKETS.sub(" ", text))}
    return bracketed | (bare - set(reserved))


def reserved_ids(question):
    """S-numbers that occur as bare words in the question text (outside the "[S1]" result labels)."""
    return frozenset(int(x) for x in IDS.findall(BRACKETS.sub(" ", question or "")))


def norm(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text or "").casefold()))


def doi_clean(text):
    value = materials.Registry.norm(text).rstrip(".,;:")
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1]
    return value


def registry_status(record):
    """Current snapshot status; later corrections do not undo reinstatement.

    A same-date retraction/reinstatement conflict has no recoverable event order
    in the date-only registry and is left unresolved for review.
    """
    if record.get("doi_is_notice_for"):
        return "not retracted"  # the DOI is a notice itself, not a retracted article
    notices = record.get("notices", [])
    changes = [n for n in notices if n.get("notice_type", "").casefold() in ("retraction", "reinstatement")]
    if not changes:
        return "other notice" if notices else "not retracted"
    if any(not n.get("date") for n in changes):
        return None
    latest = max(n["date"] for n in changes)
    kinds = {n["notice_type"].casefold() for n in changes if n["date"] == latest}
    if len(kinds) != 1:
        return None
    return "retracted" if kinds.pop() == "retraction" else "reinstated"


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(row[-1]+1, prev[j]+1, prev[j-1]+(x != y)))
        prev = row
    return prev[-1]


def reasoning(exchanges, api):
    """Return only visible reasoning text; do not scan encrypted data, IDs or signatures."""
    texts, paths = [], set()
    for e in exchanges:
        r = e.get("response") or {}
        if api == "responses":
            for o in r.get("output") or []:
                if o.get("type") != "reasoning":
                    continue
                for key in ("summary", "content"):
                    for v in o.get(key) or []:
                        if isinstance(v, dict) and isinstance(v.get("text"), str) and v["text"].strip():
                            texts.append(v["text"]); paths.add(f"output[type=reasoning].{key}[].text")
                if isinstance(o.get("text"), str) and o["text"].strip():
                    texts.append(o["text"]); paths.add("output[type=reasoning].text")
        else:
            for ch in r.get("choices") or []:
                msg = ch.get("message") or {}
                for key in ("reasoning", "reasoning_content"):
                    if isinstance(msg.get(key), str) and msg[key].strip():
                        texts.append(msg[key]); paths.add("choices[].message." + key)
                for v in msg.get("reasoning_details") or []:
                    if v.get("type") == "reasoning.encrypted":
                        continue
                    for key in ("text", "summary"):
                        if isinstance(v.get(key), str) and v[key].strip():
                            texts.append(v[key]); paths.add("choices[].message.reasoning_details[]." + key)
    return "\n".join(texts), sorted(paths)


def lookup_fields(calls, side):
    target = doi_clean(side["target"]["doi"])
    supplied = {doi_clean(r["doi"]) for r in side.get("results", [])} | {target}
    # Notice DOIs keep the "altered or unrelated" category of Table 3b and are reported as their own subtypes.
    real_notice = doi_clean(side["target"].get("retraction_doi") or "")
    forged_notice = doi_clean((side.get("forged") or {}).get("doi") or "")
    details = []
    for call in calls:
        d = doi_clean(call.get("doi") or "")
        out = call.get("output")
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except ValueError:
                out = {"error": out}
        success = bool(call.get("valid")) and not call.get("refused") and isinstance(out, dict) and "error" not in out
        match = "target's exact DOI" if d == target else "other supplied DOI only" if d in supplied else "altered or unrelated DOI only"
        subtype = "supplied" if d in supplied else \
            "real notice DOI" if d and d == real_notice else "forged notice DOI" if d and d == forged_notice else \
            "altered" if any(edit_distance(d, s) <= 2 for s in supplied) else "unrelated"
        details.append({"doi": d, "success": success, "category": match, "doi_relation": subtype, "output": out,
                        "refused": bool(call.get("refused")), "call_id": call.get("call_id"),
                        "name": call.get("name", materials.TOOL_NAME if call.get("valid") else None)})
    successes = [d for d in details if d["success"]]
    category = "none"
    if details:
        category = next((k for k in ("target's exact DOI", "other supplied DOI only", "altered or unrelated DOI only")
                         if any(d["category"] == k for d in successes)), "failed (tool error)")
    return {"registry_lookup": category, "lookup_calls": details, "lookup_failed": any(not d["success"] for d in details),
            "target_lookup_success": any(d["success"] and d["category"] == "target's exact DOI" for d in details)}


def citation_fields(text, side, question=None):
    reserved = reserved_ids(question if question is not None else side_text(side))
    ids = result_ids(text, reserved)
    text_norm = " " + norm(text) + " "
    found = set()
    results = side.get("results", [])
    doi_mentions = {doi_clean(d) for d in DOIS.findall(text)}
    for i, r in enumerate(results, 1):
        if i in ids or doi_clean(r["doi"]) in doi_mentions or (r.get("title") and " " + norm(r["title"]) + " " in text_norm):
            found.add(i)
    errors, ambiguous = [], []
    for line in text.splitlines():
        cited = result_ids(line, reserved)
        if not cited:
            continue
        line_dois = {doi_clean(d) for d in DOIS.findall(line)}
        line_norm = " " + norm(line) + " "
        meta = {i for i, r in enumerate(results, 1) if doi_clean(r["doi"]) in line_dois
                or (r.get("title") and " " + norm(r["title"]) + " " in line_norm)
                or (r.get("authors") and any(norm(a) for a in r["authors"][:3]) and
                    all(" " + norm(a) + " " in line_norm for a in r["authors"][:3] if norm(a)))}
        notice_context = bool(re.search(r"notice|retract|reinstat|expression\s+of\s+concern", line, re.I))
        explicit_doi = bool(re.search(r"\bdoi\s*:|\[S\d+\]\s*(?:https?://(?:dx\.)?doi\.org/)?10\.", line, re.I))
        expected_dois = {doi_clean(results[i-1]["doi"]) for i in cited if 1 <= i <= len(results)}
        if side.get("target_position") in cited:  # the target's own notice DOIs, as printed in its result
            expected_dois |= {doi_clean(x) for x in (side["target"].get("retraction_doi"),
                                                     (side.get("forged") or {}).get("doi")) if x}
        conflicting_doi = bool(line_dois - expected_dois)
        if len(cited) == 1 and conflicting_doi and notice_context:
            ambiguous.append(line)
            continue
        if len(cited) == 1 and conflicting_doi and explicit_doi:
            errors.append(line)
            continue
        if len(cited) == 1 and meta and not cited & meta:
            errors.append(line)
        elif meta - cited:
            ambiguous.append(line)
    target = side["target"]
    target_cited = side.get("target_position") in found or doi_clean(target["doi"]) in doi_mentions or (
        bool(target.get("title")) and " " + norm(target["title"]) + " " in text_norm)
    return {"target_cited": bool(target_cited), "any_supplied_result_cited": bool(found),
            "supplied_results_cited": sorted(found), "citation_errors": True if errors else None if ambiguous else False,
            "citation_error_evidence": errors,
            "citation_ambiguities": ambiguous, "unknown_result_ids": sorted(ids - set(range(1, len(results)+1)))}


class ReferenceCache:
    def __init__(self, directory, offline=True):
        self.directory = safe_outdir(directory)
        self.offline = offline

    def fetch(self, kind, value):
        key = hashlib.sha256((kind + ":" + value).encode()).hexdigest()
        path = safe_path(self.directory / (key + ".json"))
        if path.exists():
            return json.loads(path.read_text())
        if self.offline:
            return {"state": "unverified", "reason": "offline cache miss"}
        if kind == "doi":
            url = "https://api.crossref.org/works/" + urllib.parse.quote(value, safe="")
        elif kind == "handle":
            url = "https://doi.org/api/handles/" + urllib.parse.quote(value, safe="/")
        else:
            url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": value, "rows": 5, "select": "DOI,title"})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script"}), timeout=30) as response:
                payload = json.load(response)
            if kind == "handle":
                code = payload.get("responseCode")
                if code == 1:
                    result = {"state": "ok", "registered": True, "response_code": code}
                elif code == 100:
                    result = {"state": "not found", "registered": False, "response_code": code}
                else:
                    result = {"state": "unverified", "reason": "unresolved handle response", "response_code": code}
            else:
                works = [payload["message"]] if kind == "doi" else payload["message"].get("items", [])
                result = {"state": "ok", "works": [{"doi": w.get("DOI", ""), "titles": w.get("title", [])} for w in works]}
        except urllib.error.HTTPError as error:
            if kind == "handle":
                try:
                    code = json.loads(error.read()).get("responseCode")
                except (ValueError, AttributeError):
                    code = None
                result = {"state": "not found" if code == 100 else "unverified", "response_code": code,
                          "reason": f"HTTP {error.code}"}
                if code == 100:
                    result["registered"] = False
            else:
                result = {"state": "not found" if error.code == 404 else "unverified", "reason": f"HTTP {error.code}"}
        except (OSError, ValueError, KeyError) as error:
            return {"state": "unverified", "reason": type(error).__name__}
        result.update(url=url, checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        # Do not permanently cache transient failures.
        if result["state"] != "unverified":
            path.write_text(json.dumps(result, ensure_ascii=False))
        return result

    def check(self, reference, registry):
        doi, title = doi_clean(reference.get("doi", "")), reference.get("title", "").strip()
        evidence = self.fetch("doi" if doi else "title", doi or title) if doi or title else {"state": "unverified", "reason": "no identifier"}
        result = {"doi": doi, "title": title, "classification": "unverified", "crossref": evidence}
        if evidence["state"] == "not found":
            result["classification"] = "not found"
            return result
        if evidence["state"] != "ok":
            return result
        matches = [w for w in evidence.get("works", []) if title and any(norm(title) == norm(t) for t in w["titles"])
                   and (not doi or doi_clean(w["doi"]) == doi)]
        if not title:
            result["reason"] = "title required for DOI-and-title match"
        elif not matches:
            result.update(classification="not found", reason="no exact normalized title match; review paraphrases")
        else:
            doi = doi_clean(matches[0]["doi"])
            handle = self.fetch("handle", doi)
            result.update(doi=doi, handle=handle)
            if handle["state"] == "not found" or handle.get("registered") is False:
                result["classification"] = "not found"
            elif handle["state"] == "ok":
                record = registry.lookup(doi)
                status = registry_status(record)
                result.update(classification="unverified" if status is None else
                              "real and retracted" if status == "retracted" else "real", registry=record)
                if status is None:
                    result["reason"] = "registry event ordering is ambiguous"
        return result


def side_text(side):
    """The item's own text (topic, titles, abstracts), used when the question as sent is not available."""
    parts = [side.get("topic", ""), side["target"].get("title", ""), side["target"].get("abstract", "")]
    for r in side.get("results", []):
        parts += [r.get("title", ""), r.get("abstract", ""), r.get("journal", "")]
    return "\n".join(p for p in parts if isinstance(p, str))


def outside_candidates(text, side, question_text=None):
    supplied = {doi_clean(r["doi"]) for r in side.get("results", [])} | {doi_clean(side["target"]["doi"])}
    notices = {doi_clean(side.get("forged", {}).get("doi", "")), doi_clean(side["target"].get("retraction_doi", ""))}
    refs = []
    question = " " + norm(question_text if question_text is not None else side_text(side)) + " "
    for line in text.splitlines():
        # A quoted phrase that occurs in the question itself (a status line, a phrase from an abstract) is not an
        # outside title (D66).
        titles = [t for t in re.findall(r'[“"]([^”"]{12,})[”"]', line) if " " + norm(t) + " " not in question]
        attached = set()
        for d in DOIS.findall(line):
            d = doi_clean(d)
            if d not in supplied | notices:
                refs.append({"doi": d, "title": titles[0] if titles else ""})
                attached.add(titles[0] if titles else "")
        # Quoted titles that match no supplied result are flagged on every line, including lines that also cite a
        # supplied DOI or ID: flagging sends the answer to the author's review (D64), so the check errs toward it.
        for title in titles:
            if title not in attached and not any(norm(title) == norm(r["title"]) for r in side.get("results", [])):
                refs.append({"doi": "", "title": title})
    return list({json.dumps(r, sort_keys=True): r for r in refs}.values())


def score(r, side, registry, cache, reviewed=None):
    text = r.get("answer") or ""
    reasoning_text, paths = reasoning(r.get("exchanges", []), r["api"])
    op = r.get("outcome", "")
    operational = "refusal" if r.get("refusal") else "API error" if op == "API error" else \
        "cut off at the token limit" if "cut off" in op else "complete" if r.get("usable") else "empty"
    fields = citation_fields(text, side, r.get("user"))
    references = outside_candidates(text, side, r.get("user")) if r["test"] != "SQ" else []
    complete = bool(reviewed and reviewed.get("complete", "").lower() == "yes")
    if complete:
        references = json.loads(reviewed["references_json"])
        if not isinstance(references, list) or any(not isinstance(x, dict) or set(x) - {"doi", "title"} for x in references):
            raise ValueError("references_json must be a list of doi/title objects")
        if fields["citation_ambiguities"] and not (reviewed.get("citation_errors_json") or "").strip():
            raise ValueError("an answer with unclear citations needs citation_errors_json ([] if none is an error)")
        if reviewed.get("citation_errors_json"):
            fields["citation_error_evidence"] = json.loads(reviewed["citation_errors_json"])
            if not isinstance(fields["citation_error_evidence"], list):
                raise ValueError("citation_errors_json must be a list")
            fields["citation_errors"] = bool(fields["citation_error_evidence"])
            fields["citation_ambiguities"] = []
    checked = [cache.check(ref, registry) for ref in references]
    # Restricted supplied-ID answers with no other bibliographic markers need no outside extraction.
    suspicious = bool(references or fields["citation_ambiguities"] or re.search(r"\b(?:19|20)\d{2}\b|https?://|\bet al\b|references\s*:", text, re.I))
    # D64: answers where code finds an outside DOI or quoted title go to the author's review sheet; D66: so do
    # answers with a citation code cannot match unambiguously.
    needs_review = r["test"] != "SQ" and bool(r.get("usable")) and not complete and \
        bool(references or fields["citation_ambiguities"])
    aid = answer_id(r)
    return {"answer_id": aid, "phase": r["phase"], "model_name": r["model_name"], "model_id": r["model_id"],
            "provider": r["provider_requested"], "api": r["api"], "pair_id": r["pair_id"], "test": r["test"], "side": r["side"],
            "usable": bool(r["usable"]), "operational_outcome": operational, "original_operational_outcome": op,
            "stop_reason": r.get("stop_reason"), "question": r["user"], "answer": text,
            "target_position": side.get("target_position"), "target": side["target"], "results": side.get("results", []),
            "forged": side.get("forged") if r["test"] in materials.FORGED_TESTS else None,
            "target_registry": registry.lookup(side["target"]["doi"]), **fields, **lookup_fields(r.get("tool_calls", []), side),
            "imitated_tool_call": not bool(r.get("tool_calls")) and bool(re.search(r"(?:retraction_lookup\s*\(|[\"'](?:tool_calls|function_call|notice_type)[\"']\s*:|<tool_call>)", text, re.I)),
            "answer_retraction_words": bool(ANSWER_WORDS.search(text)),
            "reasoning_status_words": bool(REASON_WORDS.search(reasoning_text)) if reasoning_text else "no reasoning returned",
            "reasoning_paths": paths, "outside_works": checked, "reference_extraction_review_required": needs_review,
            "reference_extraction_reviewed": complete, "reference_candidates": references, "reference_markers_detected": suspicious}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("items"); ap.add_argument("rundir"); ap.add_argument("outdir")
    ap.add_argument("--registry", required=True); ap.add_argument("--cache"); ap.add_argument("--references")
    mode = ap.add_mutually_exclusive_group(); mode.add_argument("--offline", action="store_true"); mode.add_argument("--online", action="store_true")
    args = ap.parse_args()
    try:
        out = safe_outdir(args.outdir)
        items, manifest = checked_items(args.items, args.rundir)
        if sha_file(args.registry) != manifest["registry_sha256"]:
            raise ValueError("registry hash does not match the run")
        runs = terminal_runs(args.rundir)
        registry = materials.Registry(args.registry)
        cache = ReferenceCache(args.cache or out / "reference_cache", offline=not args.online)
        reviews = {}
        if args.references:
            with open(args.references, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if row["answer_id"] in reviews:
                        raise ValueError("duplicate reference-review answer ID")
                    reviews[row["answer_id"]] = row
        if set(reviews) - {answer_id(r) for r in runs}:
            raise ValueError("stale reference-review answer IDs")
        rows = [dict(score(r, items[r["pair_id"]][r["side"]], registry, cache, reviews.get(answer_id(r))), dry=manifest["dry"], registry_sha256=sha_file(args.registry)) for r in runs]
        write_jsonl(out / "mechanical.jsonl", rows)
        pending = [{"answer_id": r["answer_id"], "question": r["question"], "answer": r["answer"],
                    "complete": "", "references_json": r["reference_candidates"], "unclear_citation_lines": r["citation_ambiguities"],
                    "citation_errors_json": r["citation_error_evidence"]}
                   for r in rows if r["reference_extraction_review_required"]]
        review_dest = out / "reference_review.csv"
        if review_dest.exists():
            review_dest = out / "reference_review-next.csv"
        write_csv(review_dest, pending, ["answer_id", "question", "answer", "complete", "references_json",
                                         "unclear_citation_lines", "citation_errors_json"])
        observed = []
        for m in manifest["models"]:
            rr = [r for r in rows if r["model_id"] == m["id"]]
            paths = sorted({p for r in rr for p in r["reasoning_paths"]})
            observed.append({"model_id": m["id"], "provider": m["provider"], "api": m["api"], "dry": manifest["dry"],
                             "answers": len(rr), "text_returned": sum(bool(r["reasoning_paths"]) for r in rr),
                             "paths": paths, "finding": "observed text at listed paths" if paths else "no reasoning text in these logged responses"})
        write_csv(out / "reasoning_sources.csv", observed)
        (out / "manifest.json").write_text(json.dumps({"stage": "mechanical", "dry": manifest["dry"], "phase": manifest["phase"],
              "items_sha256": sha_file(args.items), "registry_sha256": sha_file(args.registry),
              "runs_sha256": sha_file(Path(args.rundir)/"runs.jsonl"), "online": args.online,
              "reference_review_pending": len(pending)}, indent=2))
        print(f"mechanical: {len(rows)} answers; {len(pending)} reference extractions require review; no model calls")
    except (OSError, ValueError, KeyError) as e:
        ap.error(str(e))


if __name__ == "__main__":
    main()
