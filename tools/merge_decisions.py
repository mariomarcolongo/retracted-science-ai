"""Write decisions downloaded from the screening page (tools/screen_view.py) back into the screening sheet.

Usage: python3 -I tools/merge_decisions.py SHEET.csv DECISIONS.csv
  e.g. python3 -I tools/merge_decisions.py data/work/draw/screening.csv ~/Downloads/screening_decisions.csv

Fills the decision and reason columns. A row that already has a different decision in the sheet is a conflict:
nothing is written and the conflicts are listed. An exclusion without a reason is refused. A backup of the
sheet is kept next to it (.bak) before it is changed.
"""
import csv, os, shutil, sys

sheet, dec_path = sys.argv[1:3]
DEC, WHY = "decision (include / exclude)", "reason if excluded"
with open(sheet, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    cols, rows = reader.fieldnames, list(reader)
control = "target_rw_record_id" in cols
key = (lambda r: f"{r['target_rw_record_id']}|{r['doi']}") if control else (lambda r: r["rw_record_id"])
by_key = {key(r): r for r in rows}
new = {r["key"]: (r["decision"].strip().lower(), r["reason"].strip())
       for r in csv.DictReader(open(dec_path, encoding="utf-8-sig"))}

problems, changed = [], 0
for k, (d, w) in new.items():
    if k not in by_key:
        problems.append(f"{k}: not in the sheet")
        continue
    if d not in ("include", "exclude"):
        problems.append(f"{k}: decision must be include or exclude")
    if d == "exclude" and not w:
        problems.append(f"{k}: exclusion without a reason")
    r = by_key[k]
    old = (r[DEC] or "").strip().lower()
    if old and (old, (r[WHY] or "").strip()) != (d, w):
        problems.append(f"{k}: the sheet already says '{old}'; the page says '{d}'")
if problems:
    raise SystemExit("Nothing written:\n  " + "\n  ".join(problems))
for k, (d, w) in new.items():
    r = by_key[k]
    if (r[DEC] or "").strip().lower() != d or (r[WHY] or "").strip() != w:
        r[DEC], r[WHY] = d, (w if d == "exclude" else "")
        changed += 1
shutil.copy(sheet, sheet + ".bak")
with open(sheet + ".tmp", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
os.replace(sheet + ".tmp", sheet)
print(f"{changed} decisions written to {sheet} (backup: {sheet}.bak)")
