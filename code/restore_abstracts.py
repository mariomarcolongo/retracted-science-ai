# Release abstracts by reference, not as text (README, "Responsible release").
#
#   python3 -I code/restore_abstracts.py redact   # maintainer: targets.json -> targets.redacted.json
#   python3 -I code/restore_abstracts.py restore  # anyone: targets.redacted.json -> targets.json
#
# The released snapshot replaces each abstract with its source (PubMed or OpenAlex), the PubMed or
# OpenAlex ID already in the record, and the SHA-256 of the exact text. "restore" fetches each abstract
# the way code/draw.py built it, checks every hash, and writes targets.json only if the whole file
# matches the SHA-256 recorded at release; otherwise it writes nothing and lists the mismatches.
# PubMed and OpenAlex are public; no key, email or personal data is sent.
import hashlib, json, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("draw", "pilot")
sha = lambda b: hashlib.sha256(b).hexdigest()
dump = lambda rows: json.dumps(rows, indent=1, ensure_ascii=False).encode()  # format of the original files


def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-script"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def pubmed_abstracts(pmids):
    out = {}
    for i in range(0, len(pmids), 100):
        q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids[i:i + 100]), "retmode": "xml",
                                    "tool": "research-script"})
        root = ET.fromstring(get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + q))
        for art in root.iter("PubmedArticle"):  # same construction as code/draw.py
            parts = []
            for t in art.iter("AbstractText"):
                label, txt = t.get("Label"), "".join(t.itertext()).strip()
                if txt:
                    parts.append((label + ": " if label else "") + txt)
            out[art.findtext(".//MedlineCitation/PMID")] = " ".join(parts)
        time.sleep(0.4)
    return out


def openalex_abstract(work_url):
    wid = work_url.rstrip("/").rsplit("/", 1)[-1]
    inv = json.loads(get(f"https://api.openalex.org/works/{wid}?select=abstract_inverted_index"))
    inv = inv.get("abstract_inverted_index") or {}
    pos = {i: w for w, idx in inv.items() for i in idx}  # same construction as code/draw.py
    return " ".join(pos[i] for i in sorted(pos))


def redact():
    for g in GROUPS:
        src = ROOT / f"data/work/{g}/targets.json"
        raw = src.read_bytes()
        rows = json.loads(raw)
        assert dump(rows) == raw, f"{src}: not in the expected format; restore could not reproduce it"
        for r in rows:
            assert r["abstract"] and r["abstract_source"] in ("pubmed", "openalex")
            assert r["pmid"] if r["abstract_source"] == "pubmed" else r["openalex_id"]
            r["abstract_sha256"] = sha(r["abstract"].encode())
            r["abstract"] = None
        out = {"note": "Abstracts are withheld as text. Run: python3 -I code/restore_abstracts.py restore",
               "file_sha256": sha(raw), "records": rows}
        dst = src.with_name("targets.redacted.json")
        dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{dst.relative_to(ROOT)}: {len(rows)} abstracts withheld; original SHA-256 {sha(raw)}")


def restore():
    bad = 0
    for g in GROUPS:
        red = json.loads((ROOT / f"data/work/{g}/targets.redacted.json").read_text(encoding="utf-8"))
        rows = red["records"]
        pm = pubmed_abstracts(sorted({r["pmid"] for r in rows if r["abstract_source"] == "pubmed"}))
        for r in rows:
            text = pm.get(r["pmid"], "") if r["abstract_source"] == "pubmed" else openalex_abstract(r["openalex_id"])
            want = r.pop("abstract_sha256")
            if sha(text.encode()) != want:
                bad += 1
                print(f"{g} {r['id']}: {r['abstract_source']} text differs from the released hash "
                      f"(the source may have been edited since the snapshot)")
            r["abstract"] = text
        raw = dump(rows)
        if sha(raw) != red["file_sha256"]:
            print(f"{g}: rebuilt file does not match; targets.json not written")
            bad += 1
            continue
        (ROOT / f"data/work/{g}/targets.json").write_bytes(raw)
        print(f"data/work/{g}/targets.json restored and verified ({len(rows)} abstracts)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    {"redact": redact, "restore": restore}[sys.argv[1] if len(sys.argv) > 1 else ""]()
