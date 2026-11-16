"""Second pass for ref_check.json: retry arXiv and Semantic Scholar slowly; add title searches for arXiv-only items.
DBLP is skipped (it currently serves a bot check). Usage: python3 -I tools/ref_check_retry.py data/work/ref_check.json"""
import json, sys, time, importlib.util
spec = importlib.util.spec_from_file_location("rc", "tools/ref_check.py")
src = open("tools/ref_check.py", encoding="utf-8").read().split("refs = json.load")[0]
rc = {}; exec(compile(src, "ref_check.py", "exec"), rc)
p = sys.argv[1]; R = json.load(open(p, encoding="utf-8"))
time.sleep(60)
for r in R:
    i = r["input"]
    if i.get("arxiv") and (r.get("arxiv") or {}).get("error"):
        for k in range(5):
            a = rc["arxiv"](i["arxiv"])
            if not a.get("error"): break
            time.sleep(30 * (k + 1))
        r["arxiv"] = a; time.sleep(10)
        t = a.get("title")
        if t and not r.get("title"):
            r["title"] = t
            r["crossref_search"] = rc["crossref_search"](t); time.sleep(1)
            r["openalex"] = rc["openalex"](t); time.sleep(1)
    r.pop("dblp", None)
    if (r.get("s2") or {}).get("error"):
        ident = ("arXiv:" + i["arxiv"]) if i.get("arxiv") else (("DOI:" + i["doi"]) if i.get("doi") else None)
        for k in range(4):
            s = rc["s2"](ident=ident) if ident else rc["s2"](title=r.get("title"))
            if not s.get("error"): break
            time.sleep(20 * (k + 1))
        r["s2"] = s; time.sleep(6)
    print("done", r["key"], file=sys.stderr, flush=True)
json.dump(R, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("updated", p)
