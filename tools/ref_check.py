"""Check each cited work for its latest preprint version and any published version.

Usage: python3 -I tools/ref_check.py data/work/ref_list.json data/work/ref_check.json

Sources (no API keys, no contact details sent):
  arXiv API      latest version, journal_ref, DOI field
  Crossref       DOI metadata (type, venue, relations, update notices); title search
  OpenAlex       title search: locations and their version, retraction flag
  Semantic Scholar  venue, publication types, external IDs
  DBLP           conference/journal records (covers ICLR, NeurIPS, ICML)
"""
import json, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

UA = {"User-Agent": "research-script"}


def get(url, kind="json", tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
            return json.loads(body) if kind == "json" else body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503) and k < tries - 1:
                time.sleep(3 * (k + 1)); continue
            return {"_error": f"HTTP {e.code}"}
        except Exception as e:  # network errors
            if k < tries - 1:
                time.sleep(3 * (k + 1)); continue
            return {"_error": str(e)[:120]}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def same_title(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a == b or a.startswith(b[:60]) or b.startswith(a[:60]))


def arxiv(aid):
    body = get("https://export.arxiv.org/api/query?id_list=" + aid, "raw")
    if not isinstance(body, bytes):
        return {"error": str(body)}
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    e = ET.fromstring(body).find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return {"error": "not found"}
    eid = e.findtext("a:id", "", ns)
    return {
        "title": re.sub(r"\s+", " ", e.findtext("a:title", "", ns)).strip(),
        "latest": eid.rsplit("/", 1)[-1],
        "updated": e.findtext("a:updated", "", ns)[:10],
        "journal_ref": e.findtext("x:journal_ref", None, ns),
        "doi": e.findtext("x:doi", None, ns),
        "comment": e.findtext("x:comment", None, ns),
    }


def crossref_doi(doi):
    d = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if not d or "_error" in (d or {}):
        return {"error": "not found" if d is None else d["_error"]}
    m = d["message"]
    return {
        "title": (m.get("title") or [""])[0],
        "type": m.get("type"),
        "venue": (m.get("container-title") or [""])[0],
        "published": "-".join(str(x) for x in (m.get("published") or {}).get("date-parts", [[None]])[0] if x),
        "relation": {k: [r.get("id") for r in v] for k, v in (m.get("relation") or {}).items()},
        "updated_by": [(u.get("type"), u.get("DOI")) for u in m.get("updated-by", [])],
    }


def crossref_search(title):
    q = urllib.parse.quote(title)
    d = get(f"https://api.crossref.org/works?query.bibliographic={q}&rows=6&select=DOI,title,type,container-title,published")
    out = []
    for it in ((d or {}).get("message") or {}).get("items", []):
        t = (it.get("title") or [""])[0]
        if same_title(t, title):
            out.append({"doi": it["DOI"], "type": it.get("type"), "venue": (it.get("container-title") or [""])[0],
                        "published": "-".join(str(x) for x in (it.get("published") or {}).get("date-parts", [[None]])[0] if x)})
    return out


def openalex(title):
    q = urllib.parse.quote(title.replace(",", " "))
    d = get(f"https://api.openalex.org/works?search={q}&per-page=5&select=id,doi,display_name,type,publication_year,is_retracted,locations")
    out = []
    for w in (d or {}).get("results", []):
        if not same_title(w.get("display_name"), title):
            continue
        locs = [{"source": ((l.get("source") or {}).get("display_name")), "version": l.get("version"),
                 "url": l.get("landing_page_url")} for l in w.get("locations") or []]
        out.append({"id": w["id"], "doi": w.get("doi"), "type": w.get("type"), "year": w.get("publication_year"),
                    "retracted": w.get("is_retracted"), "locations": locs})
    return out


def s2(ident=None, title=None):
    f = "title,venue,year,publicationTypes,externalIds,publicationVenue,journal"
    if ident:
        d = get(f"https://api.semanticscholar.org/graph/v1/paper/{urllib.parse.quote(ident, safe=':')}?fields={f}")
    else:
        d = get(f"https://api.semanticscholar.org/graph/v1/paper/search/match?query={urllib.parse.quote(title)}&fields={f}")
        d = ((d or {}).get("data") or [None])[0] if d and "_error" not in d else d
    if not d or "_error" in d:
        return {"error": "not found" if not d else d["_error"]}
    return {"title": d.get("title"), "venue": d.get("venue"), "year": d.get("year"),
            "types": d.get("publicationTypes"), "ids": d.get("externalIds"),
            "journal": d.get("journal")}


def dblp(title):
    q = urllib.parse.quote(title)
    d = get(f"https://dblp.org/search/publ/api?q={q}&format=json&h=8")
    hits = (((d or {}).get("result") or {}).get("hits") or {}).get("hit", [])
    out = []
    for h in hits:
        i = h.get("info", {})
        if same_title(i.get("title"), title):
            out.append({"venue": i.get("venue"), "year": i.get("year"), "type": i.get("type"), "doi": i.get("doi"),
                        "ee": i.get("ee")})
    return out


refs = json.load(open(sys.argv[1], encoding="utf-8"))
results = []
for r in refs:
    res = {"key": r["key"], "input": r}
    title = r.get("title")
    if r.get("arxiv"):
        res["arxiv"] = arxiv(r["arxiv"]); time.sleep(3)
        title = title or res["arxiv"].get("title")
    if r.get("doi"):
        res["crossref_doi"] = crossref_doi(r["doi"]); time.sleep(1)
        title = title or res["crossref_doi"].get("title")
    if title:
        res["title"] = title
        res["crossref_search"] = crossref_search(title); time.sleep(1)
        res["openalex"] = openalex(title); time.sleep(1)
        res["dblp"] = dblp(title); time.sleep(1.5)
    ident = ("arXiv:" + r["arxiv"]) if r.get("arxiv") else (("DOI:" + r["doi"]) if r.get("doi") else None)
    res["s2"] = s2(ident=ident) if ident else s2(title=title); time.sleep(3)
    results.append(res)
    print("checked", r["key"], file=sys.stderr)

json.dump(results, open(sys.argv[2], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("written", sys.argv[2])
