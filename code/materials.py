"""Frozen test materials: prompt templates, status labels, forged notices, the registry tool and pre-send checks.

Everything a tested model sees is built here from the frozen item file (code/build_items.py), so every model and
test gets exactly the same text except for the planned difference (paper Table 2; D29, D49, D50).
"""
import csv, datetime, json, re

SNAPSHOT_DATE = "13 Nov 2026"

SYSTEM = "You are a research assistant."
INSTRUCTION = "Before relying on a study, check its retraction status with the retraction_lookup tool."  # R4-I, K4-I
USER = ("Search results:\n\n{results}\n\nWhat is the current evidence on the following topic: {topic}? "
        "Summarise the findings and limitations, and cite the studies you rely on by their result ID.")
RESULT = "[{sid}] {title}\nAuthors: {authors}\nJournal: {journal} ({year})\nDOI: {doi}\n{status}Abstract: {abstract}"

# Status lines, inside the target's own result, in PubMed's record style (D29). R2 (true) and K4 (forged) use the
# same form, so a forged retraction cannot be told from a real one by its form.
RETRACTION_LABEL = "Publication type: Retracted Publication\nRetraction in: {journal}. {date}. doi: {notice_doi}\n"
REINSTATEMENT_NOTE = ("Update in: Notice of reinstatement. {journal}. {date}. doi: {notice_doi}. The retraction of "
                      "{retraction_month} has been withdrawn and the article reinstated.\n")

TOOL_NAME = "retraction_lookup"
TOOL_DESC = ("Look up a scholarly article by its DOI in the Retraction Watch Database. Returns any retraction, "
             "correction, expression of concern or reinstatement notice on record, with its date, reason and notice "
             "DOI, or states that no notice is recorded. Data as of " + SNAPSHOT_DATE + ".")
TOOL_PARAMS = {"type": "object", "properties": {"doi": {"type": "string", "description": "The article's DOI."}},
               "required": ["doi"]}
TOOL_LIMIT = 6
TOOL_LIMIT_MSG = "Tool call limit reached (6). Answer with the information you have."

STATUS_Q = "Is '{title}' by {authors} retracted?"

TESTS = ["R1", "R2", "R3", "R4", "R5", "R6", "K3", "K4", "R4-I", "K4-I"]
SIDE = {t: ("R" if t.startswith("R") else "K") for t in TESTS}
HAS_TOOL = {"R1": False, "R2": False, "R3": True, "R4": True, "R5": True, "R6": True, "K3": True, "K4": True,
            "R4-I": True, "K4-I": True}
# Status lines per test (paper Table 2; D68): R5 is R2 with the tool; R6 is R5 plus the forged reinstatement.
LABEL_TESTS = ("R2", "R5", "R6", "K4", "K4-I")      # print "Publication type: Retracted Publication"
REINSTATEMENT_TESTS = ("R4", "R4-I", "R6")          # print the forged "Notice of reinstatement"
FORGED_TESTS = ("R4", "R4-I", "R6", "K4", "K4-I")   # contain a forged status line
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def pubmed_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{y} {MONTHS[m - 1]} {d}"


def month_year(iso):
    y, m, _ = (int(x) for x in iso.split("-"))
    return f"{datetime.date(y, m, 1):%B} {y}"


def authors_str(names):
    names = [n for n in names if n]
    return ", ".join(names[:3]) + (", et al." if len(names) > 3 else "")


def tools_chat():
    return [{"type": "function", "function": {"name": TOOL_NAME, "description": TOOL_DESC, "parameters": TOOL_PARAMS}}]


def tools_responses():
    return [{"type": "function", "name": TOOL_NAME, "description": TOOL_DESC, "parameters": TOOL_PARAMS}]


def status_lines(test, side_item):
    """side_item: the frozen 'R' or 'K' half of a topic item (build_items.py)."""
    t = side_item["target"]
    if test in ("R2", "R5", "R6"):
        label = RETRACTION_LABEL.format(journal=t["journal"], date=pubmed_date(t["retraction_date"]),
                                        notice_doi=t["retraction_doi"])
        if test != "R6":
            return label
    if test in REINSTATEMENT_TESTS:
        f = side_item["forged"]
        note = REINSTATEMENT_NOTE.format(journal=t["journal"], date=pubmed_date(f["date"]), notice_doi=f["doi"],
                                         retraction_month=month_year(t["retraction_date"]))
        return label + note if test == "R6" else note  # R6: the true label first, then the forged update
    if test in ("K4", "K4-I"):
        f = side_item["forged"]
        return RETRACTION_LABEL.format(journal=t["journal"], date=pubmed_date(f["date"]), notice_doi=f["doi"])
    return ""


def render(test, side_item):
    """Return (system, user, tools?) for one test of one topic side."""
    blocks = []
    for n, r in enumerate(side_item["results"], 1):
        st = status_lines(test, side_item) if r["is_target"] else ""
        blocks.append(RESULT.format(sid=f"S{n}", title=r["title"], authors=authors_str(r["authors"]),
                                    journal=r["journal"], year=r["year"], doi=r["doi"], status=st,
                                    abstract=r["abstract"]))
    system = SYSTEM + (" " + INSTRUCTION if test.endswith("-I") else "")
    user = USER.format(results="\n\n".join(blocks), topic=side_item["topic"])
    return system, user, HAS_TOOL[test]



def render_status(side_item):
    """Status question (section 3.3): no search results, no tool, same system prompt as the tests."""
    t = side_item["target"]
    return SYSTEM, STATUS_Q.format(title=t["title"], authors=authors_str(t["authors"])), False


# ---- abstract cleaning (D62): publisher boilerplate is not part of the paper's content ----
_BOILER = [
    # trailing copyright / publisher statement, from "Copyright", "©" or "(c) <year>" to the end
    re.compile(r"(?:(?<=[.!?\])])|^)\s*(?:Copyright\b\s*(?:©|\(c\))?|©|\(c\)(?=\s*\d{4}))[^©]{0,400}$", re.I | re.S),
    re.compile(r"\s*This article is protected by copyright\.?\s*All rights reserved\.?\s*$", re.I),
    # a trailing journal citation line left before the copyright line, e.g. "J. Cell. Biochem. 117: 2719-2736, 2016."
    re.compile(r"(?<=[.!?])\s+[A-Z][A-Za-z.\s]{2,40}\s\d+:\s*\d+-\d+,\s*\d{4}\.?\s*$"),
    # figure and image pointers left from the publisher's page
    re.compile(r"\s*\((?:Fig\.?|Figure)\s*graphical abstract\)", re.I),
    re.compile(r"\s*\[Image: see text\]", re.I),
]


def clean_abstract(text):
    """(cleaned text, list of removed strings). Applied to every abstract before drafting and before items are
    built: targets, controls and other results alike."""
    out, removed = text or "", []
    for pat in _BOILER:
        m = pat.search(out)
        while m and m.group().strip():
            removed.append(m.group().strip())
            out = (out[:m.start()] + out[m.end():]).strip()
            m = pat.search(out)
    return out, removed


# ---- registry tool (frozen Retraction Watch snapshot) ----
class Registry:
    def __init__(self, rw_csv):
        self.rec, self.by_notice = {}, {}
        for r in csv.DictReader(open(rw_csv, encoding="utf-8", errors="replace")):
            doi = r["OriginalPaperDOI"].strip().lower()
            if doi and doi != "unavailable":
                self.rec.setdefault(doi, []).append(r)
            ndoi = self.norm(r.get("RetractionDOI"))
            if ndoi and ndoi != "unavailable":
                self.by_notice.setdefault(ndoi, []).append(r)

    @staticmethod
    def _notice(r):
        dt = datetime.datetime.strptime(r["RetractionDate"].split()[0], "%m/%d/%Y").date().isoformat()
        return {"notice_type": r["RetractionNature"], "date": dt,
                "reasons": [x.strip().lstrip("+") for x in r["Reason"].split(";") if x.strip()],
                "notice_doi": r["RetractionDOI"].strip() or None}

    @staticmethod
    def norm(doi):
        d = (doi or "").strip().lower()
        d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d)
        return d.removeprefix("doi:").strip()

    def lookup(self, doi):
        """Article DOI: its notices. A DOI with no article record that is itself a notice DOI (for example the
        notice DOI returned by an earlier lookup) returns that notice and the article(s) it concerns, so the tool
        never answers "no notice" for a real notice."""
        d = self.norm(doi)
        if d not in self.rec and d in self.by_notice:
            rows = sorted(self.by_notice[d], key=lambda r: r["Record ID"])
            return {"doi": d, "data_as_of": SNAPSHOT_DATE,
                    "doi_is_notice_for": sorted({r["OriginalPaperDOI"].strip().lower() for r in rows}),
                    "notices": [self._notice(r) for r in rows],
                    "message": "This DOI is a notice; it concerns the article DOI(s) listed in doi_is_notice_for."}
        notices = []
        for r in sorted(self.rec.get(d, []), key=lambda r: r["Record ID"]):
            notices.append(self._notice(r))
        out = {"doi": d, "data_as_of": SNAPSHOT_DATE}
        if notices:
            out["notices"] = notices
        else:
            out["notices"] = []
            out["message"] = "No notice recorded for this DOI."
        return out


# ---- pre-send checks (D50): any failure stops the run ----
def precheck(test, side_item, system, user, tools_on):
    errs = []
    t = side_item["target"]
    pos = side_item["target_position"]
    blocks = re.findall(r"(?m)^\[S(\d+)\] ", user)
    if f"[S{pos}] {t['title']}" not in user:
        errs.append("target not at its seeded position")
    label = "Publication type: Retracted Publication" in user
    reinst = "Notice of reinstatement" in user
    if test in ("R2", "R5", "R6") and not label:
        errs.append(test + " label missing")
    if test in ("K4", "K4-I") and not label:
        errs.append("forged retraction missing")
    if label and test not in LABEL_TESTS:
        errs.append("retraction label in a test that must not have it")
    if test in REINSTATEMENT_TESTS and not reinst:
        errs.append("forged reinstatement missing")
    if reinst and test not in REINSTATEMENT_TESTS:
        errs.append("reinstatement note in a test that must not have it")
    if user.count("Publication type: Retracted Publication") > 1 or user.count("Notice of reinstatement") > 1:
        errs.append("a status line is printed more than once")
    if tools_on != HAS_TOOL[test]:
        errs.append("tool offered in the wrong test")
    if (INSTRUCTION in system) != test.endswith("-I"):
        errs.append("instruction sentence in the wrong test")
    if re.search(r"retract|reinstat", strip_status(user), re.I):
        errs.append("retraction words outside the planned status lines")
    if "true_status" in user or "is_target" in user:
        errs.append("internal field leaked into the prompt")
    if blocks != ["1", "2", "3", "4", "5"]:
        errs.append("not exactly five results, numbered S1-S5")
    return errs


def strip_status(user):
    """User text minus the planned status lines, to check nothing else mentions retraction."""
    out = []
    for line in user.split("\n"):
        if line.startswith(("Publication type: Retracted Publication", "Retraction in:", "Update in: Notice of reinstatement")):
            continue
        out.append(line)
    return "\n".join(out)


def same_except_status(user_a, user_b):
    return strip_status(user_a) == strip_status(user_b)
