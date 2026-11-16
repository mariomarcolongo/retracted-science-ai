"""Knowledge check, step 1: the paper list for the status question asked to the drafter, the judges and their
backups (paper section 3.5, "Choice of drafter and judges"; D56 reversed).

Usage: python3 -I code/check_items.py OUT.json DIR [DIR ...]
  e.g. python3 -I code/check_items.py data/work/check_items.json data/work/draw data/work/pilot

Reads <dir>/targets.json and <dir>/controls.json of every DIR (main draw and pilot: the drafter sees both) and
writes OUT.json in the item format the runner reads for the status question (title and display authors only).
Every target must have its control, and pair IDs must be unique across the directories (D66). Then:
  python3 -I code/run_tests.py data/work/check_items.json data/logs/knowledge_check --phase knowledge_check --roles aux --tests SQ --budget 5
  python3 -I code/judge.py data/work/check_items.json data/logs/knowledge_check --budget 10
  python3 -I code/knowledge_check.py data/logs/knowledge_check
"""
import json, os, sys

if len(sys.argv) < 3:
    raise SystemExit(__doc__)
out, dirs = sys.argv[1], sys.argv[2:]


def side(p):
    a = p.get("authors_display") or []
    if isinstance(a, str):
        a = json.loads(a.replace("'", '"'))
    return {"target": {"title": p["title"], "authors": a, "doi": p["doi"]}}


items = []
for d in dirs:
    targets = json.load(open(os.path.join(d, "targets.json")))
    controls = json.load(open(os.path.join(d, "controls.json")))
    unmatched = [t["id"] for t in targets if t["id"] not in controls]
    if unmatched:
        raise SystemExit(f"{d}: targets without a control: {', '.join(unmatched)}")
    items += [{"pair_id": t["id"], "R": side(t), "K": side(controls[t["id"]])} for t in targets]
ids = [it["pair_id"] for it in items]
if len(ids) != len(set(ids)):
    raise SystemExit("a pair ID occurs in more than one directory")
tmp = out + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(items, f, indent=1, ensure_ascii=False)
os.replace(tmp, out)
print("pairs:", len(items), "| papers:", 2 * len(items), "| from:", ", ".join(dirs))
