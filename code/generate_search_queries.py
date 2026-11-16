"""Frozen, isolated query extraction for the pilot development questions.

python3 -I code/generate_search_queries.py --drafts DRAFTS.jsonl --logdir DIR --budget 1
Use --prepare-only to freeze exact requests without making calls.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import openrouter
from budget import RequestBudget, BudgetReached
from environment import capture_environment
from logfiles import Appender, read_log, write_json
from draft_topics_v2 import digest, file_hash, completed_record

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "protocol/search-query-v1"
STOP = frozenset("a an the of for in on at to and or with by from as its their".split())


def compile_query(groups, question):
    if not isinstance(groups, dict) or set(groups) != {"context", "focus"}:
        raise ValueError("exactly context and focus groups are required")
    compiled = []
    for name in ("context", "focus"):
        terms = groups[name]
        if not isinstance(terms, list) or not 1 <= len(terms) <= 3:
            raise ValueError("each group must have one to three spans")
        parts = []
        for term in terms:
            if not isinstance(term, str) or not term.strip() or term != term.strip() or len(term.split()) > 5:
                raise ValueError("invalid or overlong span")
            if not re.fullmatch(r"[^\W_]+(?:[ -][^\W_]+)*", term, re.UNICODE):
                raise ValueError("search syntax or unsupported characters in span")
            if not re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", question):
                raise ValueError("span is not copied verbatim from the question")
            tokens = [t for t in re.findall(r"[^\W_]+", term, re.UNICODE) if t.lower() not in STOP]
            if not tokens:
                raise ValueError("span has no searchable tokens")
            part = "(" + " AND ".join(tokens) + ")"
            if part in parts:
                raise ValueError("duplicate compiled span")
            parts.append(part)
        compiled.append("(" + " OR ".join(parts) + ")")
    if compiled[0] == compiled[1]:
        raise ValueError("context and focus must differ")
    return " AND ".join(compiled)


def request_plan(drafts, cfg, prompt):
    requests, seen = [], set()
    for row in drafts:
        code = row["item_code"]
        if code in seen or row.get("dry") or row.get("status") != "pending_scientific_review":
            raise ValueError("duplicate, dry or incomplete input question")
        seen.add(code)
        if digest({"request_sha256": row["request_sha256"], "raw_text": row["raw_text"]}) != row["content_sha256"]:
            raise ValueError("question identity mismatch")
        if row["draft"] != row["raw_text"].strip():
            raise ValueError("question changed from the saved first response")
        body = {"model": cfg["id"], "provider": openrouter._provider(cfg["provider"]), "max_tokens": 4000,
                "temperature": 0, "top_p": 1,
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content":
                    json.dumps({"question": row["draft"]}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}]}
        requests.append({"item_code": code, "topic_content_sha256": row["content_sha256"],
                         "question": row["draft"], "body": body, "request_sha256": digest(body)})
    if len(requests) != 6:
        raise ValueError("this development batch must include all six pilot questions")
    return requests


def interpret(request, response, started, seconds, recovered=False):
    r = completed_record(request, response, started, seconds, False, recovered)
    r["topic_content_sha256"] = request["topic_content_sha256"]
    r["question"] = request["question"]
    try:
        if r.get("stop_reason") != "stop":
            raise ValueError("output incomplete or stop reason missing")
        groups = json.loads(r["raw_text"])
        query = compile_query(groups, request["question"])
        r.update(status="compiled_unapproved", groups=groups, query=query,
                 query_sha256=hashlib.sha256(query.encode()).hexdigest())
    except (ValueError, TypeError) as e:
        r.update(status="needs_review", validation_error=str(e))
    return r


def run(drafts_path, directory, budget, prepare_only=False):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".query.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another query-generation process holds this directory")
        return run_locked(Path(drafts_path), directory, budget, prepare_only)


def run_locked(drafts_path, directory, budget, prepare_only):
    cfg = json.loads((ROOT / "code/models.json").read_text())["drafter"]
    prompt = (PACKAGE / "PROMPT.txt").read_text()
    drafts = [json.loads(line) for line in drafts_path.read_text().splitlines()]
    requests = request_plan(drafts, cfg, prompt)
    manifest = {"phase": "search-query-development-v1", "drafts_sha256": file_hash(drafts_path),
                "prompt_sha256": file_hash(PACKAGE / "PROMPT.txt"), "protocol_sha256": file_hash(PACKAGE / "PROTOCOL.md"),
                "requests_sha256": digest(requests), "runner_sha256": file_hash(__file__),
                "client_sha256": file_hash(ROOT / "code/openrouter.py"),
                "helper_sha256": file_hash(ROOT / "code/draft_topics_v2.py"), "scientific_approvals": 0}
    mp = directory / "manifest.json"
    if mp.exists() and json.loads(mp.read_text()) != manifest:
        raise SystemExit("manifest differs: use a new version/directory, never mix configurations")
    write_json(str(mp), manifest, indent=2)
    write_json(str(directory / "requests.json"), requests, indent=2, ensure_ascii=False)
    if prepare_only:
        print("Prepared six exact requests; no calls made."); return
    append = Appender()
    http, hn = read_log(str(directory / "http.jsonl"))
    rows, rn = read_log(str(directory / "queries.jsonl"))
    expected = {r["item_code"]: r for r in requests}; done = {}
    for r in rows:
        code = r["item_code"]
        if code in done or code not in expected or r["request_sha256"] != expected[code]["request_sha256"]:
            raise SystemExit("duplicate, unknown or stale query completion")
        done[code] = r
    guard = RequestBudget(budget, .10, http)
    sent = {h["uid"]: h for h in http if h["kind"] == "request"}
    for h in http:
        code = h.get("item_code"); response = h.get("body")
        if h["kind"] != "response" or h.get("http_status") != 200 or code in done:
            continue
        if isinstance(response, dict) and response.get("error"):
            continue
        previous = sent.get(h["uid"])
        if code not in expected or previous is None or previous.get("body") != expected[code]["body"]:
            raise SystemExit("unmatched HTTP completion")
        r = interpret(expected[code], response, previous["utc"], h.get("seconds"), True)
        r["received_utc"] = h["utc"]
        append.write(str(directory / "queries.jsonl"), r); done[code] = r
    append.write(str(directory / "events.jsonl"), {"event": "started", "utc": openrouter._now(),
                 "repairs": [x for x in (hn, rn) if x], "budget_guard_usd": budget,
                 **capture_environment([__file__, str(PACKAGE / "PROMPT.txt"), str(ROOT / "code/openrouter.py")])})
    try:
        for request in requests:
            code, body = request["item_code"], request["body"]
            if code in done:
                continue
            def log_http(record):
                if record["kind"] == "request" and record["body"] != body:
                    raise SystemExit("outgoing payload differs from frozen request")
                guard.observe(record)
                append.write(str(directory / "http.jsonl"), {"item_code": code, **record})
            started = openrouter._now()
            response, seconds = openrouter.chat(body["model"], body["provider"]["only"][0], body["messages"],
                max_tokens=body["max_tokens"], temperature=body["temperature"], top_p=body["top_p"], log=log_http)
            r = interpret(request, response, started, seconds)
            append.write(str(directory / "queries.jsonl"), r); done[code] = r
            print(code, r["status"], r.get("query", r.get("validation_error")), flush=True)
    finally:
        good = [done[r["item_code"]] for r in requests if r["item_code"] in done and done[r["item_code"]]["status"] == "compiled_unapproved"]
        summary = {"completed": len(done), "compiled": len(good), "planned": len(requests),
                   "known_cost_usd": guard.known_cost, "reserved_or_known_usd": guard.spent,
                   "unknown_attempts": guard.unknown_attempts, "approvals": 0}
        write_json(str(directory / "summary.json"), summary, indent=2)
        append.write(str(directory / "events.jsonl"), {"event": "stopped", "utc": openrouter._now(), **summary})
        if len(good) == len(requests):
            keys = ("item_code", "question", "topic_content_sha256", "groups", "query", "query_sha256")
            plan = {"status": "FROZEN_DEVELOPMENT_QUERIES_UNAPPROVED", "version": "search-query-v1",
                    "generation_manifest_sha256": file_hash(mp), "items": [{k:r[k] for k in keys} for r in good]}
            write_json(str(directory / "query-plan.json"), plan, indent=2, ensure_ascii=False)
    if len(good) != len(requests):
        raise SystemExit("query batch unresolved; no complete search plan exported; no semantic rerolls")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drafts", required=True); ap.add_argument("--logdir", required=True)
    ap.add_argument("--budget", type=float); ap.add_argument("--prepare-only", action="store_true")
    a = ap.parse_args()
    if not a.prepare_only and a.budget is None:
        ap.error("--budget is required for live calls")
    try:
        run(a.drafts, a.logdir, a.budget, a.prepare_only)
    except (openrouter.StopRun, openrouter.CallFailed, openrouter.RateLimited, BudgetReached, ValueError) as e:
        raise SystemExit(f"STOPPED: {e}")
