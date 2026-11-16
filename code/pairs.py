"""Draw, step 4: fix the matched control for each target from the author's control screening.

Usage: python3 -I code/pairs.py data/work/draw

Reads <dir>/targets.json, <dir>/control_candidates.json (code/controls.py) and the author's decisions in
<dir>/control_screening.csv. For each target, candidates are taken in their seeded order; the first one included
becomes the control. A target whose listed candidates are all excluded is dropped and logged (Table F1: "If none
qualifies, the pair is dropped"). Writes <dir>/controls.json and <dir>/pairs_log.csv.
"""
import csv, json, os, sys

d = sys.argv[1]
targets = json.load(open(os.path.join(d, "targets.json")))
cands = json.load(open(os.path.join(d, "control_candidates.json")))
mp = os.path.join(d, "control_more.json")
more = json.load(open(mp)) if os.path.exists(mp) else {}
dec = {}
for row in csv.DictReader(open(os.path.join(d, "control_screening.csv"), encoding="utf-8-sig")):
    v = (row["decision (include / exclude)"] or "").strip().lower()
    if v:
        if v not in ("include", "exclude"):
            raise SystemExit(f"target {row['target_rw_record_id']}: decision must be include or exclude")
        dec[(row["target_rw_record_id"], row["doi"])] = (v, row["reason if excluded"].strip())

controls, log, pending = {}, [], []
for t in targets:
    chosen = None
    for c in cands.get(t["id"], []):
        v = dec.get((t["id"], c["doi"]))
        if v is None:
            pending.append((t["id"], c["doi"], c["title"]))
            break
        log.append((t["id"], c["doi"], v[0], v[1]))
        if v[0] == "include":
            chosen = c
            break
    if chosen:
        controls[t["id"]] = chosen
    elif not any(p[0] == t["id"] for p in pending):
        if more.get(t["id"]):
            pending.append((t["id"], "", "all listed candidates excluded: run controls.py with a larger list "
                                         "(third argument, e.g. 6), then screen the new ones"))
        else:
            log.append((t["id"], "", "pair dropped", "no candidate in the seeded sample was included"))

if pending:
    print(len(pending), "control candidates need a decision (in control_screening.csv):")
    for p in pending:
        print("  target", p[0], "|", p[1], "|", p[2][:70])
    sys.exit(1)
json.dump(controls, open(os.path.join(d, "controls.json"), "w"), indent=1, ensure_ascii=False)
with open(os.path.join(d, "pairs_log.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["target_rw_record_id", "control_doi", "outcome", "reason"])
    w.writerows(log)
print("pairs:", len(controls), "of", len(targets), "targets")
