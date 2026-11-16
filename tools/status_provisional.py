"""Provisional status-question table (paper section 4.1), counted directly from the judge forms.

Usage: python3 -I tools/status_provisional.py   (reads data/logs/status-question and status-question-deepseek)
A label counts only where both judges give the same one; other answers are "disputed". Rules as in the paper:
refusal; conflicting claims = uncertain; uncertain or not stated = uncertain; reinstated or other notice = other.
Not the study's scoring pipeline: no adjudication, no human check, no intervals.
"""
import collections, json
COLS = ["retracted", "not retracted", "uncertain", "other", "refusal", "disputed", "no answer"]


def label(f):
    if f["refusal"]:
        return "refusal"
    if f["conflicting_assertions"]:
        return "uncertain"
    a = f["asserted_status"]
    return a if a in ("retracted", "not retracted") else "uncertain" if a in ("uncertain", "not stated") else "other"


def table():
    out = collections.defaultdict(collections.Counter)
    for d in ("status-question", "status-question-deepseek"):
        runs, forms = {}, collections.defaultdict(dict)
        for line in open(f"data/logs/{d}/runs.jsonl"):
            r = json.loads(line)
            if r["terminal"]:
                runs[(r["model_name"], r["pair_id"], r["side"])] = r
        for line in open(f"data/logs/{d}/judging/judging.jsonl"):
            j = json.loads(line)
            if j["valid"]:
                m, p, _, s, _ = j["answer_key"]
                forms[(m, p, s)][j["judge"]] = j["form"]
        for (m, p, s), r in runs.items():
            if not r["usable"]:
                out[(m, s)]["no answer"] += 1
                continue
            labels = {label(f) for f in forms[(m, p, s)].values()}
            out[(m, s)][labels.pop() if len(forms[(m, p, s)]) == 2 and len(labels) == 1 else "disputed"] += 1
    return out


if __name__ == "__main__":
    print("| Model | Papers | " + " | ".join(COLS) + " |\n|" + "---|" * (len(COLS) + 2))
    for (m, s), c in sorted(table().items()):
        print(f"| {m} | {'retracted' if s == 'R' else 'control'} | " + " | ".join(str(c[x]) for x in COLS) + " |")
