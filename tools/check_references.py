"""Check every entry in the draft's reference list against its own link.

Usage: python3 -I tools/check_references.py paper/paper-draft.md data/work/reference_check.md

For a DOI: fetch Crossref metadata and compare title, year and first author with the entry.
For any other link: fetch the page and compare its <title> with the entry's title.
Sends no personal data; User-Agent "research-script". Pages that block scripts are reported
as "blocked" and must be checked by hand in a browser.
"""
import difflib, html, json, re, sys, time, urllib.parse, urllib.request

src, out = sys.argv[1], sys.argv[2]
UA = {"User-Agent": "research-script"}

lines = open(src, encoding="utf-8").read().split("\n")
i = lines.index("## References")
refs = []
for line in lines[i + 1:]:
    if line.startswith("## "):
        break
    if line.startswith("- "):
        refs.append(line[2:])


def fetch(url, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)


def norm(s):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def sim(a, b):
    return difflib.SequenceMatcher(None, " ".join(norm(a)), " ".join(norm(b))).ratio()


def entry_title(ref):
    # Title = text after "(year...). " up to the next ". " (or "? ").
    m = re.search(r"\(\d{4}[^)]*\)\.\s+(.+?[.?])(?:\s|$)", ref)
    return m.group(1).rstrip(".") if m else ""


try:  # hand-checked section of an earlier run, kept on every re-run
    old = open(out, encoding="utf-8").read()
    hand = old[old.index("## Checked by hand"):] if "## Checked by hand" in old else ""
except FileNotFoundError:
    hand = ""

rows = []
for ref in refs:
    name = ref.split(" (")[0][:40]
    year = (re.search(r"\((\d{4})", ref) or [None, ""])[1]
    title = entry_title(ref)
    url = (re.search(r"https?://\S+?(?=[.,;]?(?:\s|$))", ref) or [None])[0]
    doi = None
    if url and "doi.org/" in url:
        doi = url.split("doi.org/", 1)[1]
    if doi:
        st, body = fetch("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/"))
        if st == 200:
            m = json.loads(body)["message"]
            ctitle = (m.get("title") or [""])[0]
            cyear = str(((m.get("issued") or {}).get("date-parts") or [[None]])[0][0])
            cauth = ((m.get("author") or [{}])[0].get("family") or (m.get("author") or [{}])[0].get("name") or "")
            s = sim(title, ctitle)
            ok = s >= 0.8 and cyear == year and (not cauth or cauth.split()[0].lower() in ref.lower())
            rows.append((name, year, "DOI", "OK" if ok else "CHECK", f"title match {s:.2f}; Crossref year {cyear}; first author {cauth}"))
        else:
            # Some DOIs (e.g. DataCite, ACL) are not in Crossref: check that the DOI resolves.
            st2, body2 = fetch("https://doi.org/" + doi)
            t = (re.search(r"<title[^>]*>(.*?)</title>", body2, re.S | re.I) or [None, ""])[1]
            s = sim(title, t)
            rows.append((name, year, "DOI (not in Crossref)", "OK" if st2 == 200 and s >= 0.6 else "CHECK",
                         f"resolves: HTTP {st2}; page title match {s:.2f}"))
    elif url:
        st, body = fetch(url)
        t = (re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I) or [None, ""])[1]
        s = sim(title, t)
        if st in (401, 403, 429) or (st is None):
            rows.append((name, year, "URL", "BLOCKED", f"HTTP {st}; check by hand in a browser"))
        elif url.lower().endswith(".pdf") or "application/pdf" in body[:200]:
            rows.append((name, year, "URL (PDF)", "OK" if st == 200 else "CHECK", f"HTTP {st}; PDF, title not compared"))
        else:
            rows.append((name, year, "URL", "OK" if st == 200 and s >= 0.5 else "CHECK",
                         f"HTTP {st}; page title match {s:.2f}"))
    else:
        rows.append((name, year, "none", "CHECK", "no link in entry"))
    time.sleep(0.5)

with open(out, "w", encoding="utf-8") as f:
    f.write(f"# Reference check ({time.strftime('%Y-%m-%d')})\n\n")
    f.write("Automatic check of every reference against its own DOI or link (tools/check_references.py). "
            "OK = title, year and first author match Crossref, or the page title matches. "
            "CHECK = differs, read by hand. BLOCKED = the site refuses scripts, checked by hand in a browser.\n\n")
    f.write("| Reference | Year | Link | Result | Detail |\n|---|---|---|---|---|\n")
    for r in rows:
        f.write("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |\n")
if hand:  # keep the hand-checked section written below the automatic table
    with open(out, "a", encoding="utf-8") as f:
        f.write("\n" + hand)
counts = {k: sum(1 for r in rows if r[3] == k) for k in ("OK", "CHECK", "BLOCKED")}
print(len(rows), "references:", counts)
