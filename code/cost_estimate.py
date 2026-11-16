"""Estimate the complete study cost without network calls (paper section 3.6, Appendix I).

Usage: python3 -I code/cost_estimate.py SNAPSHOT.json [N_PAIRS] [--output ESTIMATE.csv]
       [--models code/models.json] [--endpoints data/snapshots/endpoints] [--pilot-pairs 3]

All ten tests, both status questions, stability repeats, pilot, drafting, the five
auxiliary knowledge checks and two judges are included. Prices used for the budget
come from exact pinned provider tags in the saved endpoint files; catalogue list
prices are reported separately. A missing endpoint is an error, never a cheap fallback.
Token counts and the 3% retry allowance are planning assumptions, not measurements.
Reasoning is budgeted per request, including each tool round. Later rounds include
an assumed 200-token increment of conversation history; caching savings are not assumed.
Auxiliary status questions include main and pilot papers. Drafting includes 10% edits.
An entire replacement drafting run, optional human-check block, unsized preflight and
provider price changes are not priced; measure the pilot before setting live ceilings.
The optional CSV contains estimates, not actual costs. No output is written into data/.
"""
import argparse
import csv
import json
from pathlib import Path

S = {
    "test_input": (2100, 2300, 2600),
    "tool_rounds": (1, 2, 3),
    "answer": (400, 700, 1000),
    "reasoning": {"minimal": (0, 200, 500), "medium": (800, 2000, 4000),
                  "high": (2000, 4000, 8000)},
    "status_input": (80, 100, 120),
    "status_answer": (100, 150, 250),
    "status_reasoning_share": (0.2, 0.3, 0.5),
    "judge_input": (1800, 2300, 3000),
    "judge_output": (300, 1200, 3000),
    "draft_input": (500, 600, 700),
    "draft_output": (1000, 2500, 4000),
}
EFFORT = {"google/gemini-3.5-flash-lite": "minimal",
          "anthropic/claude-sonnet-5.5": "high",
          "deepseek/deepseek-v4.1-flash-1017": "high",
          "baidu/ernie-5.5-flash-preview:free": "high"}
RETRY = 1.03
TESTS = ("R1", "R2", "R3", "R4", "R5", "R6", "K3", "K4", "R4-I", "K4-I")
FIELDS = ("scenario", "phase", "source_phase", "role", "model_id", "provider", "test",
          "answers", "requests", "input_tokens", "output_tokens", "estimate_usd",
          "list_price_usd", "input_price_per_token", "output_price_per_token", "price_source")


def load_prices(snapshot, config, endpoint_dir):
    """Resolve the exact endpoint, retaining the catalogue rate for comparison."""
    raw = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    catalogue = {m["id"]: m["pricing"] for m in (raw["data"] if isinstance(raw, dict) else raw)}
    prices = {}
    models = config["tested"] + [config["drafter"]] + config["judges"] + config["backups"]
    for m in models:
        mid = m["id"]
        path = Path(endpoint_dir) / (mid.replace("/", "_").replace(":", "_") + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        endpoints = data.get("data", data)["endpoints"]
        matches = [e for e in endpoints if e.get("tag") == m["provider"] and not e.get("service_tier")]
        if len(matches) != 1:
            raise ValueError(f"need exactly one standard endpoint for {mid} / {m['provider']}")
        p, q = matches[0]["pricing"], catalogue[mid]
        prices[mid] = {"input": float(p["prompt"]), "output": float(p["completion"]),
                       "list_input": float(q["prompt"]), "list_output": float(q["completion"]),
                       "source": path.name + "#" + m["provider"]}
    return prices


def estimate(config, prices, pairs=25, pilot_pairs=3):
    """Return one auditable estimate row per scenario, phase, model and test."""
    if pairs < 1 or pilot_pairs < 0:
        raise ValueError("pairs must be positive and pilot pairs nonnegative")
    rows = []
    for k, scenario in enumerate(("low", "mid", "high")):
        def add(model, phase, role, test, n, inp, out, rounds=1, source_phase=""):
            if n == 0:
                return
            p = prices[model["id"]]
            input_tokens, output_tokens = n * inp * RETRY, n * out * RETRY
            rows.append(dict(scenario=scenario, phase=phase, source_phase=source_phase,
                             role=role, model_id=model["id"], provider=model["provider"], test=test,
                             answers=n, requests=n * rounds * RETRY,
                             input_tokens=input_tokens, output_tokens=output_tokens,
                             estimate_usd=input_tokens*p["input"] + output_tokens*p["output"],
                             list_price_usd=input_tokens*p["list_input"] + output_tokens*p["list_output"],
                             input_price_per_token=p["input"], output_price_per_token=p["output"],
                             price_source=p["source"]))
        scored = []
        for m in config["tested"]:
            reasoning = S["reasoning"][EFFORT.get(m["id"], "medium")][k]
            for phase, n, tests in (("main run", pairs, TESTS),
                                    ("pilot", pilot_pairs, TESTS),
                                    ("stability", 2 * min(5, pairs), ("R3", "R4", "R5", "R6", "K3", "K4"))):
                for test in tests:
                    rounds = 1 if test in ("R1", "R2") else S["tool_rounds"][k]
                    inp = rounds*S["test_input"][k] + 200*rounds*(rounds-1)/2
                    out = S["answer"][k] + rounds*reasoning + 200*(rounds-1)
                    actual_phase = "instruction test" if phase == "main run" and test.endswith("-I") else phase
                    add(m, actual_phase, "tested model", test, n, inp, out, rounds)
                    scored.append((actual_phase, test, n))
            for phase, n in (("main run", 2*pairs), ("pilot", 2*pilot_pairs)):
                add(m, phase, "tested model", "status question", n, S["status_input"][k],
                    S["status_answer"][k] + reasoning*S["status_reasoning_share"][k])
                scored.append((phase, "status question", n))
        auxiliaries = [config["drafter"]] + config["judges"] + config["backups"]
        for m in auxiliaries:
            n = 2*(pairs + pilot_pairs)
            # No auxiliary reasoning-class measurement exists: conservative high-class assumption.
            out = S["status_answer"][k] + S["reasoning"]["high"][k]*S["status_reasoning_share"][k]
            add(m, "knowledge check", "drafter" if m == config["drafter"] else "judge",
                "status question", n, S["status_input"][k], out)
            scored.append(("knowledge check", "status question", n))
        add(config["drafter"], "drafting", "drafter", "", 2*(pairs+pilot_pairs)*1.1,
            S["draft_input"][k], S["draft_output"][k])
        counts = {}
        for phase, test, n in scored:
            counts[(phase, test)] = counts.get((phase, test), 0) + n
        for m in config["judges"]:
            for (phase, test), n in sorted(counts.items()):
                add(m, "judging", "judge", test, n, S["judge_input"][k],
                    S["judge_output"][k], source_phase=phase)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("pairs", type=int, nargs="?", default=25)
    parser.add_argument("--models", default=str(Path(__file__).with_name("models.json")))
    parser.add_argument("--endpoints", default=str(Path(__file__).resolve().parents[1]/"data/snapshots/endpoints"))
    parser.add_argument("--pilot-pairs", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.models).read_text(encoding="utf-8"))
        prices = load_prices(args.snapshot, config, args.endpoints)
        rows = estimate(config, prices, args.pairs, args.pilot_pairs)
        if args.output:
            dest = Path(args.output).resolve()
            data_dir = Path(__file__).resolve().parents[1]/"data"
            if dest == data_dir or data_dir in dest.parents:
                raise ValueError("estimate output must be outside data/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
        print("Planning assumptions only; pinned endpoint prices; 3% request-retry allowance.")
        print("All ten tests, main/pilot status questions, five auxiliary checks, drafting and judging included.")
        print("Reasoning budgeted per request; auxiliary reasoning assumed high; no cache savings.")
        print("Unpriced: unsized preflight, a full replacement drafting run, provider price changes.")
        for scenario in ("low", "mid", "high"):
            selected = [r for r in rows if r["scenario"] == scenario]
            print(f"\n{scenario}: N={args.pairs}, pilot={args.pilot_pairs}")
            for phase in sorted({r["phase"] for r in selected}):
                print(f"  {phase:20s} ${sum(r['estimate_usd'] for r in selected if r['phase']==phase):.2f}")
            print(f"  TOTAL                ${sum(r['estimate_usd'] for r in selected):.2f}")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
