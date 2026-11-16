"""Draw, step 1: eligible retracted papers in a seeded order, with fresh records, ready for hand screening.

Usage: python3 -I code/draw.py data/raw/retraction_watch.csv data/work/pool_jan_full.json data/work/draw
       python3 -I code/draw.py data/raw/retraction_watch.csv data/work/pool_jan_full.json data/work/pilot --pilot
       (pilot set: same rules, but 1-4 citations instead of at least 5, so it never overlaps the main sample)

Python 3, standard library only. Public metadata only (OpenAlex, PubMed); no personal data is sent.
Every API response is cached under <outdir>/cache, so a re-run reproduces the same output offline.

Rules (paper Table F1; DECISIONS D28, D30):
  1. Retracted from 1 Jul 2026, research article, health subject, data-invalidating reason (pool.py),
     at least 5 OpenAlex citations (count.py).
  2. No reinstatement, correction or expression of concern for the same DOI in the registry snapshot, earlier or
     later (D30, applied to any date so that the registry tool returns only the retraction).
  3. Title and abstract from PubMed first, OpenAlex as fallback (D28). An abstract that is a retraction
     notice is rejected; if no usable English abstract remains, the paper is excluded.
  4. Seeded random order. Walking that order, a paper is accepted only if its journal and its authors
     (any shared author name or OpenAlex author ID) are not already used by an accepted paper.
     The rule gives at most one paper per journal and author group; it is journal-balanced, not uniform
     over papers.
  5. Hand screening (health research, research article) follows the same order; an excluded paper frees
     its journal and authors for the next one (code/draw_screen.py, step 2).

Outputs in <outdir>: eligible.json (every eligible paper with its record and flags), exclusions.csv
(every exclusion with its reason), screening.csv (papers in seeded order, for hand screening).
"""
import csv, json, os, random, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

SEED = 20261115
START = "2026-07-01"
MIN_CITES = 5
UA = {"User-Agent": "research-script"}

rw_path, pool_path, outdir = sys.argv[1:4]
PILOT = "--pilot" in sys.argv[4:]  # pilot set (section 3.6): the same rules, but fewer than 5 citations (and at least 1)
cache = os.path.join(outdir, "cache")
os.makedirs(cache, exist_ok=True)


def fetch(url, name):
    """GET with cache; fail closed after 4 attempts (no silent reuse of earlier data)."""
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
        except Exception as e:  # network or HTTP error
            last = e
            print("retry", attempt + 1, e)
            time.sleep(2 + 3 * attempt)
    raise SystemExit(f"FAILED after 4 attempts: {url} ({last})")


def norm_name(n):
    n = re.sub(r"[^a-z ]", " ", n.lower())
    parts = [p for p in n.split() if len(p) > 1]
    return " ".join(parts)


def sheet_path(path, decision_col):
    """Never overwrite a sheet that already holds the author's decisions: write a *_new.csv next to it instead."""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            if any((row.get(decision_col) or "").strip() for row in csv.DictReader(f)):
                new = path[:-4] + "_new.csv"
                print("NOTE:", path, "has decisions; not overwritten. New sheet written to", new)
                return new
    return path


NOTICE_START = re.compile(r"^\s*(this (article|paper) has been (retracted|withdrawn)|retraction( notice| note)?\b|"
                          r"the (publisher|journal|editors?|authors?) (has|have) retracted|withdrawn\b|"
                          r"expression of concern\b|notice of retraction)", re.I)
MARKER = re.compile(r"^\s*(retracted article[:.\s-]*|\[?retracted\]?[:.\s-]*|withdrawn[:.\s-]*)", re.I)


def clean_title(t):
    c = MARKER.sub("", t or "").strip()
    return c, (c != (t or "").strip())


def openalex_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for w, idx in inv.items():
        for i in idx:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


# ---- 1. registry and pool ----
rw = list(csv.DictReader(open(rw_path, encoding="utf-8", errors="replace")))
other_notices = {}
for r in rw:
    doi = r["OriginalPaperDOI"].strip().lower()
    if doi and r["RetractionNature"] != "Retraction":
        other_notices.setdefault(doi, []).append(f'{r["RetractionNature"]} {r["RetractionDate"].split()[0]} (record {r["Record ID"]})')
pmid_rw = {r["Record ID"]: r["OriginalPaperPubMedID"].strip() for r in rw}

pool = json.load(open(pool_path))
excl = []
elig = []
for p in pool:
    if p["rdate"] < START:
        continue
    if PILOT:
        if not p["oa"] or not (1 <= p["oa"]["cites"] < MIN_CITES):
            excl.append((p["id"], p["doi"], "pilot: not 1-4 OpenAlex citations, or no OpenAlex record"))
            continue
    elif not p["oa"] or p["oa"]["cites"] < MIN_CITES:
        excl.append((p["id"], p["doi"], "fewer than 5 OpenAlex citations or no OpenAlex record"))
        continue
    if p["doi"] in other_notices:
        excl.append((p["id"], p["doi"], "later status notice: " + "; ".join(other_notices[p["doi"]])))
        continue
    elig.append(p)
print("retracted from", START, "with 1-4 citations (pilot)" if PILOT else "with >= 5 citations", "and no other notice:", len(elig))

# ---- 2. fresh records: OpenAlex (abstract, all authors) and PubMed ----
oa = {}
dois = sorted(p["doi"] for p in elig)
for i in range(0, len(dois), 40):
    chunk = dois[i:i + 40]
    q = urllib.parse.urlencode({"filter": "doi:" + "|".join(chunk), "per-page": "50",
                                "select": "id,doi,title,publication_year,type,language,cited_by_count,"
                                          "abstract_inverted_index,authorships,primary_location,primary_topic"})
    data = json.loads(fetch("https://api.openalex.org/works?" + q, f"openalex_targets_{i:04d}.json"))
    for w in data["results"]:
        oa[(w.get("doi") or "").replace("https://doi.org/", "").lower()] = w
missing = [d for d in dois if d not in oa]
if missing:
    print("OpenAlex returned no record for", len(missing), "DOIs; they are excluded")

pmids = {}
for p in elig:
    pm = (p.get("pmid") or pmid_rw.get(p["id"], "") or "").strip()
    if pm in ("", "0"):
        q = urllib.parse.urlencode({"db": "pubmed", "term": p["doi"] + "[doi]", "retmode": "json", "tool": "research-script"})
        ids = json.loads(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + q,
                               f"pubmed_esearch_{p['id']}.json"))["esearchresult"]["idlist"]
        pm = ids[0] if len(ids) == 1 else ""
    if pm:
        pmids[p["id"]] = pm
pm_rec = {}
ids = sorted(set(pmids.values()))
for i in range(0, len(ids), 100):
    chunk = ids[i:i + 100]
    q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "tool": "research-script"})
    root = ET.fromstring(fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + q, f"pubmed_efetch_{i:04d}.xml"))
    for art in root.iter("PubmedArticle"):
        pid = art.findtext(".//MedlineCitation/PMID")
        title = "".join(art.find(".//ArticleTitle").itertext()).strip() if art.find(".//ArticleTitle") is not None else ""
        parts = []
        for t in art.iter("AbstractText"):
            label = t.get("Label")
            txt = "".join(t.itertext()).strip()
            if txt:
                parts.append((label + ": " if label else "") + txt)
        pm_rec[pid] = {"title": title, "abstract": " ".join(parts), "lang": art.findtext(".//Language"),
                       "pubtypes": [x.text for x in art.iter("PublicationType")]}

# ---- 3. abstracts (PubMed first, OpenAlex fallback), notices rejected ----
records = []
for p in elig:
    w = oa.get(p["doi"])
    if not w:
        excl.append((p["id"], p["doi"], "no OpenAlex record in fresh query"))
        continue
    pm = pm_rec.get(pmids.get(p["id"], ""), {})
    cand = []
    if pm.get("abstract") and pm.get("lang") in (None, "eng"):
        cand.append(("pubmed", pm["title"] or p["title"], pm["abstract"]))
    oa_abs = openalex_abstract(w.get("abstract_inverted_index"))
    if oa_abs and w.get("language") in (None, "en"):
        cand.append(("openalex", w.get("title") or p["title"], oa_abs))
    chosen, notes = None, []
    for src, title, ab in cand:
        if NOTICE_START.search(ab):
            notes.append(f"{src} abstract is a notice")
            continue
        if len(ab.split()) < 50:
            notes.append(f"{src} abstract under 50 words")
            continue
        chosen = (src, title, ab)
        break
    if not chosen:
        excl.append((p["id"], p["doi"], "no usable English abstract (" + ("; ".join(notes) or "none found") + ")"))
        continue
    title, marked = clean_title(chosen[1])
    authors_names = {norm_name(a) for a in p["authors"].split(";") if norm_name(a)}
    authors_names |= {norm_name(a["author"]["display_name"]) for a in w.get("authorships", []) if a.get("author")}
    author_ids = {a["author"]["id"] for a in w.get("authorships", []) if a.get("author") and a["author"].get("id")}
    src_id = ((w.get("primary_location") or {}).get("source") or {}).get("id")
    records.append({
        "id": p["id"], "doi": p["doi"], "pmid": pmids.get(p["id"]), "journal": p["journal"], "openalex_source": src_id,
        "openalex_id": w["id"], "publication_year": w.get("publication_year"), "openalex_type": w.get("type"),
        "cites": w.get("cited_by_count"), "retraction_date": p["rdate"], "original_date": p["odate"],
        "reasons": p["reasons"], "subfield": ((w.get("primary_topic") or {}).get("subfield") or {}).get("display_name"),
        "subfield_id": ((w.get("primary_topic") or {}).get("subfield") or {}).get("id"),
        "title": title, "title_marker_removed": marked, "abstract": chosen[2], "abstract_source": chosen[0],
        "abstract_notes": notes, "retraction_words_in_abstract": bool(re.search(r"retract|withdraw", chosen[2], re.I)),
        "pubmed_types": pm.get("pubtypes", []), "author_names": sorted(authors_names),
        "authors_display": [a.strip() for a in p["authors"].split(";") if a.strip()], "author_ids": sorted(author_ids),
    })

# ---- 4. seeded order with journal and author-group rule ----
rng = random.Random(SEED)
order = sorted(records, key=lambda r: r["id"])
rng.shuffle(order)
for rank, r in enumerate(order, 1):
    r["rank"] = rank


def blocker(r, accepted):
    for a in accepted:
        if a["journal"].lower() == r["journal"].lower():
            return f"journal of rank {a['rank']}"
        if set(r["author_names"]) & set(a["author_names"]) or set(r["author_ids"]) & set(a["author_ids"]):
            return f"author group of rank {a['rank']}"
    return ""


# First pass, assuming every screened paper is included. code/draw_screen.py redoes this walk with the
# author's decisions and lists any reserve paper that a hand exclusion frees.
accepted = []
for r in order:
    r["blocked_by"] = blocker(r, accepted)
    if not r["blocked_by"]:
        accepted.append(r)

json.dump(order, open(os.path.join(outdir, "eligible.json"), "w"), indent=1, ensure_ascii=False)
with open(os.path.join(outdir, "exclusions.csv"), "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["rw_record_id", "doi", "reason"])
    wr.writerows(sorted(excl))
with open(sheet_path(os.path.join(outdir, "screening.csv"), "decision (include / exclude)"), "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["rank", "rw_record_id", "screen now", "decision (include / exclude)", "reason if excluded", "title",
                 "journal", "publication_year", "openalex_type", "openalex_subfield", "pubmed_types", "abstract_source",
                 "retraction_words_in_abstract", "abstract"])
    for r in sorted(order, key=lambda r: (bool(r["blocked_by"]), r["rank"])):  # papers to screen first
        wr.writerow([r["rank"], r["id"], "yes" if not r["blocked_by"] else "reserve (" + r["blocked_by"] + ")", "", "",
                     r["title"], r["journal"], r["publication_year"], r["openalex_type"], r["subfield"],
                     "; ".join(r["pubmed_types"]), r["abstract_source"], "yes" if r["retraction_words_in_abstract"] else "",
                     r["abstract"]])
print("to screen now:", len(accepted), "| reserves:", len(order) - len(accepted))
print("eligible with usable abstract:", len(order), "| journals:", len({r["journal"] for r in order}),
      "| exclusions logged:", len(excl))
print("abstract source:", {s: sum(r["abstract_source"] == s for r in order) for s in ("pubmed", "openalex")},
      "| title markers removed:", sum(r["title_marker_removed"] for r in order),
      "| retraction words left in abstract:", sum(r["retraction_words_in_abstract"] for r in order))
