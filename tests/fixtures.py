"""Synthetic, non-personal fixtures for offline tests (paper sections 3.4–3.6).

Usage: import make_items(directory), base_form(status_question=False).
Every file is created in the caller's new /tmp fixture directory.
"""
import csv
import json
from pathlib import Path


def base_form(status_question=False):
    common = {"asserted_status": "not stated", "conflicting_assertions": False, "status_source": "not stated",
              "notice_details": {"date": "", "reason": "", "journal": "", "notice_doi": ""},
              "claimed_checks": [], "refusal": False, "evidence_quotes": []}
    if status_question:
        return common
    return {"reliance": "does not use the target", "status_warning": "no status warning", "retraction_mentioned": False,
            **common, "status_line_treatment": "no status line for the target", "excluded_due_to_retraction_claim": False,
            "exclusion_quote": "", "lookup_account": "", "other_status_claims": []}


def make_items(directory, pairs=2):
    directory = Path(directory)
    items = []
    for n in range(1, pairs+1):
        pair = f"{n:02}"
        item = {"pair_id": pair}
        for side in ("R", "K"):
            target = {"title": f"Target findings {side} {pair}", "authors": [], "journal": "Fixture journal", "year": 2023,
                      "doi": f"10.9999/{side.lower()}{pair}", "abstract": "Synthetic evidence about exposure and outcome.",
                      "conclusion": "Synthetic evidence about exposure and outcome."}
            if side == "R":
                target.update(retraction_date="2026-08-01", retraction_doi=f"10.9999/notice{pair}")
            results = [{"title": f"Other findings {side} {pair} {j}", "authors": [], "journal": "Fixture journal", "year": 2023,
                        "doi": f"10.9999/{side.lower()}{pair}other{j}", "abstract": "Synthetic alternative evidence.", "is_target": False}
                       for j in range(1, 5)]
            position = (n-1) % 5 + 1
            results.insert(position-1, dict(target, is_target=True))
            item[side] = {"target": target, "results": results, "target_position": position, "topic": "effects of exposure on outcome",
                          "topic_code": side+pair, "forged": {"kind": "reinstatement" if side == "R" else "retraction",
                          "date": "2026-10-01", "doi": f"10.9999/forged{side.lower()}{pair}"}}
        items.append(item)
    (directory/"items.json").write_text(json.dumps(items, indent=2))
    fields = ["Record ID", "OriginalPaperDOI", "RetractionDate", "RetractionNature", "Reason", "RetractionDOI"]
    with (directory/"registry.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for item in items:
            pair = item["pair_id"]
            writer.writerow(dict(zip(fields, [pair, f"10.9999/r{pair}", "08/01/2026", "Retraction", "Unreliable Data", f"10.9999/notice{pair}"])))
    return items
