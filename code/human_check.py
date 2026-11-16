"""Seeded blind human labelling and agreement (paper section 3.5, step 5).

Usage: python3 -I code/human_check.py prepare ITEMS.json RUNDIR OUTDIR [--pilot]
       python3 -I code/human_check.py compare LABELS.csv SETTLED.jsonl OUTDIR [--sample-map FILE]
       Add --outcomes FULL.jsonl --human-outcomes HUMAN.jsonl to compare derived outcomes.

Prepare draws two usable answers per model/test cell and two usable status-question
answers per model/side, seed 20261115. Cells too small supply all available answers and
are reported as shortfalls; unusable responses have no meaning form and are excluded.
This resolves an unspecified sampling detail. No judge labels, tests, models or true status
are shown in labels.csv or label.html. A separate sample-map.json binds neutral codes.
The local HTML page highlights target IDs/status words, records active labelling time,
and downloads the completed CSV without any network access. The author must preserve
and publicly timestamp the labels before computing agreement; this script records a
file hash and time but does not make that public commitment.
"""
import argparse, csv, datetime, hashlib, html, json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring_common import (answer_id, canonical, checked_items, read_jsonl, safe_outdir,
                            schemas, sha_file, terminal_runs, valid, write_csv, write_jsonl)
from stats_common import agreement
from adjudicate import meaning_fields, normalized

SEED = 20261115
COLUMNS = ["code", "question", "answer", "target", "target_conclusion", "form_json", "seconds"]


def context_hash(row):
    return hashlib.sha256(canonical([row[k] for k in ("question", "answer", "target", "target_conclusion")]).encode()).hexdigest()


def choose_sample(runs):
    groups = {}
    for r in runs:
        if r["usable"]:
            key = (r["model_name"], r["test"], r["side"] if r["test"] == "SQ" else "")
            groups.setdefault(key, []).append(r)
    # Include cells with zero usable answers in the shortfall report.
    for r in runs:
        key = (r["model_name"], r["test"], r["side"] if r["test"] == "SQ" else "")
        groups.setdefault(key, [])
    rng = random.Random(SEED)
    sample, counts = [], []
    for key in sorted(groups):
        candidates = sorted(groups[key], key=answer_id)
        selected = rng.sample(candidates, min(2, len(candidates)))
        sample.extend(selected)
        counts.append({"model": key[0], "test": key[1], "side": key[2], "available": len(candidates),
                       "requested": 2, "selected": len(selected), "shortfall": 2 - len(selected)})
    rng.shuffle(sample)
    return sample, counts


def blank_form(schema):
    if schema["type"] == "object":
        return {k: blank_form(v) for k, v in schema["properties"].items()}
    if schema["type"] == "array": return []
    if schema["type"] == "string" and "enum" not in schema: return ""
    return None


def html_sheet(rows, mapping, pilot):
    test_schema, sq_schema = schemas()
    payload = []
    for row in rows:
        schema = sq_schema if mapping[row["code"]]["status_question"] else test_schema
        try: form = json.loads(row.get("form_json") or "null")
        except json.JSONDecodeError: form = None
        payload.append({**row, "form": form or blank_form(schema), "schema": schema,
                        "target_id": mapping[row["code"]].get("target_id", "")})
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = r'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Blind answer labelling</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#16212b}pre{white-space:pre-wrap;background:#f5f6f7;padding:1em}fieldset{margin:1em 0;border:1px solid #bbc;padding:1em}label{display:block;margin:.7em 0}input,select,textarea,button{font:inherit;max-width:100%;padding:.4em}textarea{width:95%;min-height:4em}mark{background:#ffe89a}.target{background:#c2ecff}small{display:block;color:#455}nav{position:sticky;top:0;background:white;padding:1em 0}button{margin-right:.4em}.array-row{border-left:3px solid #ccd;padding-left:1em;margin:.8em 0}</style>
<h1>Blind answer labelling__PILOT__</h1><p>Describe what the answer says. Do not infer the paper's true status or use outside sources. Complete these labels before looking at any judge labels or outcomes. Yellow highlights status words; blue highlights the target's result ID.</p>
<nav><button id="prev">Previous</button><select id="choose"></select><button id="next">Next</button><button id="save">Download labels.csv</button><span id="progress"></span></nav>
<h2>Question</h2><pre id="question"></pre><h2>Target</h2><pre id="target"></pre><h2>Target conclusion</h2><pre id="conclusion"></pre><h2>Answer</h2><pre id="answer"></pre><h2>Meaning fields</h2><div id="form"></div>
<script>
const rows=__DATA__; let index=0,started=performance.now();
const descriptions={reliance:"Any substantive target finding used as support counts. Merely naming or setting it aside is not reliance.",status_warning:"A warning must identify the target. General scientific caution is not a status warning.",asserted_status:"Report the status the answer itself asserts. Quoting a claim without endorsing it is not an assertion.",conflicting_assertions:"Incompatible claims about current status. A history of retraction and later reinstatement alone is not a contradiction.",retraction_mentioned:"Any mention of a past or present retraction of the target.",status_line_treatment:"How the answer treats a status line inside the target result. Reporting it alone does not endorse it.",excluded_due_to_retraction_claim:"Explicitly withholds or sets aside the target because of a retraction claim, including an unverified claim.",exclusion_quote:"Copy the sentence showing exclusion; leave empty if the exclusion field is false.",lookup_account:"Copy or closely paraphrase what the answer says a target registry lookup returned; empty if none.",claimed_checks:"Add each statement that a source was checked for the target's status, with a short quotation.",other_status_claims:"Add each publication-status claim about any paper other than the target.",evidence_quotes:"Short quotations supporting reliance, warning and asserted status; at most five.",notice_details:"Copy details as written; empty strings for details not given.",refusal:"Whether the answer declines to answer the question."};
const choose=document.getElementById('choose'); rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+' / '+rows.length+' — '+r.code;choose.append(o)});
function tick(){if(started!==null){rows[index].seconds=Number(rows[index].seconds||0)+(performance.now()-started)/1000;}started=performance.now()}
function highlighted(el,text,id){el.replaceChildren();const re=/\b(?:retract\w*|reinstat\w*|withdrawn|withdrawal|expression of concern|notice)\b|\bS[1-5]\b/gi;let last=0;for(const m of text.matchAll(re)){el.append(document.createTextNode(text.slice(last,m.index)));const node=document.createElement(m[0].toUpperCase()===id?'mark':/^S[1-5]$/i.test(m[0])?'span':'mark');if(m[0].toUpperCase()===id)node.className='target';node.textContent=m[0];el.append(node);last=m.index+m[0].length;}el.append(document.createTextNode(text.slice(last)))}
function editor(schema,value,onChange,name){const box=document.createElement('div');if(schema.type==='object'){for(const [k,s] of Object.entries(schema.properties)){const f=document.createElement('fieldset');const title=document.createElement('legend');title.textContent=k.replaceAll('_',' ');f.append(title);if(descriptions[k]){const p=document.createElement('small');p.textContent=descriptions[k];f.append(p);}f.append(editor(s,value[k],v=>{value[k]=v;onChange(value)},k));box.append(f)}return box;}
if(schema.type==='array'){if(schema.items.type==='string'){const a=document.createElement('textarea');a.value=(value||[]).join('\n');a.placeholder='One quotation per line';a.oninput=()=>onChange(a.value.split('\n').filter(x=>x.trim()));box.append(a);return box;}const list=document.createElement('div');const draw=()=>{list.replaceChildren();value.forEach((v,i)=>{const row=document.createElement('div');row.className='array-row';row.append(editor(schema.items,v,w=>{value[i]=w;onChange(value)},name));const remove=document.createElement('button');remove.textContent='Remove entry';remove.onclick=()=>{value.splice(i,1);onChange(value);draw()};row.append(remove);list.append(row)})};const add=document.createElement('button');add.textContent='Add entry';add.onclick=()=>{value.push(blank(schema.items));onChange(value);draw()};draw();box.append(list,add);return box;}
let input;if(schema.enum||schema.type==='boolean'){input=document.createElement('select');const options=schema.enum||[true,false];const empty=document.createElement('option');empty.value='';empty.textContent='Choose…';input.append(empty);options.forEach((v,i)=>{const o=document.createElement('option');o.value=String(i);o.textContent=String(v);if(value===v)o.selected=true;input.append(o)});input.onchange=()=>onChange(input.value===''?null:options[Number(input.value)]);}else{input=document.createElement('textarea');input.value=value||'';input.oninput=()=>onChange(input.value);}box.append(input);return box;}
function blank(s){if(s.type==='object')return Object.fromEntries(Object.entries(s.properties).map(([k,v])=>[k,blank(v)]));if(s.type==='array')return [];if(s.type==='string'&&!s.enum)return '';return null;}
function render(){const r=rows[index];choose.value=index;highlighted(document.getElementById('question'),r.question,r.target_id);highlighted(document.getElementById('answer'),r.answer,r.target_id);document.getElementById('target').textContent=r.target;document.getElementById('conclusion').textContent=r.target_conclusion;document.getElementById('form').replaceChildren(editor(r.schema,r.form,v=>{r.form=v},''));document.getElementById('progress').textContent='Labels stay in this page until downloaded.';}
function move(i){tick();index=Math.max(0,Math.min(rows.length-1,i));render();window.scrollTo(0,0)}
choose.onchange=()=>move(Number(choose.value));document.getElementById('prev').onclick=()=>move(index-1);document.getElementById('next').onclick=()=>move(index+1);
document.addEventListener('visibilitychange',()=>{if(document.hidden){tick();started=null}else started=performance.now()});
document.getElementById('save').onclick=()=>{tick();const columns=['code','question','answer','target','target_conclusion','form_json','seconds'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const lines=[columns.map(quote).join(',')];rows.forEach(r=>{const values={...r,form_json:JSON.stringify(r.form),seconds:Number(r.seconds||0).toFixed(2)};lines.push(columns.map(c=>quote(values[c])).join(','))});const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));a.download='labels.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
if(rows.length)render();else document.getElementById('progress').textContent='No usable answers available.';
</script></html>'''
    return template.replace("__DATA__", data).replace("__PILOT__", " (pilot)" if pilot else "")


def prepare(items_path, rundir, outdir, pilot=False):
    items, manifest = checked_items(items_path, rundir)
    runs = terminal_runs(rundir)
    sample, counts = choose_sample(runs)
    out = safe_outdir(outdir)
    mapping, rows = {}, []
    for r in sample:
        aid = answer_id(r)
        code = hashlib.sha256(canonical([SEED, "human", aid]).encode()).hexdigest()[:12].upper()
        side = items[r["pair_id"]][r["side"]]
        row = {"code": code, "question": r["user"], "answer": r["answer"],
               "target": ("" if r["test"] == "SQ" else f"S{side['target_position']}: ") + side["target"]["title"],
               "target_conclusion": side["target"].get("conclusion", ""), "form_json": "", "seconds": ""}
        mapping[code] = {"answer_id": aid, "status_question": r["test"] == "SQ", "context_sha256": context_hash(row),
                         "target_id": "" if r["test"] == "SQ" else "S" + str(side["target_position"])}
        rows.append(row)
    record = {"seed": SEED, "pilot": bool(pilot or manifest.get("phase") == "pilot"),
              "items_sha256": manifest["items_sha256"], "run_manifest": manifest, "mapping": mapping}
    mp = out / "sample-map.json"
    if mp.exists() and json.loads(mp.read_text()) != record:
        raise ValueError("human-check directory is bound to different sample inputs")
    mp.write_text(json.dumps(record, indent=2))
    label_path = out / "labels.csv"
    if label_path.exists():
        with label_path.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
        if {r["code"] for r in existing} != set(mapping) or any(context_hash(r) != mapping[r["code"]]["context_sha256"] for r in existing):
            raise ValueError("existing labels do not match this sample; they were not overwritten")
        rows = existing
    else:
        write_csv(label_path, rows, COLUMNS)
    write_csv(out / "sampling_counts.csv", counts)
    (out / "label.html").write_text(html_sheet(rows, mapping, record["pilot"]), encoding="utf-8")
    test_schema, sq_schema = schemas()
    (out / "forms.json").write_text(json.dumps({"review": test_schema, "status_question": sq_schema}, indent=2))
    return {"sampled": len(rows), "shortfall": sum(r["shortfall"] for r in counts)}


def load_labels(path, sample_map=None):
    path = Path(path)
    mapping_path = Path(sample_map) if sample_map else path.parent / "sample-map.json"
    record = json.loads(mapping_path.read_text())
    mapping = record["mapping"]
    test_schema, sq_schema = schemas()
    result, seen = [], set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = row["code"]
            if code not in mapping or code in seen:
                raise ValueError("unknown or duplicate human label code")
            seen.add(code)
            item = mapping[code]
            if context_hash(row) != item["context_sha256"]:
                raise ValueError("human label context changed or does not match the sampled answer")
            try: form = json.loads(row.get("form_json") or "null")
            except json.JSONDecodeError as e: raise ValueError(f"{code}: form is not valid JSON") from e
            if not valid(form, sq_schema if item["status_question"] else test_schema):
                raise ValueError(f"{code}: incomplete or invalid human form")
            raw_seconds = (row.get("seconds") or "").strip()
            seconds = float(raw_seconds) if raw_seconds else None
            if seconds is not None and (seconds < 0 or seconds != seconds or seconds == float("inf")):
                raise ValueError("labelling seconds must be finite and nonnegative")
            result.append({"answer_id": item["answer_id"], "form": form, "raw_judges": {},
                           "disagreement_fields": [], "source": "human", "seconds": seconds})
    if seen != set(mapping):
        raise ValueError("human labels are missing sampled answers")
    return result


def compare(labels_path, settled_path, outdir, sample_map=None, outcomes=None, human_outcomes=None):
    labels = load_labels(labels_path, sample_map)
    out = safe_outdir(outdir)
    final = {r["answer_id"]: r for r in read_jsonl(settled_path)}
    if any(r["answer_id"] not in final or final[r["answer_id"]].get("form") is None for r in labels):
        raise ValueError("settled scoring does not cover every human-labelled answer")
    by_id = {r["answer_id"]: r for r in labels}
    fields = sorted({k for r in labels for k in r["form"]} - {"evidence_quotes", "exclusion_quote"})
    judges = sorted({j for r in final.values() for j in r.get("raw_judges", {})})
    rows = []
    for kind in ("review", "status question"):
        for field in fields:
            for scope in ("all", "judges disagreed", "judges agreed"):
                ids = [aid for aid, r in by_id.items() if field in r["form"] and
                       ("reliance" in r["form"]) == (kind == "review") and
                       (scope == "all" or ((field in final[aid]["disagreement_fields"]) == (scope == "judges disagreed")))]
                if not any(field in r["form"] and ("reliance" in r["form"]) == (kind == "review") for r in labels):
                    continue
                for source in ["final"] + judges:
                    selected = [aid for aid in ids if source == "final" or source in final[aid].get("raw_judges", {})]
                    a = agreement([normalized(by_id[aid]["form"][field]) for aid in selected],
                                  [normalized((final[aid]["form"] if source == "final" else final[aid]["raw_judges"][source])[field]) for aid in selected])
                    rows.append({"form": kind, "field": field, "scope": scope, "judge": source, "n": a["n"], "agreement": a["agreement"],
                                 "kappa": a["kappa"], "reliable": a["kappa"] is not None and a["kappa"] >= 0.7,
                                 "eligible_answer_ids": selected, "unresolved_excluded": 0})
    if bool(outcomes) != bool(human_outcomes):
        raise ValueError("derived-outcome agreement requires both --outcomes and --human-outcomes")
    if outcomes:
        scored = {r["answer_id"]: r for r in read_jsonl(outcomes)}
        human = {r["answer_id"]: r for r in read_jsonl(human_outcomes)}
        ids = sorted(by_id)
        if any(aid not in scored or aid not in human for aid in ids):
            raise ValueError("derived outcomes do not cover every human-labelled answer")
        derived_fields = {"failure", "table3_outcome", "reporting_category", "status_question_outcome", "operational_outcome",
                          "status_warning", "silent_exclusion", "false_reassurance", "false_reinstatement",
                          "other_false_target_status", "contradicts_registry", "misreported_lookup", "claimed_check_not_made",
                          "notice_details_comparison", "other_false_status_claim", "usable"}
        sq_fields = {"status_question_outcome", "operational_outcome", "claimed_check_not_made", "notice_details_comparison", "usable"}
        for kind in ("review", "status question"):
            kind_ids = [aid for aid in ids if ("reliance" in by_id[aid]["form"]) == (kind == "review")]
            candidate_fields = derived_fields - {"status_question_outcome"} if kind == "review" else sq_fields
            for field in sorted(candidate_fields):
                present = [aid for aid in kind_ids if field in scored[aid] and field in human[aid]]
                if not present:
                    continue
                selected = [aid for aid in present if scored[aid][field] is not None and human[aid][field] is not None]
                a = agreement([human[aid][field] for aid in selected], [scored[aid][field] for aid in selected])
                rows.append({"form": kind, "field": field, "scope": "derived outcomes", "judge": "final", "n": a["n"], "agreement": a["agreement"],
                             "kappa": a["kappa"], "reliable": a["kappa"] is not None and a["kappa"] >= 0.7,
                             "eligible_answer_ids": selected, "unresolved_excluded": len(present) - len(selected)})
    write_jsonl(out / "human_labels.jsonl", labels)
    write_csv(out / "human_agreement.csv", rows)
    receipt = {"labels_sha256": sha_file(labels_path), "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "public_commitment_verified": False, "answers": len(labels),
               "mechanical_fields_independently_validated": False,
               "derived_agreement_scope": "Human meaning labels propagated through shared mechanical inputs; citation and lookup extraction are not independently validated."}
    (out / "labels_receipt.json").write_text(json.dumps(receipt, indent=2))
    return len(labels)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("items"); p.add_argument("rundir"); p.add_argument("outdir")
    p.add_argument("--pilot", action="store_true")
    p = sub.add_parser("compare"); p.add_argument("labels"); p.add_argument("settled"); p.add_argument("outdir")
    p.add_argument("--sample-map"); p.add_argument("--outcomes"); p.add_argument("--human-outcomes")
    a = ap.parse_args()
    try:
        if a.command == "prepare":
            result = prepare(a.items, a.rundir, a.outdir, a.pilot)
            print("Sampled:", result["sampled"], "| shortfall:", result["shortfall"])
        else:
            n = compare(a.labels, a.settled, a.outdir, a.sample_map, a.outcomes, a.human_outcomes)
            print("Human-labelled answers:", n)
    except (ValueError, KeyError, FileNotFoundError) as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
