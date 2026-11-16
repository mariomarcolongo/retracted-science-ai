"""Readable, read-only development audit; no ratings are written by this viewer."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
def esc(value):
    return html.escape(str(value))

versions = [
    ("v2.1 · MiMo", "drafting-v2.1/pilot", None),
    ("v3 · MiMo", "materials-v3/topics", "materials-v3/question-review"),
    ("v4 · MiMo", "materials-v4/topics", "materials-v4/question-review"),
    ("v4 · Kimi, 4k allowance", "materials-v4-kimi/topics", None),
    ("v4 · Kimi, 16k allowance", "materials-v4-kimi16k/topics", "materials-v4-kimi16k/question-review"),
]
data = []; costs = 0
for label, loc, reviewloc in versions:
    d = ROOT / "data/logs" / loc
    entries = {r["item_code"]: r for r in rows(d / "drafts.jsonl")}
    reviews = rows(ROOT / "data/logs" / reviewloc / "reviews.jsonl") if reviewloc else []
    data.append((label, entries, reviews))
for f in (ROOT / "data/logs").glob("materials-v*/**/summary.json"):
    costs += json.loads(f.read_text()).get("known_cost_usd", 0)
fit_path = ROOT / "data/logs/materials-v4-kimi16k/candidate-review/candidate-fit-summary.json"
fits = json.loads(fit_path.read_text()) if fit_path.exists() else {}
packet_path = ROOT / "data/work/pilot-materials-v4-kimi16k/other_candidates.DEVELOPMENT.json"
packets = json.loads(packet_path.read_text()) if packet_path.exists() else {}
codes = json.loads((ROOT / "data/work/pilot/topic_codes.json").read_text())

body = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
'''<title>Pilot materials: development review</title><style>
body{font:17px/1.55 system-ui;max-width:1100px;margin:auto;padding:28px;background:#f5f6f8;color:#17212c}
h1,h2{line-height:1.2}article{background:white;padding:24px;margin:24px 0;border-radius:12px;border:1px solid #d3dbe3}
.version{padding:16px 0;border-top:1px solid #ddd}.question{font-weight:600}.note{color:#586473;font-size:15px}
.pass{color:#126444}.unresolved{color:#9a350b}summary{cursor:pointer}pre{white-space:pre-wrap}a{color:#175fa0}
table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd}
label{margin-right:15px}select{font:inherit;padding:5px}</style>
<h1>Pilot materials: development review</h1>
<p>All earlier versions and failures are preserved. These are development items, not a held-out validation set.
AI reviewer agreement is not specialist verification. No final experimental packet is approved by this page.</p>''',
f'<p class="note">Additional recorded model cost for v3/v4 development: ${costs:.3f}. This excludes earlier preparation.</p>',
'<label>Show item <select id="item"><option value="all">All six</option>'+''.join(f'<option>{c}</option>' for c in sorted(data[0][1]))+'</select></label>']
for code in sorted(data[0][1]):
    source = data[0][1][code]["source"]
    body += [f'<article data-code="{code}"><h2>{code}</h2><details><summary>Original title and abstract</summary><h3>{esc(source["title"])}</h3><p>{esc(source["abstract"])}</p></details>']
    if code in fits:
        fit = fits[code]
        body.append(f'<h3>Latest retrieval and relevance check</h3><p><b>{len(fit["jointly_passing"])} candidates passed both AI reviewers</b> out of {len(fit["candidates"])} prepared. Final packet approval remains pending.</p>')
        body.append('<details><summary>Candidate papers and decisions</summary><table><tr><th>Rank</th><th>Paper</th><th>Both AI reviewers pass</th></tr>')
        lookup = {p['doi']:p for p in packets.get(codes[code],{}).get('candidates',[])}
        for candidate in fit['candidates']:
            paper = lookup[candidate['doi']]
            body.append(f'<tr><td>{candidate["rank"]}</td><td><a href="https://doi.org/{esc(candidate["doi"])}">{esc(paper["title"])}</a></td><td>{"Yes" if candidate["joint_ai_pass"] else "No / unresolved"}</td></tr>')
        body.append('</table></details>')
    for label, entries, reviews in data:
        r = entries.get(code)
        body.append(f'<section class="version"><h3>{esc(label)}</h3>')
        if not r:
            body.append('<p class="note">No completed response recorded.</p></section>');continue
        body.append(f'<p class="question">{esc(r["draft"] or "No final question returned")}</p>')
        body.append(f'<p class="note">Output: {esc(r["status"])} · {len(r["draft"].split())} words</p>')
        relevant = [x for x in reviews if x["item_code"] == code]
        if not relevant: body.append('<p class="note">No complete formal AI review set recorded for this version.</p>')
        for rev in relevant:
            model = rev["request"]["model"]
            body.append(f'<details><summary class="{"pass" if rev["status"]=="ai_all_criteria_pass" else "unresolved"}">{esc(model)}: {esc(rev["status"])}</summary>')
            if rev.get("validation_error"):body.append(f'<p>{esc(rev["validation_error"])}</p>')
            for criterion, val in rev.get("assessment",{}).get("criteria",{}).items():
                body.append(f'<p><b>{criterion}: {esc(val["decision"])}</b> — {esc(val["reason"])}<br><small>Evidence: “{esc(val["evidence"])}”</small></p>')
            body.append('</details>')
        body.append('</section>')
    body.append('</article>')
body.append('''<script>document.querySelector('#item').onchange=e=>document.querySelectorAll('article').forEach(a=>a.hidden=e.target.value!=='all'&&a.dataset.code!==e.target.value)</script></html>''')
out=ROOT/'results/pilot-materials-development-review.html';out.write_text('\n'.join(body))
print(out)
