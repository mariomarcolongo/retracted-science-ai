"""Run the tests and the status question on the tested models (paper sections 3.3, 3.6; D50).

Usage:
  python3 -I code/run_tests.py ITEMS.json LOGDIR --phase pilot|main --budget USD [--models SUBSTR,...]
                               [--tests R1,...,SQ] [--per-model 2] [--reserve 0.25] [--dry [--dry-mode MODE]]

  ITEMS.json  frozen items (code/build_items.py)
  LOGDIR      one directory per run: manifest.json (what this run is), plan.json (the seeded job order),
              http.jsonl (every HTTP attempt: exact body sent, full response or redacted error), runs.jsonl (one
              record per answer attempt), events.jsonl (starts, pauses, stops, errors)
  --roles     tested (default) or aux: the knowledge check (section 3.5), status question only, on the drafter,
              the judges and their backups, with items from code/check_items.py
  --budget    scheduling allowance in USD; every HTTP attempt reserves --reserve, including retries.
              Unknown charges retain the reserve. This is not a guaranteed billing cap.
  --dry       no network: a scripted fake model (modes: normal, tool-loop, empty, ratelimit, error-after-tool)

Resume: the run refuses to continue in a LOGDIR whose manifest differs (items, registry, templates, models with all
their settings in models.json, tests, settings, the reserve, dry or live); jobs with a terminal record are skipped.
A log line that cannot be written (disk full) stops the run; nothing is written after it (D66). Only one process may use a LOGDIR at a time.
Retries (section 3.6): transient HTTP errors are retried inside openrouter.py only (4 attempts per request, the same
conversation turn). A rejected request is terminal ("API error"). An empty answer not caused by the token limit
starts a fresh conversation, up to 4 attempts in all, then is terminal ("missing"). Cut-off answers and refusals
are terminal. Rate limits pause that model without using an attempt (Retry-After respected); a model paused for
more than 45 minutes in all, or any rate limit on a model with a daily limit, stops for this run and resumes later.
Tool limit: the seventh and later calls get the limit message; the next request is sent with tool_choice "none"
(with no tools at all for an endpoint marked "tool_choice_none": false in models.json); if the model still calls a
tool or gives no answer, the job is terminal and not usable ("tool limit exhausted").
Outages: a request still failing after the client's 4 attempts (or with no endpoint available) is not an answer. The
model waits 60 s and the same request is sent again; after 5 such failures in a row the model stops for this run and
its unfinished jobs stay open for a resume. A request the provider rejects (4xx) counts as an API error (missing).
"""
import argparse, datetime, fcntl, hashlib, json, os, platform, random, re, sys, threading, time, traceback, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import materials as M
import openrouter
from budget import RequestBudget, BudgetReached
from logfiles import read_log, Appender, WriteFailed, write_json
from environment import capture_environment

SEED = 20261115
MAX_TOKENS = 16000
MAX_ATTEMPTS = 4
MAX_PAUSE = 45 * 60
HERE = os.path.dirname(os.path.abspath(__file__))
RW_CSV = os.path.join(HERE, "..", "data", "raw", "retraction_watch.csv")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

ap = argparse.ArgumentParser()
ap.add_argument("items"); ap.add_argument("logdir")
ap.add_argument("--phase", required=True)
ap.add_argument("--registry", default=RW_CSV, help="frozen registry CSV; fixtures may use a temporary snapshot")
ap.add_argument("--budget", type=float, default=None)
ap.add_argument("--reserve", type=float, default=0.25)
ap.add_argument("--models", default="")
ap.add_argument("--roles", default="tested", choices=["tested", "aux"],
                help="tested: the nine tested models; aux: knowledge check of the drafter, judges and backups (status question only)")
ap.add_argument("--tests", default=",".join(M.TESTS + ["SQ"]))
ap.add_argument("--per-model", type=int, default=2)
ap.add_argument("--dry", action="store_true")
ap.add_argument("--dry-mode", default="normal", choices=["normal", "tool-loop", "empty", "ratelimit", "error-after-tool",
                                                     "ignore-none", "ignore-none-cut", "outage", "outage-down"])
args = ap.parse_args()
RW_CSV = args.registry
try:
    RequestBudget(args.budget, args.reserve)
except ValueError as e:
    ap.error(str(e))
if not args.dry and args.budget is None:
    raise SystemExit("--budget is required for a live run")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def sha_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


os.makedirs(args.logdir, exist_ok=True)
lockf = open(os.path.join(args.logdir, ".lock"), "w")
try:
    fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("another process is using " + args.logdir)
P = {k: os.path.join(args.logdir, k) for k in ("manifest.json", "plan.json", "http.jsonl", "runs.jsonl", "events.jsonl")}
APPEND = Appender()


def write(key, rec):
    APPEND.write(P[key], rec)


# ---- inputs and manifest ----
items = json.load(open(args.items, encoding="utf-8"))
cfg = json.load(open(os.path.join(HERE, "models.json")))
models = cfg["tested"] if args.roles == "tested" else [cfg["drafter"]] + cfg["judges"] + cfg["backups"]
if args.roles == "aux" and args.tests != "SQ":
    raise SystemExit("the knowledge check (--roles aux) uses only the status question: pass --tests SQ")
if args.models:
    want = [w.strip().lower() for w in args.models.split(",") if w.strip()]
    models = [m for m in models if any(w in m["name"].lower() or w in m["id"].lower() for w in want)]
tests = [t.strip() for t in args.tests.split(",") if t.strip()]
pair_ids = [it["pair_id"] for it in items]
for label, xs in (("pair IDs", pair_ids), ("model names", [m["name"] for m in models]), ("tests", tests)):
    if len(xs) != len(set(xs)):
        raise SystemExit("duplicate " + label)
bad = [t for t in tests if t not in M.TESTS + ["SQ"]]
if bad or not models:
    raise SystemExit(f"unknown tests {bad}" if bad else "no model matches --models")

manifest = {"phase": args.phase, "roles": args.roles, "dry": args.dry, "dry_mode": args.dry_mode if args.dry else None, "seed": SEED,
            "items_sha256": sha_file(args.items), "registry_sha256": sha_file(RW_CSV),
            "materials_sha256": sha_file(os.path.join(HERE, "materials.py")),
            "models": [{k: v for k, v in m.items() if not k.startswith("_")} for m in models], "tests": tests,
            "settings": {"max_tokens": MAX_TOKENS, "tool_limit": M.TOOL_LIMIT, "max_attempts": MAX_ATTEMPTS,
                         "reserve_usd": args.reserve}}
if os.path.exists(P["manifest.json"]):
    old = json.load(open(P["manifest.json"]))
    if old != manifest:
        diff = [k for k in manifest if old.get(k) != manifest[k]]
        raise SystemExit(f"{args.logdir} belongs to a different run (differs in: {', '.join(diff)}); use a new LOGDIR")
else:
    write_json(P["manifest.json"], manifest, indent=1)
MANIFEST_SHA = sha_obj(manifest)
registry = M.Registry(RW_CSV)


# ---- dry run: a scripted model, no network ----
class Fake:
    n = 0
    flock = threading.Lock()

    @classmethod
    def _next(cls):
        with cls.flock:
            cls.n += 1
            return cls.n

    @classmethod
    def _wants_tool(cls, tools, tool_choice, called):
        if not tools or (tool_choice == "none" and args.dry_mode not in ("ignore-none", "ignore-none-cut")):
            return False
        return args.dry_mode in ("tool-loop", "ignore-none", "ignore-none-cut") or not called

    @classmethod
    def _wrap(cls, path, body, log, make):
        n = cls._next()
        uid = "dry-" + uuid.uuid4().hex
        if log:
            log({"uid": uid, "kind": "request", "utc": now(), "attempt": 1, "path": path, "body": body})
        if args.dry_mode == "ratelimit" and n % 7 == 1:
            if log:
                log({"uid": uid, "kind": "error", "utc": now(), "http_status": 429,
                     "error": "dry rate limit", "retried": False})
            e = openrouter.RateLimited("dry rate limit"); e.retry_after = 0.05
            raise e
        down = (args.dry_mode == "outage" and n % 6 == 2) or \
            (args.dry_mode == "outage-down" and body.get("model") == models[0]["id"]
             and not os.environ.get("DRY_PROVIDER_BACK"))  # set on a resume to simulate the provider coming back
        if down:
            if log:
                log({"uid": uid, "kind": "error", "utc": now(), "http_status": 503,
                     "error": "dry provider unavailable", "retried": False})
            raise openrouter.Unavailable("dry: provider unavailable (503)")
        out = make(n)
        if out is None:
            if log:
                log({"uid": uid, "kind": "error", "utc": now(), "http_status": 400,
                     "error": "dry rejected request", "retried": False})
            raise openrouter.CallFailed("dry: request rejected (400)")
        out["id"] = uid
        if log:
            log({"uid": uid, "kind": "response", "utc": now(), "http_status": 200, "seconds": 0.0, "body": out})
        return out, 0.0

    @classmethod
    def chat(cls, model, provider, messages, tools=None, max_tokens=None, response_format=None, tool_choice=None,
             log=None):
        user = next(m["content"] for m in messages if m["role"] == "user")
        doi = user.split("DOI: ", 1)[1].split("\n", 1)[0] if "DOI: " in user else ""
        called = any(m["role"] == "tool" for m in messages)

        def make(n):
            if args.dry_mode == "error-after-tool" and called:
                return None
            if cls._wants_tool(tools, tool_choice, called) and doi:
                msg = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call_{n}", "type": "function",
                       "function": {"name": M.TOOL_NAME, "arguments": json.dumps({"doi": doi})}}]}
                fin = "length" if args.dry_mode == "ignore-none-cut" and tool_choice == "none" else "tool_calls"
                if fin == "length":
                    msg["content"] = "Partial text before the cut"
            else:
                text = "" if args.dry_mode == "empty" else "Dry-run answer citing [S1]."
                msg, fin = {"role": "assistant", "content": text}, "stop"
            return {"id": f"dry-{n}", "model": model, "provider": "dry", "choices": [{"message": msg, "finish_reason": fin}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "cost": 0.001}}
        return cls._wrap("chat/completions", {"model": model, "messages": messages, "tools": tools,
                                               "tool_choice": tool_choice}, log, make)

    @classmethod
    def responses(cls, model, provider, input_items, tools=None, max_output_tokens=None, tool_choice=None, log=None):
        user = next(i["content"] for i in input_items if i.get("role") == "user")
        doi = user.split("DOI: ", 1)[1].split("\n", 1)[0] if "DOI: " in user else ""
        called = any(i.get("type") == "function_call_output" for i in input_items)

        def make(n):
            if args.dry_mode == "error-after-tool" and called:
                return None
            if cls._wants_tool(tools, tool_choice, called) and doi:
                out = [{"type": "reasoning", "id": f"rs_{n}", "summary": []},
                       {"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": M.TOOL_NAME,
                        "arguments": json.dumps({"doi": doi})}]
            else:
                text = "" if args.dry_mode == "empty" else "Dry-run answer citing [S1]."
                out = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]
            return {"id": f"dry-{n}", "model": model, "provider": "dry", "status": "completed", "output": out,
                    "usage": {"input_tokens": 1000, "output_tokens": 100, "cost": 0.001}}
        return cls._wrap("responses", {"model": model, "input": input_items, "tools": tools,
                                       "tool_choice": tool_choice}, log, make)


client = Fake if args.dry else openrouter


# ---- budget, pauses ----
# A crash can leave one incomplete last line in a log; it is moved aside and the repair is logged (D65).
repairs = []
for _key in ("events.jsonl", "http.jsonl", "runs.jsonl"):
    _records, _note = read_log(P[_key])
    if _note:
        repairs.append((_key, _note))
    if _key == "http.jsonl":
        history = _records
    elif _key == "runs.jsonl":
        prior_runs = _records
for _key, _note in repairs:
    write("events.jsonl", {"utc": now(), "event": "log repaired at start", "log": _key, "note": _note})
budget = RequestBudget(args.budget, args.reserve, history)
stop_all = threading.Event()
stopped_models = set()
pause = {m["name"]: {"until": 0.0, "total": 0.0, "n": 0, "outages": 0} for m in models}
OUTAGE_WAIT, OUTAGE_LIMIT = (0.01 if args.dry else 60), 5
plock = threading.Lock()


class ModelStopped(Exception):
    pass


def request(m, fn, *a, context=None, **kw):
    """One API request for model m, with shared pauses on rate limits and the budget check."""
    while True:
        if stop_all.is_set():
            raise BudgetReached("run stopped")
        if m["name"] in stopped_models:
            raise ModelStopped(m["name"])
        with plock:
            wait = pause[m["name"]]["until"] - time.time()
        if wait > 0:
            time.sleep(min(wait, 5))
            continue
        def logged(record):
            budget.observe(record)
            write("http.jsonl", {**record, **(context or {}), "model": m["name"], "model_requested": m["id"],
                                 "provider_requested": m["provider"],
                                 "phase": args.phase, "role": "tested model" if args.roles == "tested" else
                                 ("drafter" if m["id"] == cfg["drafter"]["id"] else "judge"),
                                 "api": m["api"], "dry": args.dry})
        try:
            out = fn(*a, log=logged, **kw)
            with plock:
                pause[m["name"]]["outages"] = 0
            return out
        except openrouter.Unavailable as e:
            with plock:
                p = pause[m["name"]]
                p["outages"] += 1
                n = p["outages"]
                write("events.jsonl", {"utc": now(), "event": "provider unavailable", "model": m["name"],
                                       "in_a_row": n, "detail": openrouter.redact(e)[:300]})
                if n >= OUTAGE_LIMIT:
                    if m["name"] not in stopped_models:
                        stopped_models.add(m["name"])
                        write("events.jsonl", {"utc": now(), "event": "model stopped for this run (provider unavailable)",
                                               "model": m["name"]})
                    raise ModelStopped(m["name"])
            time.sleep(OUTAGE_WAIT)
        except BudgetReached:
            write("events.jsonl", {"utc": now(), "event": "budget reached, run stopped", "spent_usd": budget.spent})
            stop_all.set()
            raise
        except openrouter.RateLimited as e:
            with plock:
                p = pause[m["name"]]
                if time.time() < p["until"]:
                    continue  # another request of this model already started a pause; this one waits with it
                p["n"] += 1
                d = getattr(e, "retry_after", None) or min(30 * 2 ** (p["n"] - 1), 600)
                if m.get("daily_limit") or p["total"] + d > MAX_PAUSE:
                    stopped_models.add(m["name"])
                    write("events.jsonl", {"utc": now(), "event": "model stopped for this run (rate limit)",
                                           "model": m["name"], "paused_s_total": p["total"], "detail": str(e)[:300]})
                    raise ModelStopped(m["name"])
                p["until"], p["total"] = time.time() + d, p["total"] + d
                write("events.jsonl", {"utc": now(), "event": "pause (rate limit)", "model": m["name"],
                                       "seconds": d, "resume_utc": datetime.datetime.fromtimestamp(
                                           p["until"], datetime.timezone.utc).isoformat(timespec="seconds")})


# ---- one conversation ----
def tool_output(name, call_id, raw_args, st):
    st["calls"] += 1
    rec = {"n": st["calls"], "name": name, "call_id": call_id, "arguments": raw_args}
    if st["calls"] > M.TOOL_LIMIT:
        st["refused"] = True
        rec.update(valid=None, refused=True, doi=None, output=M.TOOL_LIMIT_MSG)
    else:
        try:
            a = json.loads(raw_args or "{}")
        except (json.JSONDecodeError, TypeError):
            a = None
        doi = M.Registry.norm(a.get("doi")) if isinstance(a, dict) and isinstance(a.get("doi"), str) else ""
        ok = name == M.TOOL_NAME and bool(call_id) and isinstance(a, dict) and set(a) == {"doi"} and bool(DOI_RE.match(doi))
        out = registry.lookup(doi) if ok else {"error": 'invalid call: use retraction_lookup with {"doi": "<DOI>"}'}
        rec.update(valid=ok, refused=False, doi=doi or None, output=json.dumps(out, ensure_ascii=False))
    st["tool_calls"].append(rec)
    return rec["output"]


def converse(m, system, user, tools_on, st):
    """Fill st (exchanges, tool_calls) as it goes, so nothing is lost if a request fails.
    Returns (answer text, stop reason, refusal text or None, terminal reason or None)."""
    resp_api = m["api"] == "responses"
    if resp_api:
        hist = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tools = M.tools_responses() if tools_on else None
    else:
        hist = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tools = M.tools_chat() if tools_on else None
    while True:
        last_turn = st["refused"]
        # Final turn: tools off. An endpoint that does not accept tool_choice "none" gets no tools instead.
        no_tools = last_turn and m.get("tool_choice_none") is False
        tc = "none" if last_turn and not no_tools else None
        send_tools = None if no_tools else tools
        sent = now()
        if resp_api:
            resp, secs = request(m, client.responses, m["id"], m["provider"], hist, tools=send_tools,
                                 max_output_tokens=MAX_TOKENS, tool_choice=tc, context=st.get("context"))
            st["exchanges"].append({"sent_utc": sent, "received_utc": now(), "seconds": secs, "tool_choice": tc, "tools_sent": bool(send_tools),
                                    "response": resp, **openrouter.usage_fields(resp, "responses")})
            out = resp.get("output") or []
            calls = [o for o in out if o.get("type") == "function_call"]
            text = "".join(c.get("text", "") for o in out if o.get("type") == "message"
                           for c in (o.get("content") or []) if c.get("type") == "output_text")
            refusal = "".join(c.get("refusal", "") for o in out if o.get("type") == "message"
                              for c in (o.get("content") or []) if c.get("type") == "refusal") or None
            reason = resp.get("status")
            if reason == "incomplete":
                reason = "incomplete:" + str((resp.get("incomplete_details") or {}).get("reason"))
            cut = reason == "incomplete:max_output_tokens"
        else:
            resp, secs = request(m, client.chat, m["id"], m["provider"], hist, tools=send_tools, max_tokens=MAX_TOKENS,
                                 tool_choice=tc, context=st.get("context"))
            st["exchanges"].append({"sent_utc": sent, "received_utc": now(), "seconds": secs, "tool_choice": tc, "tools_sent": bool(send_tools),
                                    "response": resp, **openrouter.usage_fields(resp, "chat")})
            ch = (resp.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            calls = msg.get("tool_calls") or []
            content = msg.get("content")
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            text, refusal, reason = content or "", msg.get("refusal") or None, ch.get("finish_reason")
            cut = reason in ("length", "max_tokens")
        if refusal:
            return text, reason, refusal, None
        if last_turn and (calls or not text.strip()):  # checked before the cut-off (D66)
            return text, reason, refusal, "tool limit exhausted"
        if cut:
            return text, reason, refusal, None
        if not calls:
            return text, reason, refusal, None
        if resp_api:
            hist = hist + out
            for c in calls:
                hist.append({"type": "function_call_output", "call_id": c.get("call_id"),
                             "output": tool_output(c.get("name"), c.get("call_id"), c.get("arguments"), st)})
        else:
            back = {"role": "assistant", "content": msg.get("content"), "tool_calls": calls}
            if msg.get("reasoning_details"):
                back["reasoning_details"] = msg["reasoning_details"]
            hist.append(back)
            for c in calls:
                f = c.get("function") or {}
                hist.append({"role": "tool", "tool_call_id": c.get("id"),
                             "content": tool_output(f.get("name"), c.get("id"), f.get("arguments"), st)})


def outcome_of(text, reason, refusal, terminal_reason):
    """(outcome, usable answer?, terminal?) for one finished conversation."""
    cut = str(reason) in ("length", "max_tokens", "incomplete:max_output_tokens")
    if refusal:
        return "refusal (flagged by the API)", False, True
    if terminal_reason:  # the model kept calling the tool or gave nothing: any text is not a final answer
        return terminal_reason, False, True
    if text.strip():
        return ("cut off at token limit" if cut else "complete"), True, True
    if cut:
        return "cut off, no usable text", False, True
    return "empty", False, False


# ---- jobs, resume ----
jobs = []
for it in items:
    for t in tests:
        for side in (["R", "K"] if t == "SQ" else [M.SIDE[t]]):
            for m in models:
                jobs.append((m["name"], it["pair_id"], t, side))
jobs.sort()
random.Random(SEED).shuffle(jobs)
if not os.path.exists(P["plan.json"]):
    write_json(P["plan.json"], [list(j) for j in jobs])

terminal, attempts = set(), {}
if prior_runs:
    for r in prior_runs:
        k = (r["model_name"], r["pair_id"], r["test"], r["side"])
        if r["outcome"] != "interrupted":  # a pause or stop does not use up an attempt
            attempts[k] = max(attempts.get(k, 0), r["attempt"])
        if r["terminal"]:
            terminal.add(k)
item_of = {it["pair_id"]: it for it in items}
by_model = {m["name"]: m for m in models}
queues = {m["name"]: [j for j in jobs if j[0] == m["name"] and j not in terminal] for m in models}
qlock = threading.Lock()
seq = [0]
worker_errors = []


def run_job(job):
    name, pair_id, test, side = job
    m = by_model[name]
    side_item = item_of[pair_id][side]
    if test == "SQ":
        system, user, tools_on = M.render_status(side_item)
    else:
        system, user, tools_on = M.render(test, side_item)
        errs = M.precheck(test, side_item, system, user, tools_on)
        if errs:
            write("events.jsonl", {"utc": now(), "event": "precheck failed, run stopped", "job": job, "errors": errs})
            stop_all.set()
            return
    k = attempts.get(job, 0)
    while k < MAX_ATTEMPTS and not stop_all.is_set():
        k += 1
        with qlock:
            seq[0] += 1
            dispatch = seq[0]
        st = {"calls": 0, "refused": False, "tool_calls": [], "exchanges": []}
        rec = {"manifest_sha256": MANIFEST_SHA, "phase": args.phase, "model_name": name, "model_id": m["id"],
               "provider_requested": m["provider"], "api": m["api"], "pair_id": pair_id, "test": test, "side": side,
               "attempt": k, "dispatch_seq": dispatch, "started_utc": now(), "system": system, "user": user,
               "tools_offered": tools_on}
        st["context"] = {"topic_id": pair_id, "pair_id": pair_id, "test": test, "side": side, "answer_attempt": k}
        try:
            text, reason, refusal, term = converse(m, system, user, tools_on, st)
            outcome, usable, final = outcome_of(text, reason, refusal, term)
            rec.update(answer=text, refusal=refusal, stop_reason=reason, error=None)
        except openrouter.CallFailed as e:
            outcome, usable, final = "API error", False, True
            rec.update(answer="", refusal=None, stop_reason=None, error=openrouter.redact(e)[:1000])
        except (ModelStopped, BudgetReached, openrouter.StopRun) as e:
            if isinstance(e, openrouter.StopRun):
                write("events.jsonl", {"utc": now(), "event": "run stopped (account)", "detail": str(e)[:300]})
                stop_all.set()
            if st["exchanges"]:  # keep what was already paid for; the job is not terminal
                rec.update(answer="", refusal=None, stop_reason=None, error="interrupted: " + type(e).__name__,
                           outcome="interrupted", usable=False, terminal=False, exchanges=st["exchanges"],
                           tool_calls=st["tool_calls"], finished_utc=now())
                write("runs.jsonl", rec)
            raise
        if not final and k >= MAX_ATTEMPTS:
            outcome, final = "missing (empty after 4 attempts)", True
        rec.update(outcome=outcome, usable=usable, terminal=final, exchanges=st["exchanges"],
                   tool_calls=st["tool_calls"], finished_utc=now())
        write("runs.jsonl", rec)
        if final:
            return
        time.sleep(0 if args.dry else 3)


def worker(name):
    while not stop_all.is_set() and name not in stopped_models:
        with qlock:
            if not queues[name]:
                return
            job = queues[name].pop(0)
        try:
            run_job(job)
        except (ModelStopped, BudgetReached, openrouter.StopRun):
            return
        except WriteFailed:
            stop_all.set()
            return
        except Exception:
            worker_errors.append(job)
            write("events.jsonl", {"utc": now(), "event": "worker error (job left unfinished)", "job": job,
                                   "traceback": openrouter.redact(traceback.format_exc())[-3000:]})


pending = sum(len(q) for q in queues.values())
write("events.jsonl", {"utc": now(), "event": "run started", "manifest_sha256": MANIFEST_SHA,
                       "code_sha256": {f: sha_file(os.path.join(HERE, f)) for f in
                                       ("run_tests.py", "openrouter.py", "materials.py")},
                       **capture_environment([os.path.join(HERE, f) for f in
                                               ("run_tests.py", "openrouter.py", "materials.py", "budget.py", "environment.py")]),
                       "jobs_total": len(jobs), "jobs_pending": pending, "budget_usd": args.budget,
                       "spent_before_usd": round(budget.spent, 4)})
print(f"{args.phase}: {len(jobs)} jobs, {len(jobs) - pending} done, {pending} to run; spent so far ${budget.spent:.4f}")
threads = [threading.Thread(target=worker, args=(m["name"],), daemon=True)
           for m in models for _ in range(max(1, args.per_model))]
for t in threads:
    t.start()
while any(t.is_alive() for t in threads):
    time.sleep(0.2 if args.dry else 10)
    if not args.dry:
        print(f"\r{now()[:19]} queued: {sum(len(q) for q in queues.values())} spent: ${budget.spent:.2f}  ",
              end="", flush=True)

if APPEND.failed:
    print(f"\nSTOPPED: {APPEND.failed}. Free disk space, then run the same command again to resume.")
    sys.exit(1)
done = set()
for line in open(P["runs.jsonl"], encoding="utf-8") if os.path.exists(P["runs.jsonl"]) else []:
    r = json.loads(line)
    if r["terminal"]:
        done.add((r["model_name"], r["pair_id"], r["test"], r["side"]))
left = [j for j in jobs if j not in done]
write("events.jsonl", {"utc": now(), "event": "run ended",
                       **capture_environment([os.path.join(HERE, f) for f in
                                               ("run_tests.py", "openrouter.py", "materials.py", "budget.py", "environment.py")]),
                       "jobs_without_terminal_record": len(left),
                       "worker_errors": len(worker_errors), "stopped_models": sorted(stopped_models),
                       "budget_stop": stop_all.is_set(), "spent_usd": round(budget.spent, 4), "known_cost_usd": budget.known_cost,
                       "unknown_cost_attempts": budget.unknown_attempts})
print(f"\nended: {len(jobs) - len(left)}/{len(jobs)} jobs terminal; worker errors {len(worker_errors)}; "
      f"stopped models {sorted(stopped_models) or 'none'}; spent ${budget.spent:.4f}")
sys.exit(0 if not left and not worker_errors else 1)
