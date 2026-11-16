"""Execute frozen v2.1 development requests, without modifying approved materials.

Usage: python3 -I code/draft_topics_v2.py --logdir DIR --budget 1
Offline: add --dry (use a separate directory).

One completed response per item, including NEEDS_REVIEW, empty or malformed output.
No semantic rerolls. Transient transport retries use the existing logged client.
Outputs are development drafts and blank reviews, not legacy approved topic sheets.
"""
import argparse
import csv
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import openrouter
from budget import RequestBudget, BudgetReached
from environment import capture_environment
from logfiles import Appender, read_log, write_json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "protocol/topic-drafting-v2.1"
REQUESTS = ROOT / "results/topic-drafting-v2.1-candidate/pilot-requests.NOT-SENT.json"
CRITERIA = ("A1_source_fidelity_and_target_relevance", "A2_neutral_premise", "A3_setting_and_components",
            "A4_incidental_identifiers", "A5_appropriate_scope", "A6_usable_format")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepared_requests(package=PACKAGE, requests_path=REQUESTS):
    package, requests_path = Path(package), Path(requests_path)
    m = json.loads((package / "manifest.json").read_text())
    prompt = (package / "PROMPT.txt").read_text()
    for path in (package / "PROMPT.txt", package / "PROTOCOL.md", requests_path):
        relative = str(path.relative_to(ROOT))
        if file_hash(path) != m["candidate_artifact_sha256"].get(relative):
            raise SystemExit(f"frozen candidate artifact changed: {relative}; version it before running")
    for relative, expected in m["prior_source_sha256"].items():
        if relative.startswith("data/") and file_hash(ROOT / relative) != expected:
            raise SystemExit(f"source materials changed: {relative}; prepare a new request package")
    requests = json.loads(requests_path.read_text())
    seen = set()
    for r in requests:
        if r["item_code"] in seen:
            raise SystemExit("duplicate prepared item code")
        seen.add(r["item_code"])
        b = r["body"]
        if digest(b) != r["request_sha256"]:
            raise SystemExit("prepared request hash mismatch")
        if {k: v for k, v in b.items() if k != "messages"} != m["request_configuration"]:
            raise SystemExit("mixed drafting configurations")
        if len(b["messages"]) != 2 or b["messages"][0] != {"role": "system", "content": prompt}:
            raise SystemExit("drafting context is not the frozen system prompt plus one source message")
        if b["messages"][1]["role"] != "user":
            raise SystemExit("invalid source role")
        source = json.loads(b["messages"][1]["content"])
        if set(source) != {"title", "abstract"} or not all(isinstance(v, str) and v.strip() for v in source.values()):
            raise SystemExit("source must contain only a nonempty title and abstract")
    if len(requests) != 6:
        raise SystemExit("this adopted development batch must contain all six pilot items")
    return requests, m


def output_status(text, finish_reason):
    if finish_reason != "stop":
        return "incomplete_or_unverified_finish"
    if text.strip() == "NEEDS_REVIEW":
        return "needs_review"
    if not text.strip():
        return "empty"
    # A format screen only. Passing this does not establish a single grammatical
    # sentence, neutral wording, scientific fidelity, or source relevance.
    stripped = text.strip()
    if "\n" in stripped or stripped.count("?") != 1 or not stripped.endswith("?"):
        return "format_requires_review"
    if stripped.startswith(("#", ">", '"', "'", "- ", "1.")):
        return "format_requires_review"
    return "pending_scientific_review"


def completed_record(request, response, started, seconds, dry, recovered=False):
    body = request["body"]
    choices = response.get("choices") if isinstance(response, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else ""
    if not isinstance(text, str):
        text = ""
    usage = openrouter.usage_fields(response, "chat") if isinstance(response, dict) else {}
    return {"item_code": request["item_code"], "request_sha256": request["request_sha256"],
            "sent_utc": started, "received_utc": openrouter._now(), "seconds": seconds, "dry": dry,
            "recovered_from_http": recovered, "request": body, "response": response,
            "raw_text": text, "draft": text.strip(),
            "content_sha256": digest({"request_sha256": request["request_sha256"], "raw_text": text}),
            "status": output_status(text, choice.get("finish_reason")),
            "source": json.loads(body["messages"][1]["content"]), **usage}


def export_review(directory, done):
    rows = []
    for code, r in sorted(done.items()):
        for criterion in CRITERIA:
            rows.append({"item_code": code, "prompt_version": "v2.1", "question": r["draft"],
                         "content_sha256": r["content_sha256"], "criterion": criterion,
                         "decision": "", "source_passage": "", "reason": "", "reviewer_id": "",
                         "reviewer_role": "", "ai_assistance": "", "reviewed_utc": ""})
    path = directory / "stage-a-review.csv"
    if path.exists():
        with path.open() as stream:
            previous = list(csv.DictReader(stream))
        if any(any(row.get(k, "").strip() for k in ("decision", "source_passage", "reason", "reviewer_id"))
               for row in previous):
            path = directory / "stage-a-review.NEW-BLANK.csv"
    if rows:
        buf = io.StringIO(newline="")
        w = csv.DictWriter(buf, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(buf.getvalue(), encoding="utf-8"); os.replace(temp, path)


def run(directory, budget, dry=False):
    requests, package_manifest = prepared_requests()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".drafting.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another drafting process holds this log directory")
        return run_locked(directory, budget, dry, requests)


def run_locked(directory, budget, dry, requests):
    manifest = {"phase": "topic-development-v2.1", "dry": dry,
                "request_file_sha256": file_hash(REQUESTS),
                "candidate_manifest_sha256": file_hash(PACKAGE / "manifest.json"),
                "runner_sha256": file_hash(__file__), "client_sha256": file_hash(ROOT / "code/openrouter.py"),
                "review_is_pending": True, "items": [r["item_code"] for r in requests]}
    mp = directory / "manifest.json"
    if mp.exists() and json.loads(mp.read_text()) != manifest:
        raise SystemExit("run manifest changed; use a new log directory, never mix dry/live or prompt versions")
    write_json(str(mp), manifest, indent=2)
    append = Appender()
    http, http_note = read_log(str(directory / "http.jsonl"))
    records, record_note = read_log(str(directory / "drafts.jsonl"))
    done = {}
    expected = {r["item_code"]: r for r in requests}
    for r in records:
        code = r["item_code"]
        if code in done or code not in expected or r["request_sha256"] != expected[code]["request_sha256"]:
            raise SystemExit("duplicate, unknown or stale completed draft")
        done[code] = r
    guard = RequestBudget(budget, .10, http)
    # Recover an answer durably logged at the HTTP boundary if a crash occurred
    # before drafts.jsonl was written. Do not pay to reroll a completed response.
    sent = {h["uid"]: h for h in http if h["kind"] == "request"}
    for h in http:
        code = h.get("item_code")
        response = h.get("body")
        if h["kind"] != "response" or h.get("http_status") != 200 or code in done:
            continue
        if isinstance(response, dict) and response.get("error"):
            continue
        request = sent.get(h["uid"])
        if code not in expected or request is None or request.get("body") != expected[code]["body"]:
            raise SystemExit("unmatched HTTP completion; inspect logs before resuming")
        rec = completed_record(expected[code], response, request["utc"], h.get("seconds"), dry, recovered=True)
        rec["received_utc"] = h["utc"]
        append.write(str(directory / "drafts.jsonl"), rec)
        done[code] = rec
    append.write(str(directory / "events.jsonl"), {"event": "started", "utc": openrouter._now(),
                 "repairs": [n for n in (http_note, record_note) if n],
                 **capture_environment([__file__, str(ROOT / "code/openrouter.py"), str(PACKAGE / "PROMPT.txt")])})
    try:
        for r in requests:
            code, body = r["item_code"], r["body"]
            if code in done:
                continue

            def log_http(record):
                if record["kind"] == "request" and record["body"] != body:
                    raise SystemExit("HTTP payload differs from frozen request")
                guard.observe(record)
                append.write(str(directory / "http.jsonl"), {"item_code": code, **record})

            started = openrouter._now()
            if dry:
                response = {"choices": [{"message": {"content": "What relationship is investigated?"},
                                         "finish_reason": "stop"}], "model": "dry", "usage": {"cost": 0}}
                seconds = 0
            else:
                response, seconds = openrouter.chat(body["model"], body["provider"]["only"][0], body["messages"],
                    max_tokens=body["max_tokens"], temperature=body["temperature"], top_p=body["top_p"], log=log_http)
            rec = completed_record(r, response, started, seconds, dry)
            append.write(str(directory / "drafts.jsonl"), rec)
            done[code] = rec
            export_review(directory, done)
            print(f"{code}: {rec['status']}", flush=True)
    finally:
        export_review(directory, done)
        summary = {"completed": len(done), "planned": len(requests), "dry": dry,
                   "known_cost_usd": guard.known_cost, "reserved_or_known_usd": guard.spent,
                   "unknown_attempts": guard.unknown_attempts,
                   "statuses": {code: r["status"] for code, r in done.items()},
                   "scientifically_approved": 0, "experimental_items_created": 0}
        write_json(str(directory / "summary.json"), summary, indent=2)
        append.write(str(directory / "events.jsonl"), {"event": "stopped", "utc": openrouter._now(), **summary})
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--logdir", required=True); ap.add_argument("--budget", type=float)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if not args.dry and args.budget is None:
        ap.error("live drafting requires --budget")
    try:
        print(json.dumps(run(args.logdir, args.budget, args.dry), indent=2))
    except (openrouter.StopRun, openrouter.CallFailed, openrouter.RateLimited, BudgetReached) as e:
        raise SystemExit(f"STOPPED: {e}")


if __name__ == "__main__":
    main()
