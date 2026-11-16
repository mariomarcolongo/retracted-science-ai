"""Isolated, versioned development calls; never produces author approvals.

--phase topics uses prior drafts only as an immutable title/abstract source.
--phase question-review or queries takes the new drafts.jsonl as --source.
Always prepare exact requests first with --prepare-only, then use the same command
with --budget. Completed malformed responses are retained, never rerolled.
"""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parent))
import openrouter
from budget import RequestBudget, BudgetReached
from draft_topics_v2 import digest, file_hash, completed_record
from environment import capture_environment
from generate_search_queries import compile_query
from logfiles import Appender, read_log, write_json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "protocol/materials-development-v3"
DRAFTER_PROFILE = "mimo"
DRAFT_TOKEN_LIMIT = 4000
PROMPTS = {"topics": "TOPIC-PROMPT.txt", "question-review": "QUESTION-REVIEW-PROMPT.txt", "queries": "QUERY-PROMPT.txt"}
OUTPUTS = {"topics": "drafts.jsonl", "question-review": "reviews.jsonl", "queries": "queries.jsonl", "candidate-review": "reviews.jsonl"}


def review_format():
    entry = {"type": "object", "additionalProperties": False, "required": ["decision", "evidence", "reason"],
             "properties": {"decision": {"type": "string", "enum": ["pass", "fail", "uncertain"]},
                            "evidence": {"type": "string"}, "reason": {"type": "string"}}}
    schema = {"type": "object", "additionalProperties": False, "required": ["criteria", "summary"],
              "properties": {"summary": {"type": "string"}, "criteria": {"type": "object", "additionalProperties": False,
                 "required": [f"A{i}" for i in range(1,7)], "properties": {f"A{i}": entry for i in range(1,7)}}}}
    return {"type": "json_schema", "json_schema": {"name": "question_review", "strict": True, "schema": schema}}


def load_drafts(source):
    rows = [json.loads(line) for line in Path(source).read_text().splitlines()]
    if len(rows) != 6 or len({r["item_code"] for r in rows}) != 6:
        raise ValueError("all six unique development items are required")
    for r in rows:
        if r.get("dry") or r["draft"] != r["raw_text"].strip() or \
                r["content_sha256"] != digest({"request_sha256": r["request_sha256"], "raw_text": r["raw_text"]}):
            raise ValueError("dry, altered or unbound source")
    return rows


def requests_for(phase, source):
    drafts = load_drafts(source)
    models = json.loads((ROOT / "code/models.json").read_text())
    drafter = models["drafter"] if DRAFTER_PROFILE == "mimo" else next(x for x in models["backups"] if x["name"] == "Kimi K2.6")
    configs = models["judges"] if phase == "question-review" else [drafter]
    prompt = (PACKAGE / PROMPTS[phase]).read_text()
    requests = []
    for r in drafts:
        if phase != "topics" and r["status"] != "pending_scientific_review":
            raise ValueError("cannot process malformed or incomplete question")
        source_text = r["source"]
        if set(source_text) != {"title", "abstract"}:
            raise ValueError("topic source must be title and abstract only")
        content = source_text if phase == "topics" else \
                  {**source_text, "question": r["draft"]} if phase == "question-review" else {"question": r["draft"]}
        for index, cfg in enumerate(configs):
            body = {"model": cfg["id"], "provider": openrouter._provider(cfg["provider"]),
                    "temperature": 0, "top_p": 1, "max_tokens": 6000 if phase == "question-review" else DRAFT_TOKEN_LIMIT if phase == "topics" else 4000,
                    "messages": [{"role": "system", "content": prompt}, {"role": "user", "content":
                        json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}]}
            if phase == "question-review" and PACKAGE.name == "materials-development-v4":
                body["response_format"] = review_format()
            requests.append({"item_code": r["item_code"], "task_id": r["item_code"] + (f"-judge{index+1}" if phase == "question-review" else ""),
                             "body": body, "request_sha256": digest(body), "topic_content_sha256": r["content_sha256"],
                             "question": r["draft"] if phase != "topics" else None})
    return requests


def review_check(value, source):
    if not isinstance(value, dict) or set(value) != {"criteria", "summary"} or not isinstance(value["summary"], str):
        raise ValueError("invalid review envelope")
    criteria = value["criteria"]
    if not isinstance(criteria, dict) or set(criteria) != {f"A{i}" for i in range(1, 7)}:
        raise ValueError("all six criteria required")
    for entry in criteria.values():
        if not isinstance(entry, dict) or set(entry) != {"decision", "evidence", "reason"} or \
                entry["decision"] not in ("pass", "fail", "uncertain"):
            raise ValueError("invalid criterion")
        evidence = entry["evidence"]
        if not isinstance(evidence, str) or not evidence or not any(evidence in text for text in source.values()):
            raise ValueError("review evidence is not an exact source substring")
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise ValueError("missing criterion reason")
    return value


def interpret(phase, request, response, started, seconds, recovered=False):
    row = completed_record(request, response, started, seconds, False, recovered)
    row.update(task_id=request["task_id"], phase=phase, prompt_version=PACKAGE.name,
               topic_content_sha256=request["topic_content_sha256"])
    if phase == "topics":
        if row["status"] == "pending_scientific_review" and len(row["draft"].split()) > (30 if PACKAGE.name.endswith("v4") else 45):
            row["status"] = "format_requires_review"
        if PACKAGE.name.endswith("v4") and row["status"] == "pending_scientific_review" and not row["draft"].startswith("What evidence is available on"):
            row["status"] = "format_requires_review"
        return row
    row["question"] = request["question"]
    try:
        if row.get("stop_reason") != "stop":
            raise ValueError("incomplete output")
        value = json.loads(row["raw_text"])
        if phase == "question-review":
            row["assessment"] = review_check(value, row["source"])
            row["status"] = "ai_all_criteria_pass" if all(x["decision"] == "pass" for x in value["criteria"].values()) else "ai_unresolved"
        else:
            query = compile_query(value, request["question"], "search-query-v3" if PACKAGE.name.endswith("v4") else "search-query-v2")
            import hashlib
            row.update(groups=value, query=query, query_sha256=hashlib.sha256(query.encode()).hexdigest(), status="compiled_unapproved")
    except (ValueError, TypeError, KeyError) as exc:
        row.update(status="needs_review", validation_error=str(exc))
    return row


def run(phase, source, directory, budget=None, prepare_only=False):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".calls.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        requests = requests_for(phase, source)
        manifest = {"version": PACKAGE.name, "phase": phase, "source_sha256": file_hash(source),
                    "drafter_profile": DRAFTER_PROFILE,
                    "draft_token_limit": DRAFT_TOKEN_LIMIT,
                    "amendments": {p.name: file_hash(p) for p in sorted(PACKAGE.glob("*.md"))},
                    "concurrency": 3 if PACKAGE.name.endswith("v4") else 1,
                    "requests_sha256": digest(requests), "script_sha256": file_hash(__file__),
                    "dependencies": {str(p.relative_to(ROOT)): file_hash(p) for p in
                        [PACKAGE / PROMPTS[phase], PACKAGE / "PROTOCOL.md", ROOT / "code/models.json",
                         ROOT / "code/openrouter.py", ROOT / "code/draft_topics_v2.py", ROOT / "code/generate_search_queries.py",
                         ROOT / "code/budget.py", ROOT / "code/logfiles.py"]}}
        mp = directory / "manifest.json"
        if mp.exists() and json.loads(mp.read_text()) != manifest:
            raise ValueError("manifest changed; preserve prior run and use a new version/directory")
        if not mp.exists() and not prepare_only:
            raise ValueError("prepare exact requests before live calls")
        write_json(str(mp), manifest, indent=2)
        write_json(str(directory / "requests.json"), requests, indent=2, ensure_ascii=False)
        if not (directory / "prepared.json").exists():
            write_json(str(directory / "prepared.json"), {"utc": openrouter._now(), "requests_sha256": digest(requests)}, indent=2)
        if prepare_only:
            print(f"Prepared {len(requests)} exact requests; no calls made.", flush=True); return
        return execute(phase, requests, directory, budget)


def execute(phase, requests, directory, budget, processor=None):
    processor = processor or interpret
    append = Appender(); path = directory / OUTPUTS[phase]
    http, hn = read_log(str(directory / "http.jsonl")); rows, rn = read_log(str(path))
    expected = {r["task_id"]: r for r in requests}; done = {}
    for r in rows:
        key = r["task_id"]
        if key in done or key not in expected or r["request_sha256"] != expected[key]["request_sha256"]:
            raise ValueError("duplicate, unknown or stale completion")
        done[key] = r
    guard = RequestBudget(budget, .20 if phase == "question-review" else .10, http)
    sent = {h["uid"]: h for h in http if h["kind"] == "request"}
    for h in http:
        key = h.get("task_id"); response = h.get("body")
        if h["kind"] != "response" or h.get("http_status") != 200 or key in done or \
                (isinstance(response, dict) and response.get("error")):
            continue
        previous = sent.get(h["uid"])
        if key not in expected or previous is None or previous["body"] != expected[key]["body"]:
            raise ValueError("unmatched HTTP completion")
        row = processor(phase, expected[key], response, previous["utc"], h.get("seconds"), True)
        row["received_utc"] = h["utc"]; append.write(str(path), row); done[key] = row
    append.write(str(directory / "events.jsonl"), {"event": "started", "utc": openrouter._now(),
        "repairs": [x for x in (hn, rn) if x], "budget_guard_usd": budget, **capture_environment([__file__])})
    stop = threading.Event()
    def one(request):
        try:
            key, body = request["task_id"], request["body"]
            if key in done or stop.is_set():
                return
            def log_http(record):
                if record["kind"] == "request" and record["body"] != body:
                    raise ValueError("outgoing payload differs from frozen request")
                guard.observe(record)
                append.write(str(directory / "http.jsonl"), {"task_id": key, **record})
            started = openrouter._now()
            response, seconds = openrouter.chat(body["model"], body["provider"]["only"][0], body["messages"],
                max_tokens=body["max_tokens"], temperature=body["temperature"], top_p=body["top_p"],
                response_format=body.get("response_format"), log=log_http)
            row = processor(phase, request, response, started, seconds)
            append.write(str(path), row); done[key] = row
            print(key, row["status"], row["draft"] if phase == "topics" else row.get("query", ""), flush=True)
        except BaseException:
            stop.set()
            raise
    try:
        workers = 3 if PACKAGE.name.endswith("v4") else 1
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending = [executor.submit(one, request) for request in requests if request["task_id"] not in done]
            for future in as_completed(pending):
                future.result()
    finally:
        summary = {"completed": len(done), "planned": len(requests), "known_cost_usd": guard.known_cost,
                   "reserved_or_known_usd": guard.spent, "unknown_attempts": guard.unknown_attempts,
                   "statuses": {k:r["status"] for k,r in done.items()}, "human_approvals": 0}
        write_json(str(directory / "summary.json"), summary, indent=2)
        append.write(str(directory / "events.jsonl"), {"event": "stopped", "utc": openrouter._now(), **summary})
        if phase == "queries" and len(done) == len(requests) and all(r["status"] == "compiled_unapproved" for r in done.values()):
            keys = ("item_code", "question", "topic_content_sha256", "groups", "query", "query_sha256")
            plan = {"status": "FROZEN_DEVELOPMENT_QUERIES_UNAPPROVED", "version": "search-query-v3" if PACKAGE.name.endswith("v4") else "search-query-v2",
                    "search_field": "search.title_and_abstract", "generation_manifest_sha256": file_hash(directory / "manifest.json"),
                    "items": [{k:done[r["task_id"]][k] for k in keys} for r in requests]}
            write_json(str(directory / "query-plan.json"), plan, indent=2, ensure_ascii=False)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=list(PROMPTS), required=True); ap.add_argument("--source", required=True)
    ap.add_argument("--logdir", required=True); ap.add_argument("--budget", type=float)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--version", choices=["v3", "v4"], default="v3")
    ap.add_argument("--drafter-profile", choices=["mimo", "kimi"], default="mimo")
    ap.add_argument("--draft-token-limit", choices=[4000, 16000], type=int, default=4000)
    args = ap.parse_args()
    PACKAGE = ROOT / ("protocol/materials-development-" + args.version)
    DRAFTER_PROFILE = args.drafter_profile
    DRAFT_TOKEN_LIMIT = args.draft_token_limit
    if not args.prepare_only and args.budget is None:
        ap.error("live calls require --budget")
    try:
        result = run(args.phase, args.source, args.logdir, args.budget, args.prepare_only)
        if result:
            print(json.dumps(result, indent=2))
    except (ValueError, openrouter.StopRun, openrouter.CallFailed, openrouter.RateLimited, BudgetReached) as exc:
        raise SystemExit(f"STOPPED: {exc}")
