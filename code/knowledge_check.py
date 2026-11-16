"""Apply the complete knowledge-check replacement rule (paper section 3.5; D61).

Usage: python3 -I code/knowledge_check.py RUNDIR [--judging JUDGING_DIR]

Requires a complete auxiliary SQ plan, both sides of every planned paper pair, and two
content-bound valid judgments for every usable answer. Dry runs use judging-dry by default.
The author settles status disagreements in knowledge_decisions.csv; neutral codes bind
both answer content and judging configuration. No output is approved while labels are
missing. Exactly ten percentage points is kept, using integer arithmetic at the boundary.

Status-question rules (D66, as in outcomes.py): an answer calls the paper retracted only if it asserts "retracted"
with no conflicting status claims; a refusal or a missing answer is no answer. Percentages use answered papers only.
A model is "replace" if the answered papers exceed ten points; "keep" only if it stays at or under ten points even
when every unanswered retracted paper counts as called retracted and every unanswered control as not; otherwise
"undetermined": run the missing answers again or replace the model.
"""
import argparse, csv, hashlib, json, os, sys

SEED = 20261115
STATUSES = ["retracted", "reinstated", "not retracted", "other notice", "uncertain", "not stated"]
LABELS = ["called retracted", "not called retracted", "refusal"]


def label(form):
    """The knowledge-check label of one judge's form (status-question rules)."""
    if form.get("refusal"):
        return "refusal"
    if form.get("asserted_status") == "retracted" and not form.get("conflicting_assertions"):
        return "called retracted"
    return "not called retracted"


def decide(yes_r, n_r, missing_r, yes_k, n_k, missing_k):
    """replace / keep / undetermined, from answered papers and the worst case for the unanswered ones."""
    if n_r and n_k and exceeds_threshold(yes_r, n_r, yes_k, n_k):
        return "replace"
    if not exceeds_threshold(yes_r + missing_r, n_r + missing_r, yes_k, n_k + missing_k):
        return "keep"
    return "undetermined"


def answer_id(r):
    value = json.dumps([r["manifest_sha256"], r["model_id"], r["provider_requested"], r["pair_id"], r["test"], r["side"],
                        r["attempt"], r["tools_offered"], r["system"], r["user"], r["answer"]])
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def exceeds_threshold(yes_r, n_r, yes_k, n_k):
    if n_r <= 0 or n_k <= 0:
        raise ValueError("both paper groups must be nonempty")
    return 10 * (yes_r * n_k - yes_k * n_r) > n_r * n_k


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def complete_runs(directory):
    manifest = json.load(open(os.path.join(directory, "manifest.json")))
    if manifest.get("roles") != "aux" or manifest.get("tests") != ["SQ"]:
        raise SystemExit("knowledge check requires an auxiliary status-question run")
    plan = [tuple(x) for x in json.load(open(os.path.join(directory, "plan.json")))]
    if not plan or len(plan) != len(set(plan)):
        raise SystemExit("knowledge plan is empty or has duplicates")
    models = {m["name"] for m in manifest["models"]}
    configs = {m["name"]: m for m in manifest["models"]}
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    pairs = {p for _, p, _, _ in plan}
    expected = {(m, p, "SQ", s) for m in models for p in pairs for s in ("R", "K")}
    if set(plan) != expected:
        raise SystemExit("knowledge plan must cover both sides for every model and pair")
    final = {}
    for r in read_jsonl(os.path.join(directory, "runs.jsonl")):
        key = (r["model_name"], r["pair_id"], r["test"], r["side"])
        if key not in expected:
            raise SystemExit("run record is not in the knowledge-check plan")
        cfg = configs[r["model_name"]]
        if r.get("manifest_sha256") != manifest_hash or r.get("model_id") != cfg["id"] or \
                r.get("provider_requested") != cfg["provider"]:
            raise SystemExit("knowledge answer does not match its manifest configuration")
        if r["terminal"]:
            if key in final:
                raise SystemExit("duplicate terminal answer in knowledge check")
            final[key] = r
    if set(final) != expected:
        raise SystemExit(f"knowledge check incomplete: {len(expected - set(final))} planned answers remain")
    return manifest, final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory"); ap.add_argument("--judging")
    args = ap.parse_args()
    d = args.directory
    manifest, final = complete_runs(d)
    jd = args.judging or os.path.join(d, "judging-dry" if manifest.get("dry") else "judging")
    jm = json.load(open(os.path.join(jd, "manifest.json")))
    if jm.get("dry") != manifest.get("dry") or jm.get("items_sha256") != manifest.get("items_sha256"):
        raise SystemExit("judging manifest does not match the knowledge run")
    judges = jm["judges"]
    if len(judges) != 2 or len({j["name"] for j in judges}) != 2:
        raise SystemExit("knowledge check requires two distinct judges")
    config = {j["name"]: hashlib.sha256(json.dumps([j["id"], j["provider"], jm["form_version"]]).encode()).hexdigest()[:12]
              for j in judges}
    backups = {b["name"]: (hashlib.sha256(json.dumps([b["id"], b["provider"], jm["form_version"]]).encode()).hexdigest()[:12],
                           b["backup_for"]) for b in jm.get("backups", []) if b["backup_for"] in config}
    forms, backup_forms = {}, {}
    for j in read_jsonl(os.path.join(jd, "judging.jsonl")):
        name = j.get("judge")
        main_form = j.get("valid") and j.get("judge_cfg") == config.get(name)
        backup_form = j.get("valid") and name in backups and j.get("judge_cfg") == backups[name][0] \
            and j.get("replaces") == backups[name][1]
        if main_form or backup_form:
            if j["form"].get("asserted_status") not in STATUSES:
                raise SystemExit("invalid asserted status in a judgment")
        if main_form:
            forms.setdefault(j["answer_id"], {})[name] = label(j["form"])
        elif backup_form:  # a backup's form takes the place of a judge that could not score the answer (D66)
            backup_forms.setdefault(j["answer_id"], {})[backups[name][1]] = label(j["form"])
    for aid, slots in backup_forms.items():
        for slot, value in slots.items():
            forms.setdefault(aid, {}).setdefault(slot, value)
    dec_path = os.path.join(d, "knowledge_decisions.csv")
    old = {}
    if os.path.exists(dec_path):
        for row in csv.DictReader(open(dec_path, encoding="utf-8-sig")):
            if row["code"] in old:
                raise SystemExit("duplicate knowledge decision code")
            value = (next((v for k, v in row.items() if k and k.startswith("decision")), "") or "").strip().lower()
            if value and value not in LABELS:
                raise SystemExit("decision must be one of " + ", ".join(LABELS))
            old[row["code"]] = value
    statuses, decisions, pending = {}, [], 0
    for key, r in sorted(final.items()):
        if not r["usable"]:
            statuses[key] = "no answer"
            continue
        aid = answer_id(r)
        f = forms.get(aid, {})
        if set(f) != set(config):
            raise SystemExit("knowledge check needs two valid current judgments for every usable answer")
        values = set(f.values())
        if len(values) == 1:
            statuses[key] = next(iter(values))
            continue
        code = hashlib.sha256(json.dumps([SEED, aid, sorted(config.items()), sorted(f.items())]).encode()).hexdigest()[:12].upper()
        choice = old.get(code, "")
        decisions.append([code, r["user"], r["answer"], " / ".join(f[n] for n in sorted(f)), choice])
        if choice:
            statuses[key] = choice
        else:
            pending += 1
    if decisions:
        with open(dec_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["code", "question", "answer", "judges",
                                           "decision (" + " / ".join(LABELS) + ")"])
            w.writerows(sorted(decisions))
    if pending:
        raise SystemExit(f"{pending} answers need a decision in {dec_path}")
    rows = []
    pct = lambda a, b: round(100 * a / b, 1) if b else ""
    for m in sorted({k[0] for k in final}):
        answered = {s: [v for k, v in statuses.items() if k[0] == m and k[3] == s and v not in ("no answer", "refusal")]
                    for s in "RK"}
        missing = {s: sum(k[0] == m and k[3] == s and v in ("no answer", "refusal") for k, v in statuses.items())
                   for s in "RK"}
        n = {s: len(answered[s]) for s in "RK"}
        yes = {s: answered[s].count("called retracted") for s in "RK"}
        diff = round(100 * (yes["R"] / n["R"] - yes["K"] / n["K"]), 1) if n["R"] and n["K"] else ""
        rows.append([m, n["R"], yes["R"], pct(yes["R"], n["R"]), missing["R"], n["K"], yes["K"], pct(yes["K"], n["K"]),
                     missing["K"], diff, decide(yes["R"], n["R"], missing["R"], yes["K"], n["K"], missing["K"])])
    with open(os.path.join(d, "knowledge_check.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "retracted papers answered", "called retracted", "retracted percent",
                    "retracted papers without answer", "control papers answered", "controls called retracted",
                    "control percent", "control papers without answer", "difference (points)", "decision"])
        w.writerows(rows)
    for r in rows:
        print(f"{r[0]:28s} retracted {r[2]}/{r[1]} ({r[3]}%; {r[4]} unanswered) | controls {r[6]}/{r[5]} "
              f"({r[7]}%; {r[8]} unanswered) | {r[9]} points -> {r[10]}")


if __name__ == "__main__":
    main()
