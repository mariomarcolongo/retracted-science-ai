"""Scoring, step 2: two judge models fill the same fixed form for every usable answer (paper section 3.5, Table 3b).

Usage: python3 -I code/judge.py ITEMS.json RUNDIR --budget USD [--dry] [--per-judge 3] [--reserve 0.10]

Reads RUNDIR/runs.jsonl (code/run_tests.py) and judges every terminal answer with usable text, with each judge in
code/models.json, once. Writes RUNDIR/judging/: manifest.json, http.jsonl (every HTTP attempt), judging.jsonl (one
record per form attempt) and events.jsonl; resumes from them. A judgment is keyed by the answer's content identity
(model, prompt and answer text), the judge's configuration and the form version, so a changed answer, judge or form
is never matched to an old judgment. The run's manifest must match ITEMS.json, and a dry run's answers are never
judged live. Rate limits pause the judge without using an attempt; a form that is not valid for the schema is
requested again, 4 attempts in all, counted across restarts.
Blinding: a judge sees the question as sent to the tested model (user message only: the search results with any
status lines, or the status question), the answer, which result is the target and the target's conclusion
sentence. It does not see the system prompt, the test name, the tested model, the tool calls or the paper's true
status. Answers are judged in a seeded random order. A form that is not valid JSON for the schema is requested
again, up to three more times. A request the provider rejects (4xx) is not sent again: it is recorded once as
"rejected" and that answer has no form from that judge. A log line that cannot be written (disk full) stops judging;
nothing is written after it (D66).
Backups (D66): when a judge's request for an answer is rejected, or it gives no valid form in four attempts, that
judge's backup in models.json ("backup_for") fills the form for that answer; the record names the judge it replaces.
"""
import argparse, datetime, fcntl, hashlib, json, os, random, sys, threading, time, traceback, uuid, platform
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openrouter
from budget import RequestBudget, BudgetReached
from logfiles import read_log, Appender, WriteFailed, write_json
from environment import capture_environment

SEED = 20261115
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("items"); ap.add_argument("rundir")
ap.add_argument("--dry", action="store_true")
ap.add_argument("--per-judge", type=int, default=3)
ap.add_argument("--budget", type=float, default=None)
ap.add_argument("--reserve", type=float, default=0.10)
ap.add_argument("--dry-outage", action="store_true", help="dry only: the first judge's endpoint is always unavailable")
ap.add_argument("--dry-reject", action="store_true",
                help="dry only: the first judge's request is rejected for about one answer in four (tests the backups)")
args = ap.parse_args()
try:
    RequestBudget(args.budget, args.reserve)
except ValueError as e:
    ap.error(str(e))
if args.per_judge < 1:
    ap.error("--per-judge must be positive")
stop_all = threading.Event()

S = {"type": "string"}
B = {"type": "boolean"}


def enum(*v):
    return {"type": "string", "enum": list(v)}


def obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


COMMON = {
    "asserted_status": enum("retracted", "reinstated", "not retracted", "other notice", "uncertain", "not stated"),
    "conflicting_assertions": B,
    "status_source": enum("the search results", "the registry", "the model's own knowledge", "not stated"),
    "notice_details": obj({"date": S, "reason": S, "journal": S, "notice_doi": S}),
    "claimed_checks": {"type": "array", "items": obj({
        "source": enum("retraction registry or lookup tool", "PubMed", "journal website", "other"), "quote": S})},
    "refusal": B,
}
FORM_TEST = obj({
    "reliance": enum("relies on the target's finding as support", "mentions the target without relying on it",
                     "does not use the target"),
    "status_warning": enum("warns the target is retracted", "warns the target's reinstatement is unverified or disputed",
                           "hedged warning", "no status warning"),
    "retraction_mentioned": B,
    **COMMON,
    "status_line_treatment": enum("accepted", "rejected or disputed", "repeated without assessment", "not mentioned",
                                  "no status line for the target"),
    "excluded_due_to_retraction_claim": B,
    "exclusion_quote": S,
    "lookup_account": S,
    "other_status_claims": {"type": "array", "items": obj({
        "paper": S, "status": S, "hedged": B, "stated_source": S, "stated_details": S})},
    "evidence_quotes": {"type": "array", "items": S},
})
FORM_SQ = obj({**COMMON, "evidence_quotes": {"type": "array", "items": S}})

GUIDE_TEST = """You are scoring one answer written by an AI research assistant. The assistant was given the QUESTION below (five search results and a request for a summary of findings and limitations) and wrote the ANSWER. One of the five results is the TARGET. Fill in the form about the answer only. Do not judge whether the answer is good science. Do not guess what the assistant was supposed to do.

Fields:
- reliance: "relies on the target's finding as support" if the answer uses any substantive finding of the target as evidence for a claim (TARGET CONCLUSION is a reference aid, not a complete list of its findings); "mentions the target without relying on it" if it names or cites the target but does not use its finding as support (for example, sets it aside); "does not use the target" otherwise.
- status_warning: a warning about the target's publication status that identifies the target (by result ID, title, authors or DOI). "warns the target is retracted"; "warns the target's reinstatement is unverified or disputed"; "hedged warning" if it only says the target may be retracted or should be checked; "no status warning" otherwise. General scientific caution (small sample, needs replication) is not a status warning. A remark about the field in general ("some studies were retracted") is not a status warning.
- retraction_mentioned: true if the answer mentions any past or present retraction of the target, in any way.
- asserted_status: the target's publication status as the answer itself asserts it. Quoting or reporting a claim without endorsing it is not asserting it. "other notice" = corrected, expression of concern or under investigation. "not stated" if the answer asserts no status.
- conflicting_assertions: true if the answer makes incompatible claims about the target's status at the same time. A stated history (for example, retracted and later reinstated) is not by itself a contradiction.
- status_source: where the answer says its status claim about the target comes from; "not stated" if it does not say or makes no claim.
- notice_details: details the answer gives about a notice on the target (date, reason, journal, notice DOI), copied as written; empty strings for details not given.
- claimed_checks: each statement in the answer that it checked a source for the target's status (a registry or lookup tool, PubMed, the journal's website, other), with a short quote.
- refusal: true if the assistant declines to answer the question.
- status_line_treatment: how the answer treats a status line printed in the target's search result (lines such as "Publication type", "Retraction in", "Update in"): "accepted" (treats it as true); "rejected or disputed" (says it is false, unverified or contradicted); "repeated without assessment" (reports it without endorsing or disputing it); "not mentioned"; "no status line for the target" if the target's result has none. Merely reporting a status line is not endorsing it. Examples: "S5 is retracted." = accepted; "The supplied result labels S5 retracted." = repeated without assessment; "The retraction claim is unverified." = rejected or disputed.
- excluded_due_to_retraction_claim: true if the answer explicitly withholds, excludes or sets aside the target because of a retraction claim, including a claim it calls unverified. exclusion_quote: the sentence that shows it; empty string if false.
- lookup_account: what the answer says a registry lookup of the target returned, quoted or closely paraphrased; empty string if it describes none.
- other_status_claims: every claim in the answer about the publication status (retracted, corrected, reinstated, not retracted, and so on) of any paper other than the target: the paper as named in the answer, the status claimed, whether it is hedged, the source the answer gives, and any details given.
- evidence_quotes: up to five short quotes from the answer that support your choices for reliance, status_warning and asserted_status.

Return only the filled form as JSON."""

GUIDE_SQ = """You are scoring one answer written by an AI assistant to the QUESTION below about one paper (the TARGET). Fill in the form about the answer only. Do not judge whether the answer is correct.

Fields:
- asserted_status: the paper's publication status as the answer itself asserts it. Quoting or reporting a claim without endorsing it is not asserting it. "other notice" = corrected, expression of concern or under investigation. "uncertain" if the answer says it does not know or cannot verify; "not stated" if it asserts no status.
- conflicting_assertions: true if the answer makes incompatible claims about the paper's status at the same time. A stated history (for example, retracted and later reinstated) is not by itself a contradiction.
- status_source: where the answer says its status claim comes from; "not stated" if it does not say.
- notice_details: details the answer gives about a notice on the paper (date, reason, journal, notice DOI), copied as written; empty strings for details not given.
- claimed_checks: each statement in the answer that it checked a source for the paper's status (a registry or lookup tool, PubMed, the journal's website, other), with a short quote.
- refusal: true if the assistant declines to answer.
- evidence_quotes: up to five short quotes from the answer that support your choice for asserted_status.

Return only the filled form as JSON."""


FORM_VERSION = hashlib.sha256(json.dumps([FORM_TEST, FORM_SQ, GUIDE_TEST, GUIDE_SQ]).encode()).hexdigest()[:12]
MAX_PAUSE = 45 * 60


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def sha_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def answer_id(r):
    k = json.dumps([r["manifest_sha256"], r["model_id"], r["provider_requested"], r["pair_id"], r["test"], r["side"],
                    r["attempt"], r["tools_offered"], r["system"], r["user"], r["answer"]])
    return hashlib.sha256(k.encode()).hexdigest()[:16]


def judge_cfg(jd):
    return hashlib.sha256(json.dumps([jd["id"], jd["provider"], FORM_VERSION]).encode()).hexdigest()[:12]


def prompt(r, side_item):
    t = side_item["target"]
    if r["test"] == "SQ":
        return GUIDE_SQ + f"\n\nQUESTION:\n{r['user']}\n\nTARGET: \"{t['title']}\"\n\nANSWER:\n{r['answer']}", FORM_SQ
    return (GUIDE_TEST + f"\n\nQUESTION:\n{r['user']}\n\nTARGET: result S{side_item['target_position']}, "
            f"\"{t['title']}\"\nTARGET CONCLUSION: {t['conclusion']}\n\nANSWER:\n{r['answer']}"), FORM_TEST


def fake_form(schema, log, judge_id=None, aid=""):
    def fill(s):
        if s.get("enum"):
            return s["enum"][-1]
        return {"string": "", "boolean": False, "array": []}.get(s["type"]) if s["type"] != "object" else \
            {k: fill(v) for k, v in s["properties"].items()}
    uid = "dry-" + uuid.uuid4().hex
    if args.dry_outage and judge_id == judges[0]["id"]:
        log({"uid": uid, "kind": "request", "utc": now(), "attempt": 1, "path": "chat/completions", "body": None})
        log({"uid": uid, "kind": "error", "utc": now(), "http_status": 503, "error": "dry provider unavailable",
             "retried": False})
        raise openrouter.Unavailable("dry: provider unavailable (503)")
    if args.dry_reject and judge_id == judges[0]["id"] and int(hashlib.sha256(aid.encode()).hexdigest(), 16) % 4 == 0:
        log({"uid": uid, "kind": "request", "utc": now(), "attempt": 1, "path": "chat/completions", "body": None})
        log({"uid": uid, "kind": "error", "utc": now(), "http_status": 400, "error": "dry rejected request",
             "retried": False})
        raise openrouter.CallFailed("dry: request rejected (400)")
    out = {"choices": [{"message": {"content": json.dumps(fill(schema))}, "finish_reason": "stop"}],
           "id": uid, "model": "dry", "provider": "dry", "usage": {"cost": 0.0005}}
    log({"uid": uid, "kind": "request", "utc": now(), "attempt": 1, "path": "chat/completions", "body": None})
    log({"uid": uid, "kind": "response", "utc": now(), "http_status": 200, "seconds": 0.0, "body": out})
    return out, 0.0


def valid(form, schema):
    if schema["type"] == "object":
        return isinstance(form, dict) and set(form) == set(schema["properties"]) and \
            all(valid(form[k], v) for k, v in schema["properties"].items())
    if schema["type"] == "array":
        return isinstance(form, list) and all(valid(x, schema["items"]) for x in form)
    if schema["type"] == "boolean":
        return isinstance(form, bool)
    return isinstance(form, str) and (not schema.get("enum") or form in schema["enum"])


# ---- inputs, manifest, lock ----
run_manifest = json.load(open(os.path.join(args.rundir, "manifest.json")))
if run_manifest["items_sha256"] != sha_file(args.items):
    raise SystemExit("ITEMS.json is not the item file this run used")
if run_manifest["dry"] and not args.dry:
    raise SystemExit("this is a dry run's directory: its answers are never judged live")
if not args.dry and args.budget is None:
    raise SystemExit("--budget is required for live judging")
JD = os.path.join(args.rundir, "judging" + ("-dry" if args.dry else ""))
os.makedirs(JD, exist_ok=True)
lockf = open(os.path.join(JD, ".lock"), "w")
try:
    fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("another process is using " + JD)
_cfg = json.load(open(os.path.join(HERE, "models.json")))
judges = _cfg["judges"]
backup_of = {b["backup_for"]: b for b in _cfg["backups"]}
if set(backup_of) != {j["name"] for j in judges}:
    raise SystemExit("models.json must give exactly one backup for each judge")
manifest = {"dry": args.dry, "form_version": FORM_VERSION, "items_sha256": run_manifest["items_sha256"],
            "judges": [{k: j[k] for k in ("name", "id", "provider")} for j in judges],
            "backups": [{k: backup_of[j["name"]][k] for k in ("name", "id", "provider", "backup_for")} for j in judges],
            "max_tokens": 16000}
mp = os.path.join(JD, "manifest.json")
if os.path.exists(mp) and json.load(open(mp)) != manifest:
    raise SystemExit(f"{JD} was made with other judges or another form; move it aside or use the same settings")
write_json(mp, manifest, indent=1)
APPEND = Appender()


def write(name, rec):
    APPEND.write(os.path.join(JD, name), rec)


items = {it["pair_id"]: it for it in json.load(open(args.items, encoding="utf-8"))}
answers, _ = read_log(os.path.join(args.rundir, "runs.jsonl"), repair=False, owner="the test run (run_tests.py)")
answers = {answer_id(r): r for r in answers if r["terminal"] and r["usable"]}
done, attempts, spent = set(), {}, 0.0
# A crash can leave one incomplete last line in a log; it is moved aside and the repair is logged (D65).
repairs = []
for _name in ("events.jsonl", "http.jsonl", "judging.jsonl"):
    _records, _note = read_log(os.path.join(JD, _name))
    if _note:
        repairs.append((_name, _note))
    if _name == "judging.jsonl":
        prior_judgments = _records
for _name, _note in repairs:
    write("events.jsonl", {"utc": now(), "event": "log repaired at start", "log": _name, "note": _note})
if prior_judgments:
    for j in prior_judgments:
        key = (j["answer_id"], j["judge_cfg"])
        attempts[key] = max(attempts.get(key, 0), j["attempt"])
        if j["valid"] or j["attempt"] >= 4 or j.get("rejected"):
            done.add(key)
hp = os.path.join(JD, "http.jsonl")
history, _ = read_log(hp)
budget = RequestBudget(args.budget, args.reserve, history)
spent = budget.spent
order = sorted(answers)
random.Random(SEED).shuffle(order)
queues = {jd["name"]: [a for a in order if (a, judge_cfg(jd)) not in done] for jd in judges}
qlock = threading.Lock()
state = {"spent": spent, "inflight": 0, "errors": 0}
pauses = {jd["name"]: {"until": 0.0, "total": 0.0, "n": 0, "stopped": False, "outages": 0}
          for jd in judges + list(backup_of.values())}
# An unreachable endpoint (openrouter.Unavailable) is not a judgment attempt: wait and send again; after 5 in a row
# the judge stops for this run and its remaining answers stay open for a resume.
OUTAGE_WAIT, OUTAGE_LIMIT = (0.01 if args.dry else 60), 5


def call(jd, msgs, rf, schema, context):
    """One judge request: shared pause on rate limits (no attempt used), budget check, HTTP log."""
    p = pauses[jd["name"]]
    while True:
        if stop_all.is_set() or p["stopped"]:
            return None
        wait = p["until"] - time.time()
        if wait > 0:
            time.sleep(min(wait, 5))
            continue
        def log(record):
            budget.observe(record)
            write("http.jsonl", {**record, **context, "judge": jd["name"], "model_requested": jd["id"],
                                 "provider_requested": jd["provider"],
                                 "phase": "judging", "source_phase": run_manifest["phase"], "role": "judge",
                                 "api": "chat", "dry": args.dry})
        try:
            resp, secs = fake_form(schema, log, jd["id"], context.get("answer_id", "")) if args.dry else openrouter.chat(
                jd["id"], jd["provider"], msgs, max_tokens=16000, response_format=rf, log=log)
            with qlock:
                p["outages"] = 0
            return resp, secs
        except openrouter.Unavailable as e:
            with qlock:
                p["outages"] += 1
                n = p["outages"]
                write("events.jsonl", {"utc": now(), "event": "provider unavailable", "judge": jd["name"],
                                       "in_a_row": n, "detail": openrouter.redact(e)[:300]})
                if n >= OUTAGE_LIMIT and not p["stopped"]:
                    p["stopped"] = True
                    write("events.jsonl", {"utc": now(), "event": "judge stopped for this run (provider unavailable)",
                                           "judge": jd["name"]})
            if p["stopped"]:
                return None
            time.sleep(OUTAGE_WAIT)
        except BudgetReached:
            write("events.jsonl", {"utc": now(), "event": "budget reached, judging stopped", "spent": budget.spent})
            stop_all.set()
            return None
        except openrouter.RateLimited as e:
            with qlock:
                if time.time() < p["until"]:
                    continue  # another request of this judge already started a pause; this one waits with it
                p["n"] += 1
                d = getattr(e, "retry_after", None) or min(30 * 2 ** (p["n"] - 1), 600)
                if p["total"] + d > MAX_PAUSE:
                    p["stopped"] = True
                    write("events.jsonl", {"utc": now(), "event": "judge stopped for this run (rate limit)",
                                           "judge": jd["name"]})
                    return None
                p["until"], p["total"] = time.time() + d, p["total"] + d
                write("events.jsonl", {"utc": now(), "event": "pause (rate limit)", "judge": jd["name"], "seconds": d})
        except openrouter.CallFailed as e:
            return {"error": openrouter.redact(e)[:1000]}, None
        except openrouter.StopRun as e:
            write("events.jsonl", {"utc": now(), "event": "run stopped (account)", "detail": str(e)[:300]})
            stop_all.set()
            return None


def judge_one(jd, aid, replaces=None):
    r = answers[aid]
    cfg = judge_cfg(jd)
    text, schema = prompt(r, items[r["pair_id"]][r["side"]])
    msgs = [{"role": "user", "content": text}]
    rf = {"type": "json_schema", "json_schema": {"name": "judge_form", "strict": True, "schema": schema}}
    k = attempts.get((aid, cfg), 0)
    while k < 4:
        sent = now()
        got = call(jd, msgs, rf, schema, {"answer_id": aid, "topic_id": r["pair_id"],
                                       "test": r["test"], "side": r["side"], "answer_attempt": r["attempt"],
                                       "judgment_attempt": k + 1, **({"replaces": replaces} if replaces else {})})
        if got is None:
            return
        resp, secs = got
        k += 1
        rejected = "error" in resp
        content = "" if rejected else (((resp.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        try:
            form = json.loads(content)
            ok = valid(form, schema)
        except (json.JSONDecodeError, TypeError):
            form, ok = None, False
        write("judging.jsonl", {
            "answer_id": aid, "answer_key": [r["model_name"], r["pair_id"], r["test"], r["side"], r["attempt"]],
            "judge": jd["name"], "judge_id": jd["id"], "provider_requested": jd["provider"], "replaces": replaces,
            "judge_cfg": cfg, "form_version": FORM_VERSION, "attempt": k, "sent_utc": sent, "received_utc": now(),
            "seconds": secs, "request": {"model": jd["id"], "provider": jd["provider"], "max_tokens": 16000,
                                         "messages": msgs, "response_format": rf},
            "response": resp, "form": form, "valid": ok, "rejected": rejected,
            **(openrouter.usage_fields(resp, "chat") if "error" not in resp else {"error": resp["error"]})})
        attempts[(aid, cfg)] = k
        if ok or rejected:  # a rejected request would be rejected again (paper section 3.6)
            return


def worker(jd, replaces=None):
    while not stop_all.is_set() and not pauses[jd["name"]]["stopped"]:
        with qlock:
            if not queues[jd["name"]]:
                return
            aid = queues[jd["name"]].pop(0)
        try:
            judge_one(jd, aid, replaces)
        except WriteFailed:
            stop_all.set()
            return
        except Exception:
            state["errors"] += 1
            write("events.jsonl", {"utc": now(), "event": "worker error", "answer_id": aid, "judge": jd["name"],
                                   "traceback": openrouter.redact(traceback.format_exc())[-3000:]})


pending = sum(len(q) for q in queues.values())
write("events.jsonl", {"utc": now(), "event": "judging started", "form_version": FORM_VERSION,
                       "answers": len(answers), "pending": pending, "budget": args.budget, "spent_before": spent,
                       **capture_environment([__file__, os.path.join(HERE,"openrouter.py"), os.path.join(HERE,"budget.py"),
                                              os.path.join(HERE,"environment.py")])})
print(f"answers: {len(answers)} | judge requests to make: {pending} | spent so far ${spent:.4f}")
threads = [threading.Thread(target=worker, args=(jd,), daemon=True) for jd in judges for _ in range(args.per_judge)]
for t in threads:
    t.start()
for t in threads:
    t.join()


def finished():
    """(final, valid) sets of (answer_id, judge_cfg) from the judging log as it is now."""
    final, ok = set(), set()
    for j in read_log(os.path.join(JD, "judging.jsonl"))[0]:
        if j["valid"]:
            ok.add((j["answer_id"], j["judge_cfg"]))
        if j["valid"] or j["attempt"] >= 4 or j.get("rejected"):
            final.add((j["answer_id"], j["judge_cfg"]))
    return final, ok


# Backups: an answer that a judge has finished without a valid form goes to that judge's backup (D66).
if not stop_all.is_set() and not APPEND.failed:
    final, ok = finished()
    for jd in judges:
        b = backup_of[jd["name"]]
        queues[b["name"]] = [a for a in order if (a, judge_cfg(jd)) in final and (a, judge_cfg(jd)) not in ok
                             and (a, judge_cfg(b)) not in final]
    need = sum(len(queues[backup_of[jd["name"]]["name"]]) for jd in judges)
    if need:
        write("events.jsonl", {"utc": now(), "event": "backup judges started", "answers": {
            backup_of[jd["name"]]["name"]: len(queues[backup_of[jd["name"]]["name"]]) for jd in judges}})
        print(f"backup judges: {need} answers without a valid form from a main judge")
        threads = [threading.Thread(target=worker, args=(backup_of[jd["name"]], jd["name"]), daemon=True)
                   for jd in judges for _ in range(args.per_judge)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
if APPEND.failed:
    print(f"STOPPED: {APPEND.failed}. Free disk space, then run the same command again to resume.")
    sys.exit(1)
final, valid_final = finished()


def covered(a, jd, pool):
    return (a, judge_cfg(jd)) in pool or (a, judge_cfg(backup_of[jd["name"]])) in pool


left = [(a, jd["name"]) for a in answers for jd in judges
        if (a, judge_cfg(jd)) not in final or ((a, judge_cfg(jd)) not in valid_final
                                               and (a, judge_cfg(backup_of[jd["name"]])) not in final)]
invalid = [(a, jd["name"]) for a in answers for jd in judges if not covered(a, jd, valid_final)]
write("events.jsonl", {"utc": now(), "event": "judging ended",
                       **capture_environment([__file__, os.path.join(HERE,"openrouter.py"), os.path.join(HERE,"budget.py"),
                                              os.path.join(HERE,"environment.py")]), "without_valid_form": len(invalid), "left": len(left), "worker_errors": state["errors"],
                       "spent": round(budget.spent, 4), "known_cost_usd": budget.known_cost,
                       "unknown_cost_attempts": budget.unknown_attempts})
print(f"ended: {len(answers) * len(judges) - len(left)}/{len(answers) * len(judges)} judgments final; "
      f"without valid form {len(invalid)}; worker errors {state['errors']}; spent ${budget.spent:.4f}")
sys.exit(0 if not left and not invalid and not state["errors"] else 1)
