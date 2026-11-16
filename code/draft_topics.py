"""Draft and preserve checked topics (paper section 3.4, Appendix B; D26, D54, D61).

Usage: python3 -I code/draft_topics.py DRAW_DIR targets|controls --logdir LOGDIR --budget USD
       python3 -I code/draft_topics.py DRAW_DIR targets|controls --logdir LOGDIR --dry

Cache entries bind the input, drafter configuration, prompt and dry/live mode. A replacement
configuration redrafts the topic and invalidates its old checks. Every HTTP attempt is logged;
--budget is a conservative guard using --reserve per outstanding or unpriced request, not a
hard provider spending limit. Dry mode uses local text and makes no network calls.
Only one drafting process may use a DRAW_DIR at a time (targets and controls share its files). The script exits with
an error when any paper is left without a stored draft (empty or cut-off reply), so the step is run again (D66).
"""
import argparse, csv, datetime, fcntl, hashlib, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openrouter
from materials import clean_abstract
from budget import RequestBudget, BudgetReached
from environment import capture_environment
from logfiles import read_log, Appender, write_json

SEED = 20261115
PROMPT = ("You will read the title and abstract of one research article. Write one sentence that states the research "
          "question it addresses, in general terms, as a topic for a literature review. Name the population, the "
          "intervention or exposure, and the outcome. Do not mention the article's title, authors, study or trial "
          "names, specific numbers, proprietary compound names, or what the study found. Return only the sentence."
          "\n\nTitle: {title}\nAbstract: {abstract}")
CHECKS = ["no names", "no numbers", "no direction of result",
          "population, intervention/exposure and outcome match the abstract", "broad enough for other studies"]


def provenance(cfg, dry):
    return {"model": cfg["id"], "provider": cfg["provider"], "api": cfg.get("api", "chat"),
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "dry": dry}


def cached(entry, doi, title, abstract, source):
    return bool(entry and entry.get("doi") == doi and entry.get("title") == title and
                entry.get("abstract") == abstract and entry.get("provenance") == source)


def keep_checks(old, entry, redrafted):
    return bool(old and not redrafted and old.get("draft topic") == entry["draft"] and
                old.get("title") == entry["title"] and old.get("abstract") == entry["abstract"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory"); ap.add_argument("which", choices=["targets", "controls"])
    ap.add_argument("--logdir", required=True); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--budget", type=float); ap.add_argument("--reserve", type=float, default=0.10)
    args = ap.parse_args()
    if not args.dry and args.budget is None:
        raise SystemExit("--budget is required for live drafting")
    d = args.directory
    lockf = open(os.path.join(d, ".drafting.lock"), "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another drafting process is using " + d + "; run targets and controls one after the other")
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.json")))["drafter"]
    src = provenance(cfg, args.dry)
    os.makedirs(args.logdir, exist_ok=True)
    manifest_path = os.path.join(args.logdir, "manifest.json")
    manifest = {"phase": "drafting", "dry": args.dry}
    if os.path.exists(manifest_path) and json.load(open(manifest_path)) != manifest:
        raise SystemExit("drafting log directory has a different mode; use a new directory")
    write_json(manifest_path, manifest, indent=1)
    http_path = os.path.join(args.logdir, "http.jsonl")
    # a crash can leave one incomplete last line; it is moved aside (D65)
    append = Appender()
    _repairs = [(n, read_log(os.path.join(args.logdir, n))[1]) for n in ("events.jsonl", "drafting.jsonl")]
    history, _note = read_log(http_path)
    _repairs = [(n, x) for n, x in _repairs + [("http.jsonl", _note)] if x]
    guard = RequestBudget(args.budget, args.reserve, history)
    def event(label):
        source_dir = os.path.dirname(os.path.abspath(__file__))
        rec = {"event": label, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               **capture_environment([os.path.join(source_dir, f) for f in
                                     ("draft_topics.py", "openrouter.py", "budget.py", "environment.py")])}
        append.write(os.path.join(args.logdir, "events.jsonl"), rec)
    event("drafting started")
    for _name, _note in _repairs:
        event(f"log repaired at start: {_name}: {_note}")
    store_p = os.path.join(d, "topics_draft.json")
    store = json.load(open(store_p)) if os.path.exists(store_p) else {}
    if args.which == "targets":
        tp = os.path.join(d, "targets.json")
        items = json.load(open(tp)) if os.path.exists(tp) else [r for r in json.load(open(os.path.join(d, "eligible.json")))
                                                               if not r["blocked_by"]]
        papers = [("T" + r["id"], r["doi"], r["title"], clean_abstract(r["abstract"])[0]) for r in items]
    else:
        pairs = json.load(open(os.path.join(d, "controls.json")))
        papers = [("C" + tid, c["doi"], c["title"], clean_abstract(c["abstract"])[0]) for tid, c in pairs.items()]
    redrafted, not_stored = set(), []
    for key, doi, title, abstract in papers:
        if cached(store.get(key), doi, title, abstract, src):
            continue
        # Stop before spending on a topic whose input still discloses the status.
        import re
        if re.search(r"retract|reinstat", title + "\n" + abstract, re.I):
            raise SystemExit("status words remain in topic input; resolve the input before drafting")
        msgs = [{"role": "user", "content": PROMPT.format(title=title, abstract=abstract)}]
        sent = datetime.datetime.now(datetime.timezone.utc).isoformat()
        def log_http(record):
            guard.observe(record)
            rec = {"phase": "drafting", "role": "drafter", "paper": key, "topic_id": key,
                   "model_requested": cfg["id"], "provider_requested": cfg["provider"], **record}
            append.write(http_path, rec)
        try:
            if args.dry:
                text = "How does the exposure affect the outcome in the study population?"
                resp = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                        "model": "dry", "provider": "dry", "usage": {"cost": 0}}
                secs = 0.0
                uid = hashlib.sha256((key + sent).encode()).hexdigest()
                log_http({"uid": uid, "kind": "request", "utc": sent, "attempt": 1,
                          "path": "chat/completions", "body": {"messages": msgs, "model": cfg["id"]}})
                log_http({"uid": uid, "kind": "response", "utc": sent, "seconds": secs,
                          "http_status": 200, "body": resp})
            else:
                resp, secs = openrouter.chat(cfg["id"], cfg["provider"], msgs, max_tokens=4000, log=log_http)
        except (openrouter.StopRun, openrouter.RateLimited, openrouter.CallFailed, BudgetReached) as e:
            event("drafting stopped")
            raise SystemExit("STOPPED: " + str(e))
        text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        rec = {"phase": "drafting", "role": "drafter", "paper": key, "topic_id": key, "doi": doi, "sent_utc": sent,
               "seconds": secs, "model_requested": cfg["id"], "provider_requested": cfg["provider"],
               "dry": args.dry, "request": {"messages": msgs}, "response": resp,
               **openrouter.usage_fields(resp, "chat")}
        append.write(os.path.join(args.logdir, "drafting.jsonl"), rec)
        draft = " ".join(text.split())
        fin = ((resp.get("choices") or [{}])[0]).get("finish_reason")
        if not draft or fin not in ("stop", None):
            print(f"Draft not stored for {key}: empty or cut off; run the step again")
            not_stored.append(key)
            continue
        store[key] = {"doi": doi, "title": title, "abstract": abstract, "draft": draft, "provenance": src}
        redrafted.add(key)
        write_json(store_p, store, indent=1, ensure_ascii=False)
    sheet = os.path.join(d, "topic_check.csv")
    kept = {row["code"]: row for row in csv.DictReader(open(sheet, encoding="utf-8-sig"))} if os.path.exists(sheet) else {}
    rows = []
    for key, v in store.items():
        code = hashlib.sha256(f"{SEED}:{key}".encode()).hexdigest()[:6].upper()
        rows.append((code, key, v))
    rows.sort(key=lambda x: x[0])
    random.Random(SEED).shuffle(rows)
    with open(sheet + ".tmp", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "draft topic", "final topic (edit here if needed)"] + CHECKS + ["note", "title", "abstract"])
        cols = ["final topic (edit here if needed)"] + CHECKS + ["note"]
        for code, key, v in rows:
            old = kept.get(code)
            same = keep_checks(old, v, key in redrafted)
            w.writerow([code, v["draft"]] + [(old[c] if same else "") for c in cols] + [v["title"], v["abstract"]])
    os.replace(sheet + ".tmp", sheet)
    write_json(os.path.join(d, "topic_codes.json"), {code: key for code, key, _ in rows}, indent=1)
    missing = [key for key, doi, title, abstract in papers if not cached(store.get(key), doi, title, abstract, src)]
    event("drafting ended" + (f": {len(missing)} papers without a stored draft" if missing else ""))
    print("drafted:", len(store), "| check sheet:", sheet)
    if missing:
        raise SystemExit(f"NOT COMPLETE: {len(missing)} papers have no stored draft ({', '.join(missing)}); "
                         "run the same command again")


if __name__ == "__main__":
    main()
