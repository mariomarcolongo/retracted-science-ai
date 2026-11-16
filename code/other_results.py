"""The four other search results for each topic (paper Table F1, "Other results"; section 3.4).

Usage: python3 -I code/other_results.py REGISTRY.csv DRAW_DIR [--candidate-limit 8]

Topics: the author's checked topics in <dir>/topic_check.csv (all five checks marked "yes"; the edited topic is
used where one was written). For each topic: OpenAlex works search with the topic sentence as the query, restricted
to articles with an English abstract published within 5 years of the paper; from the first 200 results by
relevance, eligible articles are ranked by citations. Excluded: the target, its matched paper, any paper sharing an
author with either, any paper with a Retraction Watch record (as the original paper or as the notice), other
targets and controls, abstracts under 50 words or that are notices (title or abstract; "Withdrawn" included), and
any whose title or cleaned abstract contains "retract" or "reinstat" in any sense (the items must not contain these
words, so such a paper is never proposed and then dropped at build). The same rules are applied again to the PubMed
title and abstract when PubMed supplies them (D66). The four most cited are proposed; the next four are reserves in case the author finds one off
topic. Writes <dir>/other_candidates.json and <dir>/fit_check.csv (the author marks "no" for a result that does not
fit its topic). Responses are cached under <dir>/cache.
"""
import argparse, csv, hashlib, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from materials import clean_abstract

UA = {"User-Agent": "research-script"}
ap = argparse.ArgumentParser()
ap.add_argument("registry"); ap.add_argument("directory")
ap.add_argument("--candidate-limit", type=int, default=8,
                help="increase to inspect later eligible results after rejecting the listed candidates (maximum 200)")
args = ap.parse_args()
if not 4 <= args.candidate_limit <= 200:
    raise SystemExit("--candidate-limit must be from 4 to 200")
rw_path, d = args.registry, args.directory
cache = os.path.join(d, "cache")


def fetch(url, name):
    path = os.path.join(cache, name)
    if os.path.exists(path):
        return open(path, "rb").read()
    last = None
    for attempt in range(4):
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
            with open(path + ".tmp", "wb") as _f:  # a crash never leaves a cut-off cache file (D65)
                _f.write(body)
            os.replace(path + ".tmp", path)
            time.sleep(0.4)
            return body
        except Exception as e:
            last = e
            time.sleep(2 + 3 * attempt)
    raise SystemExit(f"FAILED after 4 attempts: {url} ({last})")


def norm_name(n):
    return " ".join(p for p in re.sub(r"[^a-z ]", " ", n.lower()).split() if len(p) > 1)


def oa_abstract(inv):
    if not inv:
        return ""
    pos = {i: w for w, idx in inv.items() for i in idx}
    return " ".join(pos[i] for i in sorted(pos))


def sheet_path(path, decision_col):
    """Never overwrite a sheet that already holds the author's decisions: write a *_new.csv next to it instead."""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            if any((row.get(decision_col) or "").strip() for row in csv.DictReader(f)):
                new = path[:-4] + "_new.csv"
                print("NOTE:", path, "has decisions; not overwritten. New sheet written to", new)
                return new
    return path


NOTICE = re.compile(r"^\s*(this (article|paper) has been (retracted|withdrawn)|retraction|retracted\b|withdrawn\b|"
                    r"withdrawal\b|expression of concern|notice of|correction\b|corrigendum|erratum)", re.I)
WORDS = re.compile(r"retract|reinstat", re.I)  # the same rule as build_items.py
rw_dois = set()
for _r in csv.DictReader(open(rw_path, encoding="utf-8", errors="replace")):
    for _col in ("OriginalPaperDOI", "RetractionDOI"):
        _v = (_r.get(_col) or "").strip().lower()
        if _v and _v not in ("unavailable", "na", "n/a"):
            rw_dois.add(_v)


def disqualified(title, abstract):
    """A notice, or status words that build_items.py would reject."""
    return bool(NOTICE.search(abstract) or NOTICE.search(title or "") or WORDS.search(title or "")
                or WORDS.search(clean_abstract(abstract)[0]))
targets = {t["id"]: t for t in json.load(open(os.path.join(d, "targets.json")))}
controls = json.load(open(os.path.join(d, "controls.json")))
codes = json.load(open(os.path.join(d, "topic_codes.json")))
used = {t["doi"] for t in targets.values()} | {c["doi"] for c in controls.values()}

topics = {}
for row in csv.DictReader(open(os.path.join(d, "topic_check.csv"), encoding="utf-8-sig")):
    checks = [row[k].strip().lower() for k in ("no names", "no numbers", "no direction of result",
              "population, intervention/exposure and outcome match the abstract", "broad enough for other studies")]
    if any(c != "yes" for c in checks):
        raise SystemExit(f"topic {row['code']}: all five checks must be 'yes' (edit the topic until they are)")
    topics[codes[row["code"]]] = (row["final topic (edit here if needed)"].strip() or row["draft topic"].strip(),
                                  row["draft topic"].strip() != (row["final topic (edit here if needed)"].strip() or row["draft topic"].strip()))

code_of = {v: k for k, v in codes.items()}
out, rows = {}, []
for tid, t in targets.items():
    if tid not in controls:
        continue
    c = controls[tid]
    for side, paper, key in (("R", t, "T" + tid), ("K", c, "C" + tid)):
        topic = topics[key][0]
        y = paper["publication_year"]
        excl_names = set(t["author_names"]) | set(c["author_names"])
        excl_ids = set(t["author_ids"]) | set(c["author_ids"])
        q = urllib.parse.urlencode({"search": topic, "per-page": "200", "filter": f"type:article,has_abstract:true,"
                                    f"language:en,publication_year:{y - 5}-{y + 5}",
                                    "select": "id,doi,title,publication_year,cited_by_count,abstract_inverted_index,"
                                              "authorships,primary_location"})
        qh = hashlib.sha256(q.encode()).hexdigest()[:12]  # cache keyed by the full query, so an edited topic searches again
        res = json.loads(fetch("https://api.openalex.org/works?" + q, f"other_{key}_{qh}.json"))["results"]
        elig = []
        for w in res:
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if not doi or doi in used or doi in rw_dois:
                continue
            names = {norm_name(a["author"]["display_name"]) for a in w.get("authorships", []) if a.get("author")}
            ids = {a["author"]["id"] for a in w.get("authorships", []) if a.get("author") and a["author"].get("id")}
            if names & excl_names or ids & excl_ids:
                continue
            ab = oa_abstract(w.get("abstract_inverted_index"))
            if len(ab.split()) < 50 or disqualified(w.get("title") or "", ab):
                continue
            elig.append((w.get("cited_by_count") or 0, doi, w, ab))
        elig.sort(key=lambda x: (-x[0], x[1]))
        picked = []
        for cites, doi, w, ab in elig:
            if len(picked) >= args.candidate_limit:
                break
            # PubMed first for title and abstract (D28), OpenAlex as fallback
            qs = urllib.parse.urlencode({"db": "pubmed", "term": doi + "[doi]", "retmode": "json", "tool": "research-script"})
            ids = json.loads(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + qs,
                                   "pm_es_" + re.sub(r"[^a-z0-9]", "_", doi) + ".json"))["esearchresult"]["idlist"]
            title, abstract, src = w.get("title"), ab, "openalex"
            if len(ids) == 1:
                qs = urllib.parse.urlencode({"db": "pubmed", "id": ids[0], "retmode": "xml", "tool": "research-script"})
                root = ET.fromstring(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + qs,
                                           "pm_ef_" + ids[0] + ".xml"))
                art = root.find(".//PubmedArticle")
                if art is not None:
                    parts = [((x.get("Label") + ": ") if x.get("Label") else "") + "".join(x.itertext()).strip()
                             for x in art.iter("AbstractText") if "".join(x.itertext()).strip()]
                    pab = " ".join(parts)
                    el = art.find(".//ArticleTitle")
                    ptitle = "".join(el.itertext()).strip() if el is not None else title
                    if NOTICE.search(ptitle or "") or WORDS.search(ptitle or ""):
                        continue  # PubMed labels it a notice or uses a status word: not a usable result
                    if len(pab.split()) >= 50 and art.findtext(".//Language") in (None, "eng"):
                        if disqualified(ptitle, pab):
                            continue
                        title, abstract, src = ptitle, pab, "pubmed"
            picked.append({"doi": doi, "title": re.sub(r"\s+", " ", title or ""), "abstract": abstract,
                           "abstract_source": src, "year": w.get("publication_year"), "cites": cites,
                           "journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
                           "authors": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")]})
        out[key] = {"topic": topic, "candidates": picked}
        for k, p in enumerate(picked, 1):
            rows.append([code_of[key], topic, k, "proposed" if k <= 4 else "reserve", "", p["title"], p["journal"], p["year"],
                         p["doi"]])
        print(key, len(elig), "eligible,", len(picked), "listed")

with open(os.path.join(d, "other_candidates.json.tmp"), "w", encoding="utf-8") as _f:
    json.dump(out, _f, indent=1, ensure_ascii=False)
os.replace(os.path.join(d, "other_candidates.json.tmp"), os.path.join(d, "other_candidates.json"))
with open(sheet_path(os.path.join(d, "fit_check.csv"), "fits the topic? (leave blank = yes; write no if not)"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["topic_code", "topic", "order", "role", "fits the topic? (leave blank = yes; write no if not)",
                "title", "journal", "year", "doi"])
    w.writerows(rows)
print("topics:", len(out))
