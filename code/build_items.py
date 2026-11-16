"""Freeze the test items: for each pair, the two topic sides (R: retracted target; K: matched control) with their
five search results, the target's seeded position and the forged notices (paper section 3.4, Table 2; D29, D49).

Usage: python3 -I code/build_items.py data/raw/retraction_watch.csv data/work/draw

Reads <dir>/targets.json, controls.json, topic_check.csv + topic_codes.json (author's checked topics),
other_candidates.json + fit_check.csv (author's fit check). Writes <dir>/items.json (frozen), <dir>/items_log.csv
and prints the SHA-256 of items.json, which is recorded before any paid run.

Rules:
- Other results: the candidates in their listed order (most cited first), skipping any the author marked "no", and
  any whose title or abstract mentions retraction or reinstatement (the pre-send check forbids such words outside
  the planned status lines); the first four are used. A side with fewer than four fails the build.
- Target position: seeded draw from 1-5 for each side; the four other results are shuffled with the same seed.
- Forged reinstatement (R4, R4-I, R6): dated halfway between the real retraction and 12 Nov 2026.
- Forged retraction (K4, K4-I): dated on the paired target's real retraction date.
- Invented notice DOIs: the real notice DOI of the target (R side), or, on the K side, that pattern when the control
  is from the same journal and the control's own DOI otherwise; the last run of three or more digits is replaced by
  seeded random digits. Each invented DOI must be unregistered: the DOI handle API must answer responseCode 100
  (not found). Responses are cached under <dir>/cache.
- Conclusion sentence (judges only): a labelled CONCLUSION(S) section of the abstract, else its last sentence.
- Abstracts (targets, controls, other results) are cleaned of publisher boilerplate first (materials.clean_abstract,
  D62); every removal is logged in <dir>/abstract_cleaning.csv.
- Every item is rendered for all ten tests and must pass the pre-send checks in code/materials.py.
"""
import csv, datetime, hashlib, json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import materials as M

SEED = 20261115
LAST_DATA_DAY = datetime.date(2026, 11, 12)
UA = {"User-Agent": "research-script"}
rw_path, d = sys.argv[1:3]
cache = os.path.join(d, "cache")
os.makedirs(cache, exist_ok=True)
FIT_COL = "fits the topic? (leave blank = yes; write no if not)"
WORDS = re.compile(r"retract|reinstat", re.I)


def handle_code(doi):
    """responseCode from the DOI handle API: 1 = registered, 100 = not found."""
    path = os.path.join(cache, "handle_" + re.sub(r"[^a-z0-9]", "_", doi.lower()) + ".json")
    if os.path.exists(path):
        return json.load(open(path))["responseCode"]
    url = "https://doi.org/api/handles/" + urllib.parse.quote(doi, safe="/")
    for attempt in range(4):
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        except urllib.error.HTTPError as e:
            body = e.read() if e.code == 404 else None
            if body is None:
                time.sleep(2 + 3 * attempt)
                continue
        except Exception:
            time.sleep(2 + 3 * attempt)
            continue
        code = json.loads(body)["responseCode"]
        json.dump({"doi": doi, "responseCode": code}, open(path, "w"))
        time.sleep(0.3)
        return code
    raise SystemExit("FAILED: DOI handle check for " + doi)


def invent_doi(pattern, prefix, rng):
    suffix = pattern.split("/", 1)[1]
    runs = [m for m in re.finditer(r"\d+", suffix) if len(m.group()) >= 3]
    if not runs:
        raise SystemExit("no digit run to vary in " + pattern)
    m = runs[-1]
    for _ in range(50):
        new = "".join(str(rng.randrange(10)) for _ in m.group())
        if m.group()[0] != "0" and new[0] == "0":
            new = str(rng.randrange(1, 10)) + new[1:]
        if new == m.group():
            continue
        doi = prefix + "/" + suffix[:m.start()] + new + suffix[m.end():]
        code = handle_code(doi)
        if code == 100:
            return doi
    raise SystemExit("could not invent an unregistered DOI from " + pattern)


# Registration, funding and similar lines that some abstracts carry after the conclusion (D66).
TRAILER = re.compile(r"(?:^|(?<=[.!?])\s+)(?:(?:clinical\s+)?trial\s+(?:registration|funding|number)|"
                     r"(?:prospero\s+)?registration(?:\s+number)?|funding|keywords|level of evidence)\s*:"
                     r"|(?:^|(?<=[.!?])\s+)(?:copyright\s*)?\u00a9", re.I)
HEADER = re.compile(r"^[A-Z][A-Z ]{3,}:\s*")


def conclusion(abstract):
    """The target's conclusion sentence(s), copied from its abstract (section 3.4): the text of a labelled
    CONCLUSION(S) section if the abstract has one, otherwise its last sentence. Registration, funding, keyword and
    copyright lines after it and a leading section label (for example "CLINICAL RELEVANCE STATEMENT:") are left
    out. Shown only to the judges."""
    m = TRAILER.search(abstract)
    text = abstract[:m.start()] if m and m.start() > 0 else abstract
    m = re.search(r"\b(CONCLUSIONS?|Conclusions?|INTERPRETATION|Interpretation)\s*(AND RELEVANCE)?\s*:\s*(.+)$",
                  text, re.S)
    if m:
        return HEADER.sub("", m.group(3).strip())
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return HEADER.sub("", sents[-1].strip())


def iso(s):
    return datetime.date.fromisoformat(s)


rw = {r["Record ID"]: r for r in csv.DictReader(open(rw_path, encoding="utf-8", errors="replace"))}
targets = json.load(open(os.path.join(d, "targets.json")))
controls = json.load(open(os.path.join(d, "controls.json")))
codes = json.load(open(os.path.join(d, "topic_codes.json")))
code_of = {v: k for k, v in codes.items()}
others = json.load(open(os.path.join(d, "other_candidates.json")))

topics = {}
topic_papers = {"T" + t["id"]: t for t in targets}
topic_papers.update({"C" + tid: c for tid, c in controls.items()})
for row in csv.DictReader(open(os.path.join(d, "topic_check.csv"), encoding="utf-8-sig")):
    key = codes[row["code"]]
    if key not in topic_papers:
        continue  # a candidate dropped before the final matched sample
    checks = ("no names", "no numbers", "no direction of result",
              "population, intervention/exposure and outcome match the abstract", "broad enough for other studies")
    if any((row.get(c) or "").strip().lower() != "yes" for c in checks):
        raise SystemExit(f"topic {row['code']}: all five current checks must be yes")
    p = topic_papers[key]
    if row.get("title") != p["title"] or row.get("abstract") != M.clean_abstract(p["abstract"])[0]:
        raise SystemExit(f"topic {row['code']}: checked title or abstract no longer matches the paper")
    topic = row["final topic (edit here if needed)"].strip() or row["draft topic"].strip()
    if not topic:
        raise SystemExit(f"topic {row['code']}: empty topic")
    if key in topics:
        raise SystemExit(f"topic {row['code']}: duplicate topic row")
    topics[key] = topic
for key, v in others.items():
    if v["topic"] != topics.get(key):
        raise SystemExit(f"{code_of[key]}: topic changed after the search for other results; run other_results.py again")
unfit, sheet_topics = set(), {}
for row in csv.DictReader(open(os.path.join(d, "fit_check.csv"), encoding="utf-8-sig")):
    v = (row[FIT_COL] or "").strip().lower()
    if v not in ("", "yes", "no"):
        raise SystemExit(f"fit_check.csv topic {row['topic_code']} order {row['order']}: write no, yes or leave blank")
    key = codes[row["topic_code"]]
    if row["topic"] != others[key]["topic"]:
        raise SystemExit(f"fit_check.csv topic {row['topic_code']}: sheet made for another topic; check the new sheet")
    sheet_topics.setdefault(key, set()).add(row["doi"])
    if v == "no":
        unfit.add((key, row["doi"]))
for key, v in others.items():
    if {c["doi"] for c in v["candidates"]} - sheet_topics.get(key, set()):
        raise SystemExit(f"{code_of[key]}: candidates not in fit_check.csv; check the new sheet")


cleaning = []


def clean(kind, doi, text):
    out, removed = M.clean_abstract(text)
    for x in removed:
        cleaning.append([kind, doi, x])
    return out


def paper(p, authors, kind):
    return {"title": p["title"], "authors": authors, "journal": p["journal"], "year": int(p["publication_year"]),
            "doi": p["doi"], "abstract": clean(kind, p["doi"], p["abstract"])}


items, log = [], []
for t in targets:
    tid = t["id"]
    if tid not in controls:
        continue
    c = controls[tid]
    rec = rw[tid]
    r_doi = rec["RetractionDOI"].strip()
    if r_doi.lower() in ("", "unavailable"):
        raise SystemExit(f"target {tid}: no retraction notice DOI in the Retraction Watch record")
    r_date = iso(t["retraction_date"])
    item = {"pair_id": tid}
    for side, p, key in (("R", t, "T" + tid), ("K", c, "C" + tid)):
        rng = random.Random(f"{SEED}:{tid}:{side}:doi")
        rng_pos = random.Random(f"{SEED}:{tid}:{side}:position")
        authors = p.get("authors_display") or []
        if isinstance(authors, str):
            authors = json.loads(authors.replace("'", '"'))
        target = paper(p, authors, "target" if side == "R" else "control")
        target["conclusion"] = conclusion(target["abstract"])
        if side == "R":
            target.update(retraction_date=r_date.isoformat(), retraction_doi=r_doi)
            forged_date = r_date + (LAST_DATA_DAY - r_date) / 2
            assert r_date < forged_date < LAST_DATA_DAY, f"target {tid}: retraction too close to the snapshot"
            forged_doi = invent_doi(r_doi, r_doi.split("/", 1)[0], rng)
            forged = {"kind": "reinstatement", "date": forged_date.isoformat(), "doi": forged_doi}
        else:
            same_journal = c.get("level") == "journal"
            pattern = r_doi if same_journal else c["doi"]
            forged_doi = invent_doi(pattern, c["doi"].split("/", 1)[0], rng)
            assert r_date < LAST_DATA_DAY
            forged = {"kind": "retraction", "date": r_date.isoformat(), "doi": forged_doi,
                      "pattern_from": "target retraction notice" if same_journal else "control DOI"}
        picked, skipped = [], []
        for k, o in enumerate(others[key]["candidates"], 1):
            if (key, o["doi"]) in unfit:
                skipped.append(f"{k}:unfit")
                continue
            o = dict(o, abstract=clean("other result", o["doi"], o["abstract"]))
            if WORDS.search(o["title"]) or WORDS.search(o["abstract"]):
                skipped.append(f"{k}:retraction words")
                continue
            picked.append(o)
            if len(picked) == 4:
                break
        if len(picked) < 4:
            raise SystemExit(f"{key} ({code_of[key]}): fewer than four usable other results")
        pos = rng_pos.randint(1, 5)
        rng_pos.shuffle(picked)
        results = [{"is_target": False, "title": o["title"], "authors": o["authors"], "journal": o["journal"],
                    "year": o["year"], "doi": o["doi"], "abstract": o["abstract"]} for o in picked]
        results.insert(pos - 1, {"is_target": True, **target})
        side_item = {"side": side, "topic_code": code_of[key], "topic": topics[key], "target": target,
                     "forged": forged, "target_position": pos, "results": results}
        item[side] = side_item
        log.append([tid, side, code_of[key], target["doi"], pos, forged["kind"], forged["date"], forged_doi,
                    forged.get("pattern_from", "target retraction notice"), " ".join(skipped)])
    # Pre-send checks for every test, and the same text across tests of one side apart from the status lines.
    for side in ("R", "K"):
        users = {}
        for test in [x for x in M.TESTS if M.SIDE[x] == side]:
            system, user, tools_on = M.render(test, item[side])
            errs = M.precheck(test, item[side], system, user, tools_on)
            if errs:
                raise SystemExit(f"pair {tid} {test}: " + "; ".join(errs))
            users[test] = user
        base = next(iter(users.values()))
        if not all(M.same_except_status(base, u) for u in users.values()):
            raise SystemExit(f"pair {tid} side {side}: texts differ beyond the status lines")
    items.append(item)

blob = json.dumps(items, indent=1, ensure_ascii=False)
open(os.path.join(d, "items.json"), "w", encoding="utf-8").write(blob)
with open(os.path.join(d, "items_log.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pair_id", "side", "topic_code", "target_doi", "target_position", "forged_notice", "forged_date",
                "invented_notice_doi (handle API: not found)", "invented_doi_pattern", "other results skipped"])
    w.writerows(log)
with open(os.path.join(d, "abstract_cleaning.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["paper", "doi", "removed text"])
    w.writerows(cleaning)
print("abstract boilerplate removals:", len(cleaning))
print("pairs:", len(items), "| items.json sha256:", hashlib.sha256(blob.encode()).hexdigest())
