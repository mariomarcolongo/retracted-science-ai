"""Draw, step 2: apply the author's hand-screening decisions and fix the retracted targets.

Usage: python3 -I code/draw_screen.py data/work/draw

Reads <dir>/eligible.json (code/draw.py) and the author's decisions in <dir>/screening.csv
("include" or "exclude", with a reason for exclusions). Walks the seeded order again:
  - a paper whose journal or author group is already taken by an included paper is skipped;
  - an included paper is accepted, up to 40;
  - an excluded paper is logged and frees its journal and authors for the next paper in the order;
  - a paper with no decision yet that would be reached is listed as "screen next".
When nothing is left to screen, writes <dir>/targets.json and <dir>/screening_log.csv.
"""
import csv, json, os, sys

d = sys.argv[1]
MAX_PAIRS = int(sys.argv[2]) if len(sys.argv) > 2 else 40  # pilot: 3
order = json.load(open(os.path.join(d, "eligible.json")))
dec = {}
for row in csv.DictReader(open(os.path.join(d, "screening.csv"), encoding="utf-8-sig")):
    v = (row["decision (include / exclude)"] or "").strip().lower()
    if v:
        if v not in ("include", "exclude"):
            raise SystemExit(f"rank {row['rank']}: decision must be include or exclude, not {v!r}")
        if v == "exclude" and not row["reason if excluded"].strip():
            raise SystemExit(f"rank {row['rank']}: an exclusion needs a reason")
        dec[row["rw_record_id"]] = (v, row["reason if excluded"].strip())


def taken(r, accepted):
    for a in accepted:
        if a["journal"].lower() == r["journal"].lower():
            return f"journal of rank {a['rank']}"
        if set(r["author_names"]) & set(a["author_names"]) or set(r["author_ids"]) & set(a["author_ids"]):
            return f"author group of rank {a['rank']}"
    return ""


accepted, log, pending = [], [], []
for r in order:
    if len(accepted) >= MAX_PAIRS:
        break
    why = taken(r, accepted + pending)
    if why:
        log.append((r["rank"], r["id"], "skipped", why))
        continue
    v = dec.get(r["id"])
    if v is None:
        pending.append(r)
    elif v[0] == "include":
        accepted.append(r)
        log.append((r["rank"], r["id"], "included", ""))
    else:
        log.append((r["rank"], r["id"], "excluded by hand", v[1]))

if pending:
    print(f"{len(pending)} papers still need a decision (screen these next, in screening.csv):")
    for r in pending:
        print(f"  rank {r['rank']:4d}  record {r['id']}  {r['journal'][:40]}  {r['title'][:70]}")
    sys.exit(1)

json.dump(accepted, open(os.path.join(d, "targets.json"), "w"), indent=1, ensure_ascii=False)
with open(os.path.join(d, "screening_log.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank", "rw_record_id", "outcome", "reason"])
    w.writerows(log)
print("targets fixed:", len(accepted), "| excluded by hand:", sum(1 for x in log if x[2] == "excluded by hand"))
