"""Isolated two-model candidate-fit screen, with no human or packet approvals."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import materials_development as M
import openrouter
from budget import BudgetReached
from logfiles import write_json, read_log

ROOT = M.ROOT
PACKAGE = ROOT / "protocol/materials-development-v4"
CRITERIA = ("B1_direct_evidence", "B2_scope", "B3_relationship")


def schema_for(ids):
    properties = {k: {"type": "string", "enum": ["pass", "fail", "uncertain"]} for k in CRITERIA}
    properties.update(evidence={"type": "string"}, reason={"type": "string"})
    entry = {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}
    return {"type": "json_schema", "json_schema": {"name": "candidate_relevance", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["assessments"], "properties": {
            "assessments": {"type": "object", "additionalProperties": False, "required": ids,
                            "properties": {i:entry for i in ids}}}}}}


def plan(candidate_path, drafts_path):
    candidates = json.loads(Path(candidate_path).read_text())
    codes = json.loads((Path(candidate_path).parent / "topic_codes.json").read_text())
    reverse = {v:k for k,v in codes.items()}
    drafts = {r["item_code"]: r for r in M.load_drafts(drafts_path)}
    if set(candidates) != set(reverse):
        raise ValueError("candidate file must cover all six items")
    prompt = (PACKAGE / "CANDIDATE-REVIEW-PROMPT.txt").read_text()
    models = json.loads((ROOT / "code/models.json").read_text())["judges"]
    requests, index = [], []
    for key, packet in candidates.items():
        code = reverse[key]; question = drafts[code]["draft"]
        if packet["topic"] != question or not packet.get("development_unapproved"):
            raise ValueError("candidate packet does not match the development question")
        source = []
        for rank, c in enumerate(packet["candidates"], 1):
            identity = M.digest({"question": question, "doi": c["doi"], "title": c["title"], "abstract": c["abstract"]})
            cid = identity[:16]
            source.append({"candidate_id": cid, "title": c["title"], "abstract": c["abstract"]})
            index.append({"item_code": code, "candidate_id": cid, "rank": rank, "doi": c["doi"],
                          "content_sha256": identity, "topic_content_sha256": drafts[code]["content_sha256"]})
        if len({c["candidate_id"] for c in source}) != len(source):
            raise ValueError("duplicate candidate identity")
        for offset in range(0, len(source), 6):
            batch = sorted(source[offset:offset+6], key=lambda x:x["candidate_id"])
            content = {"question": question, "candidates": batch}
            for j, cfg in enumerate(models, 1):
                body = {"model": cfg["id"], "provider": openrouter._provider(cfg["provider"]), "temperature": 0,
                        "top_p": 1, "max_tokens": 12000, "response_format": schema_for([c["candidate_id"] for c in batch]),
                        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content":
                            json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}]}
                requests.append({"item_code": code, "task_id": f"{code}-batch{offset//6+1}-judge{j}",
                                 "body": body, "request_sha256": M.digest(body)})
    return requests, index


def interpret(phase, request, response, started, seconds, recovered=False):
    row = M.completed_record(request, response, started, seconds, False, recovered)
    row.update(task_id=request["task_id"], phase=phase, status="needs_review", reviewer_model=request["body"]["model"])
    try:
        if row.get("stop_reason") != "stop":
            raise ValueError("incomplete review")
        value = json.loads(row["raw_text"])
        source = {c["candidate_id"]: c for c in row["source"]["candidates"]}
        if not isinstance(value, dict) or set(value) != {"assessments"} or not isinstance(value["assessments"], dict) or set(value["assessments"]) != set(source):
            raise ValueError("review must cover each supplied candidate exactly once")
        assessments = {}
        for cid, entry in value["assessments"].items():
            valid = isinstance(entry, dict) and set(entry) == set(CRITERIA) | {"evidence", "reason"}
            valid = valid and all(entry[k] in ("pass", "fail", "uncertain") for k in CRITERIA)
            valid = valid and isinstance(entry["reason"], str) and bool(entry["reason"].strip())
            valid = valid and isinstance(entry["evidence"], str) and bool(entry["evidence"]) and \
                    any(entry["evidence"] in source[cid][k] for k in ("title", "abstract"))
            assessments[cid] = {"raw_assessment": entry, "evidence_and_schema_valid": bool(valid),
                                "provisional_pass": bool(valid and all(entry[k] == "pass" for k in CRITERIA))}
        row.update(status="ai_batch_assessed", assessments=assessments)
    except (ValueError, TypeError, KeyError) as exc:
        row["validation_error"] = str(exc)
    return row


def export(directory, index):
    records, _ = read_log(str(directory / "reviews.jsonl"), repair=False)
    seen = {}; all_codes = sorted(json.loads((directory / "source-items.json").read_text()))
    for r in records:
        for cid, assessment in r.get("assessments", {}).items():
            key = (r["item_code"], cid)
            seen.setdefault(key, {})[r["reviewer_model"]] = assessment
    models = [m["id"] for m in json.loads((ROOT / "code/models.json").read_text())["judges"]]
    result = {code: {"jointly_passing": [], "proposed_first_four": [], "candidates": []} for code in all_codes}
    for c in index:
        reviews = seen.get((c["item_code"], c["candidate_id"]), {})
        passed = set(reviews) == set(models) and all(a["provisional_pass"] for a in reviews.values())
        row = {**c, "joint_ai_pass": passed, "assessments": reviews}
        packet = result[c["item_code"]]; packet["candidates"].append(row)
        if passed: packet["jointly_passing"].append(c["candidate_id"])
    for packet in result.values():
        packet["proposed_first_four"] = packet["jointly_passing"][:4]
        packet["status"] = "four_ai_supported_candidates_packet_check_pending" if len(packet["jointly_passing"]) >= 4 else "insufficient_ai_supported_candidates"
        packet["human_approvals"] = 0
    write_json(str(directory / "candidate-fit-summary.json"), result, indent=2)
    return {k: {"prepared": len(v["candidates"]), "joint_ai_pass": len(v["jointly_passing"]), "status": v["status"]} for k,v in result.items()}


def run(candidate_path, drafts_path, directory, budget, prepare_only):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".calls.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        requests, index = plan(candidate_path, drafts_path)
        manifest = {"phase": "candidate-relevance-development-v4", "candidate_sha256": M.file_hash(candidate_path),
                    "drafts_sha256": M.file_hash(drafts_path), "requests_sha256": M.digest(requests), "concurrency": 3,
                    "hashes": {str(p.relative_to(ROOT)): M.file_hash(p) for p in [Path(__file__), ROOT / "code/materials_development.py",
                       ROOT / "code/draft_topics_v2.py", ROOT / "code/openrouter.py", ROOT / "code/models.json", ROOT / "code/budget.py",
                       ROOT / "code/logfiles.py", PACKAGE / "CANDIDATE-REVIEW-PROMPT.txt", PACKAGE / "CANDIDATE-REVIEW-PROTOCOL.md"]}}
        path = directory / "manifest.json"
        if path.exists() and json.loads(path.read_text()) != manifest:
            raise ValueError("changed candidate review manifest")
        if not path.exists() and not prepare_only:
            raise ValueError("prepare exact requests before calls")
        write_json(str(path), manifest, indent=2); write_json(str(directory / "requests.json"), requests, indent=2)
        write_json(str(directory / "candidate-index.json"), index, indent=2)
        write_json(str(directory / "source-items.json"), [r["item_code"] for r in M.load_drafts(drafts_path)])
        if prepare_only:
            write_json(str(directory / "prepared.json"), {"utc": openrouter._now(), "requests_sha256": M.digest(requests)}, indent=2)
            print(f"Prepared {len(requests)} calls for {len(index)} candidates; no calls made."); return
        M.PACKAGE = PACKAGE
        try:
            M.execute("candidate-review", requests, directory, budget, processor=interpret)
        finally:
            print(json.dumps(export(directory, index), indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", required=True); ap.add_argument("--drafts", required=True)
    ap.add_argument("--logdir", required=True); ap.add_argument("--budget", type=float)
    ap.add_argument("--prepare-only", action="store_true"); a = ap.parse_args()
    if not a.prepare_only and a.budget is None: ap.error("--budget required")
    try:
        run(a.candidates, a.drafts, a.logdir, a.budget, a.prepare_only)
    except (ValueError, openrouter.StopRun, openrouter.CallFailed, openrouter.RateLimited, BudgetReached) as exc:
        raise SystemExit(f"STOPPED: {exc}")
