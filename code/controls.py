"""Draw, step 3: candidate matched control papers for each retracted target, ready for hand screening.

Usage: python3 -I code/controls.py data/raw/retraction_watch.csv data/work/draw

Targets: <dir>/targets.json if it exists, otherwise every not-blocked paper in <dir>/eligible.json
(so the search can start while the targets are still being screened).

Rule (paper Table F1): a non-retracted research article in the same journal, publication year within 1 of the
target's, OpenAlex citations 0.5-2x the target's, English abstract, no author shared with the target, and no
Retraction Watch record of any kind. If none is found in the journal, the same OpenAlex subfield is used.
Candidates come from OpenAlex's seeded random sample (sample=100, seed below) over the filtered works; their order
is the seeded order. The author screens them in that order (health research, original research article); the
first one included becomes the control. Every API response is cached under <dir>/cache.
"""
import csv, json, math, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

SEED = 20261115
SHOW = int(sys.argv[3]) if len(sys.argv) > 3 else 3  # candidates listed per target: the first to screen, then reserves
UA = {"User-Agent": "research-script"}
rw_path, d = sys.argv[1:3]
cache = os.path.join(d, "cache")
os.makedirs(cache, exist_ok=True)


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
            print("retry", attempt + 1, e)
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


NOTICE = re.compile(r"^\s*(this (article|paper) has been (retracted|withdrawn)|retraction|expression of concern|"
                    r"notice of|withdrawn\b|correction\b|erratum)", re.I)

rw_dois = {r["OriginalPaperDOI"].strip().lower() for r in csv.DictReader(open(rw_path, encoding="utf-8", errors="replace"))}
tp = os.path.join(d, "targets.json")
targets = json.load(open(tp)) if os.path.exists(tp) else [r for r in json.load(open(os.path.join(d, "eligible.json")))
                                                           if not r["blocked_by"]]
target_dois = {t["doi"] for t in json.load(open(os.path.join(d, "eligible.json")))}


def candidates(t, level):
    y = t["publication_year"]
    lo, hi = math.ceil(0.5 * t["cites"]), math.floor(2 * t["cites"])
    f = [f"publication_year:{y - 1}-{y + 1}", f"cited_by_count:{lo}-{hi}", "type:article", "has_abstract:true",
         "language:en"]
    if level == "journal":
        if not t["openalex_source"]:
            return []
        f.append("primary_location.source.id:" + t["openalex_source"].rsplit("/", 1)[-1])
    else:
        if not t["subfield_id"]:
            return []
        f.append("primary_topic.subfield.id:" + str(t["subfield_id"]).rsplit("/", 1)[-1])
    q = urllib.parse.urlencode({"filter": ",".join(f), "sample": "100", "seed": str(SEED), "per-page": "100",
                                "select": "id,doi,title,publication_year,cited_by_count,type,language,"
                                          "abstract_inverted_index,authorships,primary_location,primary_topic"})
    res = json.loads(fetch("https://api.openalex.org/works?" + q, f"controls_{t['id']}_{level}.json"))["results"]
    out = []
    for w in res:
        doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
        if not doi or doi == t["doi"] or doi in rw_dois or doi in target_dois:
            continue
        names = {norm_name(a["author"]["display_name"]) for a in w.get("authorships", []) if a.get("author")}
        ids = {a["author"]["id"] for a in w.get("authorships", []) if a.get("author") and a["author"].get("id")}
        if names & set(t["author_names"]) or ids & set(t["author_ids"]):
            continue
        out.append((doi, w))
    return out


def pubmed(doi, key):
    q = urllib.parse.urlencode({"db": "pubmed", "term": doi + "[doi]", "retmode": "json", "tool": "research-script"})
    ids = json.loads(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + q,
                           f"pubmed_esearch_ctrl_{key}.json"))["esearchresult"]["idlist"]
    if len(ids) != 1:
        return None, {}
    q = urllib.parse.urlencode({"db": "pubmed", "id": ids[0], "retmode": "xml", "tool": "research-script"})
    root = ET.fromstring(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + q,
                               f"pubmed_efetch_ctrl_{key}.xml"))
    art = root.find(".//PubmedArticle")
    if art is None:
        return ids[0], {}
    parts = []
    for x in art.iter("AbstractText"):
        txt = "".join(x.itertext()).strip()
        if txt:
            parts.append((x.get("Label") + ": " if x.get("Label") else "") + txt)
    el = art.find(".//ArticleTitle")
    return ids[0], {"title": "".join(el.itertext()).strip() if el is not None else "", "abstract": " ".join(parts),
                    "lang": art.findtext(".//Language"), "pubtypes": [x.text for x in art.iter("PublicationType")]}


rows, out, out_more = [], {}, {}
for t in targets:
    # Journal candidates first, in their seeded order; the same subfield's candidates follow if the journal runs short.
    cands = [(doi, w, "journal") for doi, w in candidates(t, "journal")]
    level = "journal"
    listed = []
    tried_subfield = False
    n = -1
    while True:
        n += 1
        if n >= len(cands):
            if tried_subfield or len(listed) >= SHOW:
                break
            tried_subfield = True
            seen = {c[0] for c in cands}
            cands += [(doi, w, "subfield") for doi, w in candidates(t, "subfield") if doi not in seen]
            if n >= len(cands):
                break
        doi, w, level = cands[n]
        if len(listed) >= SHOW:
            break
        key = f"{t['id']}_{n}"
        pmid, pm = pubmed(doi, key)
        if pm.get("abstract") and pm.get("lang") in (None, "eng") and not NOTICE.search(pm["abstract"]):
            src, title, ab = "pubmed", pm["title"] or w["title"], pm["abstract"]
        else:
            src, title, ab = "openalex", w["title"], oa_abstract(w.get("abstract_inverted_index"))
        if len(ab.split()) < 50 or NOTICE.search(ab) or NOTICE.search(title or ""):
            continue
        listed.append({"doi": doi, "pmid": pmid, "openalex_id": w["id"], "title": title, "abstract": ab,
                       "abstract_source": src, "publication_year": w.get("publication_year"),
                       "cites": w.get("cited_by_count"), "level": level,
                       "journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
                       "pubmed_types": pm.get("pubtypes", []),
                       "authors_display": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
                       "author_names": sorted({norm_name(a["author"]["display_name"]) for a in w.get("authorships", [])
                                               if a.get("author")}),
                       "author_ids": sorted({a["author"]["id"] for a in w.get("authorships", [])
                                             if a.get("author") and a["author"].get("id")}),
                       "subfield": ((w.get("primary_topic") or {}).get("subfield") or {}).get("display_name")})
    out[t["id"]] = listed
    out_more[t["id"]] = len(listed) >= SHOW  # more candidates may exist: a larger list will show them
    for k, c in enumerate(listed, 1):
        rows.append([t["rank"], t["id"], t["title"], k, "yes" if k == 1 else "reserve", "", "", c["doi"], c["title"],
                     c["journal"], c["level"], c["publication_year"], c["cites"], "; ".join(c["pubmed_types"]),
                     c["abstract_source"], c["abstract"]])
    if not listed:
        rows.append([t["rank"], t["id"], t["title"], 0, "none found", "", "", "", "", "", "", "", "", "", "", ""])
    print(f"rank {t['rank']:4d} record {t['id']}: {len(cands)} candidates ({level}), {len(listed)} listed")

json.dump(out, open(os.path.join(d, "control_candidates.json"), "w"), indent=1, ensure_ascii=False)
json.dump(out_more, open(os.path.join(d, "control_more.json"), "w"), indent=1)
with open(sheet_path(os.path.join(d, "control_screening.csv"), "decision (include / exclude)"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["target_rank", "target_rw_record_id", "target_title", "candidate_order", "screen now",
                "decision (include / exclude)", "reason if excluded", "doi", "title", "journal", "match_level",
                "publication_year", "cites", "pubmed_types", "abstract_source", "abstract"])
    rows.sort(key=lambda r: (r[4] != "yes", r[0], r[3]))
    w.writerows(rows)
print("targets:", len(targets), "| with a candidate:", sum(1 for v in out.values() if v))
