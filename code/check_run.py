"""Check the logs of a run for problems that only show up with real models (paper section 3.6, D68).

Usage: python3 -I code/check_run.py LOGDIR [--endpoints data/snapshots/endpoints]

  LOGDIR       a run directory written by code/run_tests.py (manifest.json, plan.json, http.jsonl, runs.jsonl)
  --endpoints  the saved endpoint lists with the pinned prices (default: data/snapshots/endpoints of this repository)

Run it after the first live run and after the pilot, before the next paid step. It only reads; it writes no file.
Every model of the run gets five lines, each PASS, FAIL or NOTE (a NOTE is information, not a failure):
1. Service tier: "default" is reported as standard; a missing/null field leaves the tier unverified (NOTE).
   An explicitly different tier is a failure. Requested routing alone is not evidence of the served tier.
2. One provider and model: the provider and model names the responses report. More than one provider is a failure.
3. Price: the summed charge against input tokens x prompt price + output tokens x completion price of the pinned
   endpoint (snapshot file <model id with "/" and ":" as "_">.json). A ratio below 0.7 or above 1.3 requires
   investigation; it does not identify a tier. Cached input discounts are not included in this estimate.
4. Tool calls work end to end: in conversations that offered the lookup tool, did the model call it, and did those
   conversations end with a usable answer? A request rejected after a tool call ("API error") is a failure: the
   conversation sent back with the tool result was refused (for GPT-6, the Responses API replay risk). A model
   that never calls the tool is a NOTE only, since unprompted lookup is what the study measures.
5. Summary: answers finished out of those planned, usable answers, and the count of each outcome.
A dry run (--dry, the scripted model) has no real tiers, providers or prices: checks 1-3 are skipped with a NOTE.

Exit status: 0 no FAIL (NOTEs may leave checks unverified); 1 at least one FAIL; 2 invalid run directory.
"""
import argparse, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logfiles import read_log

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINTS = os.path.join(HERE, "..", "data", "snapshots", "endpoints")
FILES = ("manifest.json", "plan.json", "http.jsonl", "runs.jsonl")
OWNER = "the test run (run_tests.py)"
LOW, HIGH = 0.7, 1.3


def counts(counter):
    """'flex 3, priority 1' for a Counter."""
    return ", ".join(f"{k} {n}" for k, n in sorted(counter.items()))


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def missing_files(logdir):
    return [f for f in FILES if not os.path.exists(os.path.join(logdir, f))]


def pinned_prices(m, endpoints_dir):
    """(prompt, completion) price in USD per token of the model's pinned endpoint; None if no snapshot has it."""
    path = os.path.join(endpoints_dir, m["id"].replace("/", "_").replace(":", "_") + ".json")
    if not os.path.exists(path):
        return None
    data = json.load(open(path, encoding="utf-8"))
    for e in data.get("endpoints") or (data.get("data") or {}).get("endpoints") or []:
        if str(e.get("tag", "")).lower() == m["provider"].lower():
            return float(e["pricing"]["prompt"]), float(e["pricing"]["completion"])
    return None


def tier_check(bodies):
    if not bodies:
        return "NOTE", "no response was logged, so there is no tier to check"
    other = Counter(str(b["service_tier"]) for b in bodies if b.get("service_tier") not in (None, "default"))
    if other:
        return "FAIL", (f"{sum(other.values())} of {len(bodies)} responses did not come from the standard tier "
                        f"({counts(other)}); the study pins the standard tier")
    unknown = sum(b.get("service_tier") is None for b in bodies)
    if unknown:
        return "NOTE", f"{unknown} of {len(bodies)} responses omit the service tier; served tier not fully verified"
    return "PASS", f"all {len(bodies)} responses came from the standard tier"


def provider_check(bodies, m):
    providers = Counter(str(b["provider"]) for b in bodies if b.get("provider"))
    served = Counter(str(b["model"]) for b in bodies if b.get("model"))
    if len(providers) > 1:
        return "FAIL", f"more than one provider answered ({counts(providers)}); pinned endpoint: {m['provider']}"
    return "NOTE", (f"provider returned: {counts(providers) or 'none named'}; model returned: "
                    f"{counts(served) or 'none named'}; pinned endpoint: {m['provider']}")


def price_check(bodies, m, endpoints_dir):
    prices = pinned_prices(m, endpoints_dir)
    if prices is None:
        return "NOTE", f"no snapshot of the pinned endpoint ({m['id']} at {m['provider']}); price not checked"
    if prices == (0.0, 0.0):
        return "NOTE", "free endpoint, not checked"
    keys = ("input_tokens", "output_tokens") if m.get("api") == "responses" else ("prompt_tokens", "completion_tokens")
    n, charged, expected = 0, 0.0, 0.0
    for b in bodies:
        u = b.get("usage") or {}
        cost, tokens_in, tokens_out = u.get("cost"), u.get(keys[0]), u.get(keys[1])
        if number(cost) and number(tokens_in) and number(tokens_out):
            n, charged = n + 1, charged + cost
            expected += tokens_in * prices[0] + tokens_out * prices[1]
    if not n or expected <= 0:
        return "NOTE", "no priced responses (none reports both a cost and token counts); price not checked"
    ratio = charged / expected
    text = f"charged ${charged:.4f} for {n} responses, expected ${expected:.4f} at the pinned prices: ratio {ratio:.2f}"
    if LOW <= ratio <= HIGH:
        return ("PASS", text) if n == len(bodies) else (
            "NOTE", f"{text}; {len(bodies)-n} responses lack usable cost/token data, so price coverage is incomplete")
    return "FAIL", (f"{text}, outside {LOW}-{HIGH}. Investigate cached input tokens, discounts, pricing changes "
                    "and routing before continuing; this ratio does not establish the service tier")


def tool_check(terminal):
    offered = [r for r in terminal if r.get("tools_offered")]
    called = [r for r in offered if r.get("tool_calls")]
    usable = sum(bool(r.get("usable")) for r in called)
    rejected = [r for r in called if r.get("outcome") == "API error"]
    if rejected:
        return "FAIL", (f"{len(rejected)} conversation(s) ended in an API error after the model had called the tool: "
                        "the request sent after a tool result was rejected (for GPT-6, the Responses API replay "
                        f"risk). First error: {str(rejected[0].get('error'))[:300]}")
    if len(called) >= 3 and not usable:
        return "FAIL", (f"the model called the tool in {len(called)} conversations and none of them ended with a "
                        "usable answer")
    if not offered:
        return "NOTE", "no finished conversation offered the tool, so tool calls were not exercised"
    if not called:
        return "NOTE", (f"the model never called the tool in {len(offered)} conversations that offered it. Not a "
                        "failure (unprompted lookup is what the study measures), but the tool path stays untested")
    text = (f"the model called the tool in {len(called)} of {len(offered)} conversations that offered it; "
            f"{usable} of those ended with a usable answer")
    valid_usable = sum(bool(r.get("usable")) and any(
        c.get("valid") is True and not c.get("refused") for c in r.get("tool_calls", [])) for r in called)
    if usable and not valid_usable:
        return "NOTE", text + "; no usable conversation included a valid, non-refused lookup"
    return ("PASS", text) if usable else ("NOTE", text + " (too few to judge)")


def summary(terminal, planned):
    jobs = {(r.get("pair_id"), r.get("test"), r.get("side")) for r in terminal}
    outcomes = Counter(str(r.get("outcome")) for r in terminal)
    status = "NOTE" if len(jobs) == planned and len(terminal) == planned else "FAIL"
    return status, (f"{len(jobs)} of {planned} planned answers finished, {sum(bool(r.get('usable')) for r in terminal)} "
                    f"usable; outcomes: {counts(outcomes) or 'none'}" +
                    ("; incomplete run or duplicate terminal records" if status == "FAIL" else ""))


def check(logdir, endpoints_dir=ENDPOINTS):
    """All checks for one run directory. Returns (lines to print, number of failed checks)."""
    manifest = json.load(open(os.path.join(logdir, "manifest.json"), encoding="utf-8"))
    names = [m["name"] for m in manifest["models"]]
    if len(names) != len(set(names)):
        raise ValueError("duplicate model names in manifest would mix model logs")
    plan = json.load(open(os.path.join(logdir, "plan.json"), encoding="utf-8"))
    http, _ = read_log(os.path.join(logdir, "http.jsonl"), repair=False, owner=OWNER)
    runs, _ = read_log(os.path.join(logdir, "runs.jsonl"), repair=False, owner=OWNER)
    dry = bool(manifest.get("dry"))
    lines = [f"Run {logdir}: phase {manifest.get('phase')}, " +
             ("dry run (scripted model, no network)" if dry else "live run") + f", {len(manifest['models'])} model(s)"]
    failures = 0
    for m in manifest["models"]:
        bodies = [h["body"] for h in http if h.get("kind") == "response" and h.get("model") == m["name"]
                  and isinstance(h.get("body"), dict)]
        terminal = [r for r in runs if r.get("model_name") == m["name"] and r.get("terminal")]
        if dry:
            results = [("NOTE", "checks 1-3 (service tier, provider, price) skipped: a dry run has no real responses")]
        else:
            results = [(s, "1 service tier: " + t) for s, t in [tier_check(bodies)]]
            results += [(s, "2 provider and model: " + t) for s, t in [provider_check(bodies, m)]]
            results += [(s, "3 price: " + t) for s, t in [price_check(bodies, m, endpoints_dir)]]
        results += [(s, "4 tool calls: " + t) for s, t in [tool_check(terminal)]]
        results += [(s, "5 summary: " + t) for s, t in [summary(terminal, sum(j[0] == m["name"] for j in plan))]]
        lines += ["", f"{m['name']} ({m['id']})"] + [f"  {status}  {text}" for status, text in results]
        failures += sum(status == "FAIL" for status, _ in results)
    return lines, failures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logdir")
    ap.add_argument("--endpoints", default=ENDPOINTS, help="directory with the saved endpoint lists (pinned prices)")
    args = ap.parse_args(argv)
    missing = missing_files(args.logdir)
    if missing:
        print(f"{args.logdir} is not a complete run directory of code/run_tests.py: missing {', '.join(missing)}")
        return 2
    try:
        lines, failures = check(args.logdir, args.endpoints)
    except (ValueError, KeyError, OSError) as exc:
        print(f"Invalid run directory: {exc}")
        return 2
    print("\n".join(lines) + "\n")
    if failures:
        print(f"RESULT: {failures} check(s) FAILED — do not start the next paid step before these are understood")
    else:
        print("RESULT: no failed checks; review NOTE entries for unverified checks before the next paid step")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
