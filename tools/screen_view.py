"""Readable screening page: turns a screening sheet into one local HTML page with full abstracts and
include / exclude buttons. Decisions are kept in the browser while you work and downloaded as a small CSV,
which tools/merge_decisions.py writes back into the sheet.

Usage:
  python3 -I tools/screen_view.py data/work/draw/screening.csv        -> data/work/draw/screening.html
  python3 -I tools/screen_view.py data/work/pilot/screening.csv
  python3 -I tools/screen_view.py data/work/draw/control_screening.csv

Works with the paper sheet (code/draw.py) and the control sheet (code/controls.py). The page is self-contained:
no network, nothing leaves the computer.
"""
import csv, html, json, os, re, sys

sheet = sys.argv[1]
rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
DEC, WHY = "decision (include / exclude)", "reason if excluded"
control = "target_rw_record_id" in rows[0]
key = (lambda r: f"{r['target_rw_record_id']}|{r['doi']}") if control else (lambda r: r["rw_record_id"])
LABELS = ("BACKGROUND|OBJECTIVES?|AIMS?|PURPOSE|INTRODUCTION|METHODS?|MATERIALS AND METHODS|DESIGN|SETTING|"
          "PARTICIPANTS|PATIENTS|INTERVENTIONS?|MEASUREMENTS|MAIN OUTCOME MEASURES|RESULTS?|FINDINGS|CONCLUSIONS?|"
          "INTERPRETATION|SIGNIFICANCE|IMPORTANCE|CONTEXT|LIMITATIONS|CLINICAL RELEVANCE|TRIAL REGISTRATION")
LAB = re.compile(r"(?:^|(?<=[.!?)\]]\s))(" + LABELS + r"|" + LABELS.title() + r")(?: AND RELEVANCE)?\s*:\s", re.I)


def abstract_html(text):
    text = html.escape(text or "")
    parts = LAB.split(text)
    if len(parts) < 3:
        return f"<p>{text}</p>"
    out = [f"<p>{parts[0].strip()}</p>"] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        out.append(f"<p><b>{parts[i].strip().capitalize()}.</b> {parts[i + 1].strip()}</p>")
    return "".join(out)


# OpenAlex field codes of health and life-science subfields (first two digits of the subfield ID). A paper outside
# them gets a "check the field" flag: a hint only, many flagged papers are still health research.
HEALTH_FIELDS = {"13", "24", "27", "28", "29", "30", "32", "34", "35", "36"}
elig = {}
ep = os.path.join(os.path.dirname(sheet), "eligible.json")
if os.path.exists(ep):
    elig = {r["id"]: r for r in json.load(open(ep, encoding="utf-8"))}

cards = []
for n, r in enumerate(rows):
    now = (r.get("screen now") or "").strip().lower() == "yes"
    if control:
        head = (f"<div class=meta>For retracted paper #{html.escape(r['target_rank'])}: "
                f"<i>{html.escape(r['target_title'])}</i></div>"
                f"<div class=meta>Candidate {html.escape(r['candidate_order'])} · {html.escape(r['journal'] or '')} "
                f"({html.escape(r['publication_year'] or '')}) · matched by {html.escape(r['match_level'] or '')} · "
                f"{html.escape(r['cites'] or '')} citations · DOI {html.escape(r['doi'])}</div>")
    else:
        head = (f"<div class=meta>#{html.escape(r['rank'])} · {html.escape(r['journal'])} "
                f"({html.escape(r['publication_year'])}) · {html.escape(r['openalex_subfield'] or '')}</div>")
    types = html.escape(r.get("pubmed_types") or "")
    sid = ((elig.get(r.get("rw_record_id") or "") or {}).get("subfield_id") or "").rsplit("/", 1)[-1]
    flag = (f"<div class=flag>Check the field: OpenAlex files this under {html.escape(r.get('openalex_subfield') or '')}, "
            f"outside health and life sciences. Exclude if it has no human-health aim.</div>") if sid and sid[:2] not in HEALTH_FIELDS else ""
    cards.append(f"""
<section class="card {'now' if now else 'reserve'}" data-key="{html.escape(key(r))}" data-now="{int(now)}">
  <div class=tag>{'Screen now' if now else 'Reserve: only if asked'}</div>
  <h2>{html.escape(r['title'])}</h2>{head}{flag}
  <div class=meta>PubMed type: {types or 'not in PubMed'} · abstract from {html.escape(r.get('abstract_source') or '')}</div>
  <div class=abs>{abstract_html(r['abstract'])}</div>
  <div class=act>
    <button class=inc>Include</button><button class=exc>Exclude</button>
    <input class=why placeholder="Reason if excluded (required)">
    <span class=state></span>
  </div>
</section>""")

pre = {key(r): {"d": (r[DEC] or "").strip().lower(), "w": (r[WHY] or "").strip()} for r in rows if (r[DEC] or "").strip()}
store = "screen:" + os.path.abspath(sheet)
out_name = os.path.basename(sheet)[:-4] + "_decisions.csv"
criteria = ("Include a candidate control if it is (1) health research and (2) an original research article, not a "
            "review, editorial, protocol or notice. The first included candidate becomes the control."
            if control else
            "Include if (1) health research and (2) an original research article, not a review, editorial, protocol "
            "or notice. Excluding a paper frees its journal for the next paper in the order.")
page = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>Screening</title><style>
:root{{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--mute:#666;--line:#ddd;--inc:#1f7a3a;--exc:#a33;}}
@media (prefers-color-scheme: dark){{:root{{--bg:#161615;--card:#1f1f1d;--ink:#eee;--mute:#aaa;--line:#333;--inc:#5bc27a;--exc:#e07070;}}}}
body{{background:var(--bg);color:var(--ink);font:17px/1.6 Georgia,serif;margin:0;padding:0 16px 120px}}
main{{max-width:760px;margin:auto}} header{{position:sticky;top:0;background:var(--bg);padding:12px 0;border-bottom:1px solid var(--line);z-index:2}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px 24px;margin:20px 0}}
.card.reserve{{opacity:.75}} h2{{font-size:21px;line-height:1.35;margin:6px 0 8px}}
.meta{{color:var(--mute);font:14px/1.5 system-ui,sans-serif}} .tag{{font:12px system-ui;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}}
.abs p{{margin:.6em 0}} .act{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:14px;font:15px system-ui}}
button{{font:15px system-ui;padding:6px 14px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}}
.card.d-include{{border-left:6px solid var(--inc)}} .card.d-exclude{{border-left:6px solid var(--exc)}}
.d-include .inc{{background:var(--inc);color:#fff}} .d-exclude .exc{{background:var(--exc);color:#fff}}
.why{{flex:1;min-width:200px;font:15px system-ui;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}}
.state{{color:var(--exc);font-size:13px}} .flag{{margin:8px 0;padding:6px 10px;border-radius:6px;background:#f6e7b0;color:#4a3b00;font:14px system-ui}} .bar{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;font:15px system-ui}}
</style></head><body><main>
<header><div class=bar><b id=count></b><label><input type=checkbox id=onlynow checked> screen-now only</label>
<button id=dl>Download decisions</button></div><div class=meta>{html.escape(criteria)} Decisions are saved in this browser as you go.</div></header>
{''.join(cards)}
</main><script>
const KEY={json.dumps(store)}, PRE={json.dumps(pre)};
let D={{}}; try{{D=JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{}}
for(const k in PRE) if(!D[k]) D[k]=PRE[k];
function save(){{try{{localStorage.setItem(KEY,JSON.stringify(D))}}catch(e){{}}; paint()}}
function paint(){{let done=0,total=0;
 document.querySelectorAll('.card').forEach(c=>{{const k=c.dataset.key,v=D[k]||{{}};
  c.classList.toggle('d-include',v.d==='include');c.classList.toggle('d-exclude',v.d==='exclude');
  const w=c.querySelector('.why'); if(document.activeElement!==w) w.value=v.w||'';
  c.querySelector('.state').textContent=(v.d==='exclude'&&!v.w)?'add a reason':'';
  c.style.display=(document.getElementById('onlynow').checked&&c.dataset.now==='0'&&!v.d)?'none':'';
  if(c.dataset.now==='1'){{total++; if(v.d==='include'||(v.d==='exclude'&&v.w)) done++;}}}});
 document.getElementById('count').textContent=done+' of '+total+' screen-now decided';}}
document.querySelectorAll('.card').forEach(c=>{{const k=c.dataset.key;
 c.querySelector('.inc').onclick=()=>{{D[k]={{d:'include',w:''}};save()}};
 c.querySelector('.exc').onclick=()=>{{D[k]={{d:'exclude',w:(D[k]||{{}}).w||''}};save();c.querySelector('.why').focus()}};
 c.querySelector('.why').oninput=e=>{{D[k]=Object.assign({{d:'exclude'}},D[k]||{{}},{{w:e.target.value}});if(D[k].d!=='exclude')D[k].d='exclude';save()}};}});
document.getElementById('onlynow').onchange=paint;
document.getElementById('dl').onclick=()=>{{const q=s=>'"'+String(s).replace(/"/g,'""')+'"';
 let csv='key,decision,reason\\n'; for(const k in D) if(D[k].d) csv+=[q(k),q(D[k].d),q(D[k].w||'')].join(',')+'\\n';
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));a.download={json.dumps(out_name)};a.click();}};
paint();
</script></body></html>"""
dest = sheet[:-4] + ".html"
open(dest, "w", encoding="utf-8").write(page)
print("page:", dest, "| rows:", len(rows), "| decisions already in the sheet:", len(pre))
