"""Rebuild cost and time files from HTTP logs (paper section 4, Appendix I).

Usage: python3 -I code/costs.py --logs RUN_DIR [RUN_DIR ...] --output OUTPUT_DIR
       [--snapshot MODELS.json] [--estimate ESTIMATE.csv]
       [--credits CREDITS.csv] [--author-hours AUTHOR_HOURS.csv]

No network calls. Output must be outside data/. Each HTTP attempt has one row,
including failures and requests without responses. Unknown usage stays blank;
summary known subtotals and coverage counts are separate from complete totals.
Dry-run charges are zero actual dollars; synthetic usage is kept in separate
summary columns and never compared as actual spending with the live estimate.
Catalogue token prices are list-price comparisons, not pinned-endpoint invoices.
The supplied estimate CSV is preserved by scenario/phase/source phase/model/test.
Credits and working hours are read only, with no free-text notes copied. Deposits
cannot identify which credit source funded a request; source allocation is unknown.
Historical logs without environment or job context retain explicit missing values.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path

REQUEST_FIELDS = ('phase', 'role', 'test', 'topic_id', 'attempt', 'sent_utc', 'received_utc', 'seconds',
                  'model_requested', 'model_returned', 'provider', 'input_tokens', 'output_tokens',
                  'reasoning_tokens', 'cached_tokens', 'cost_usd', 'list_price_usd', 'stop_reason',
                  'error_code', 'error_message', 'response_id')
SUMMARY_FIELDS = ('phase', 'source_phase', 'role', 'model_requested', 'requests', 'failed_requests',
                  'uncertain_requests', 'input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_tokens',
                  'input_tokens_known', 'output_tokens_known', 'reasoning_tokens_known', 'cached_tokens_known',
                  'missing_input_tokens', 'missing_output_tokens', 'missing_reasoning_tokens', 'missing_cached_tokens',
                  'cost_usd', 'cost_usd_known', 'missing_cost_requests', 'list_price_usd', 'list_price_usd_known',
                  'missing_list_price_requests', 'elapsed_hours', 'request_seconds', 'synthetic_reported_cost_usd',
                  'credit_source')
ENVIRONMENT_FIELDS = ('run_id', 'phase', 'dry', 'python_version', 'package_versions', 'operating_system',
                      'git_commit', 'code_sha256', 'start_utc', 'end_utc', 'elapsed_hours')
ESTIMATE_FIELDS = ('scenario', 'phase', 'source_phase', 'role', 'model_id', 'provider', 'test',
                   'estimate_usd', 'actual_cost_usd', 'actual_known_usd', 'difference_usd',
                   'actual_requests', 'missing_cost_requests', 'coverage')


def number(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def csv_rows(path):
    if not path:
        return []
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def save_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def timestamp(value):
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def seconds_between(start, end):
    a, b = timestamp(start), timestamp(end)
    return b-a if a is not None and b is not None and b >= a else None


def phase_name(phase, test):
    # The runner records the knowledge check as phase "knowledge_check"; the estimate calls it "knowledge check".
    phase = {'main':'main run', 'knowledge':'knowledge check', 'knowledge_check':'knowledge check',
             'aux':'knowledge check'}.get(phase, phase or '')
    if phase == 'main run' and test in ('R4-I', 'K4-I'):
        phase = 'instruction test'
    return phase


def read_snapshot(path):
    if not path:
        return {}
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    models = raw.get('data', []) if isinstance(raw, dict) else raw
    return {m['id']: m.get('pricing', {}) for m in models}


def list_cost(model, input_tokens, output_tokens, prices):
    price = prices.get(model, {})
    pin, pout = number(price.get('prompt')), number(price.get('completion'))
    if None in (input_tokens, output_tokens, pin, pout):
        return None
    return input_tokens*pin + output_tokens*pout


def discover(paths):
    found = set()
    for raw in paths:
        path = Path(raw).resolve()
        candidates = [path] if path.is_file() else [path/'http.jsonl', path/'drafting-http.jsonl',
                        path/'judging/http.jsonl', path/'judging-dry/http.jsonl']
        found.update(p for p in candidates if p.is_file())
    if not found:
        raise ValueError('no HTTP attempt logs found')
    return sorted(found)


def usage(body, api):
    raw = body.get('usage') or {}
    if api == 'responses':
        return dict(input_tokens=number(raw.get('input_tokens')), output_tokens=number(raw.get('output_tokens')),
                    reasoning_tokens=number((raw.get('output_tokens_details') or {}).get('reasoning_tokens')),
                    cached_tokens=number((raw.get('input_tokens_details') or {}).get('cached_tokens')))
    return dict(input_tokens=number(raw.get('prompt_tokens')), output_tokens=number(raw.get('completion_tokens')),
                reasoning_tokens=number((raw.get('completion_tokens_details') or {}).get('reasoning_tokens')),
                cached_tokens=number((raw.get('prompt_tokens_details') or {}).get('cached_tokens')))


def request_rows(path, run_id, prices):
    records = read_jsonl(path)
    manifest_path = path.parent/'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    requests, terminal = {}, {}
    for record in records:
        uid, kind = record.get('uid'), record.get('kind')
        if not uid:
            raise ValueError('HTTP record is missing its request ID')
        dest = requests if kind == 'request' else terminal if kind in ('response', 'error') else None
        if dest is None:
            continue
        if uid in dest:
            raise ValueError('duplicate HTTP request or terminal ID; legacy logs require disambiguation')
        dest[uid] = record
    if set(terminal)-set(requests):
        raise ValueError('HTTP terminal record lacks its request')
    rows = []
    for uid, req in requests.items():
        end = terminal.get(uid)
        body = end.get('body') if end else None
        body = body if isinstance(body, dict) else {}
        request_body = req.get('body') or {}
        api = req.get('api') or ('responses' if req.get('path') == 'responses' else 'chat')
        test = 'status question' if req.get('test') == 'SQ' else req.get('test', '')
        dry = bool(req.get('dry', manifest.get('dry', False)))
        source_phase = phase_name(req.get('source_phase', ''), req.get('test'))
        phase = phase_name(req.get('phase') or manifest.get('phase'), req.get('test'))
        if dry:
            source_phase = source_phase or phase
            phase = 'dry run'
        role = req.get('role') or ('judge' if req.get('judge') else 'tested model')
        model = req.get('model_requested') or request_body.get('model', '')
        counts = usage(body, api)
        reported_cost = number((body.get('usage') or {}).get('cost'))
        choices = body.get('choices') or [{}]
        stop = body.get('status') if api == 'responses' else choices[0].get('finish_reason')
        error = body.get('error')
        error = error if isinstance(error, dict) else {'message':error} if error else {}
        error_code = error.get('code')
        if error_code is not None and not str(error_code).isdigit():
            error_code = 'provider_error'
        if end and end.get('kind') == 'error':
            error_code = end.get('http_status') or 'transport'
        if end is None:
            error_code = 'uncertain'
        failed = end is None or bool(error) or (end.get('kind') == 'error' if end else False)
        secs = number(end.get('seconds')) if end else None
        if secs is None and end:
            secs = seconds_between(req.get('utc'), end.get('utc'))
        row = dict(phase=phase, role=role, test=test, topic_id=req.get('topic_id', ''),
                   attempt=req.get('attempt'), sent_utc=req.get('utc'), received_utc=end.get('utc') if end else None,
                   seconds=secs, model_requested=model, model_returned=body.get('model'), provider=body.get('provider'),
                   **counts, cost_usd=0.0 if dry else reported_cost,
                   list_price_usd=0.0 if dry else list_cost(model, counts['input_tokens'], counts['output_tokens'], prices),
                   stop_reason=stop, error_code=error_code,
                   error_message=('response not recorded; charge unknown' if end is None else 'request failed') if failed else '',
                   response_id=body.get('id'), source_phase=source_phase, _dry=dry, _run_id=run_id,
                   _failed=failed, _uncertain=end is None, _synthetic_cost=reported_cost if dry else None,
                   _provider_requested=req.get('provider_requested') or
                       (((request_body.get('provider') or {}).get('only') or [None])[0]
                        if isinstance(request_body.get('provider'), dict) else None))
        rows.append(row)
    return rows


def totals(rows, field):
    """(complete total or None, known total, number unknown). A request that failed with a recorded error and
    reported nothing for the field is not charged and is left out; a request whose reply was never recorded stays
    unknown (D66)."""
    rows = [r for r in rows if not (r.get('_failed') and not r.get('_uncertain') and r.get(field) is None)]
    known = [r[field] for r in rows if r.get(field) is not None]
    return (sum(known) if len(known)==len(rows) else None), sum(known), len(rows)-len(known)


def summaries(rows):
    groups = {}
    for row in rows:
        key = tuple(row.get(k, '') for k in ('phase','source_phase','role','model_requested'))
        groups.setdefault(key, []).append(row)
    output = []
    for key, group in sorted(groups.items()):
        row = dict(zip(('phase','source_phase','role','model_requested'), key))
        row.update(requests=len(group), failed_requests=sum(r['_failed'] for r in group),
                   uncertain_requests=sum(r['_uncertain'] for r in group), credit_source='not inferable from request logs')
        for field in ('input_tokens','output_tokens','reasoning_tokens','cached_tokens'):
            row[field], row[field+'_known'], row['missing_'+field] = totals(group, field)
        row['cost_usd'], row['cost_usd_known'], row['missing_cost_requests'] = totals(group, 'cost_usd')
        row['list_price_usd'], row['list_price_usd_known'], row['missing_list_price_requests'] = totals(group, 'list_price_usd')
        row['request_seconds'] = totals(group, 'seconds')[0]
        row['synthetic_reported_cost_usd'] = sum(r['_synthetic_cost'] or 0 for r in group) if any(r['_dry'] for r in group) else None
        spans, incomplete = {}, False
        for r in group:
            start, end = timestamp(r['sent_utc']), timestamp(r['received_utc'])
            if start is None or end is None:
                incomplete = True
            else:
                a,b = spans.get(r['_run_id'], (start,end))
                spans[r['_run_id']] = min(a,start), max(b,end)
        row['elapsed_hours'] = None if incomplete else sum(b-a for a,b in spans.values())/3600
        output.append(row)
    return output


def environment(path, run_id):
    ep = path.parent/'events.jsonl'
    events = read_jsonl(ep) if ep.exists() else []
    mp = path.parent/'manifest.json'
    manifest = json.loads(mp.read_text()) if mp.exists() else {}
    starts = [e for e in events if 'started' in e.get('event','')]
    ends = [e for e in events if 'ended' in e.get('event','')]
    first = starts[0] if starts else {}
    start, end = first.get('utc'), ends[-1].get('utc') if ends else None
    duration = seconds_between(start,end)
    return dict(run_id=run_id, phase=manifest.get('phase') or ('judging' if 'judging' in path.parent.name else ''),
                dry=manifest.get('dry'), python_version=first.get('python'),
                package_versions=json.dumps(first['packages'],sort_keys=True) if 'packages' in first else None,
                operating_system=first.get('platform'), git_commit=first.get('git_commit'),
                code_sha256=json.dumps(first['code_sha256'],sort_keys=True) if 'code_sha256' in first else None,
                start_utc=start,end_utc=end,elapsed_hours=duration/3600 if duration is not None else None)


def compare_estimate(estimates, rows):
    result = []
    matched = set()
    for expected in estimates:
        phase, source = expected.get('phase',''), expected.get('source_phase','')
        selected = [r for r in rows if not r['_dry'] and r['phase']==phase and r['source_phase']==source
                    and r['role']==expected.get('role') and r['model_requested']==expected.get('model_id')
                    and r['test']==expected.get('test','') and
                    (not expected.get('provider') or r['_provider_requested']==expected['provider'])]
        matched.update(id(r) for r in selected)
        complete, known, missing = totals(selected, 'cost_usd')
        estimate = number(expected.get('estimate_usd'))
        if estimate is None:
            raise ValueError('estimate CSV needs nonnegative finite estimate_usd values')
        actual = complete if selected else None
        result.append(dict(scenario=expected.get('scenario',''),phase=phase,source_phase=source,
                           role=expected.get('role',''),model_id=expected.get('model_id',''),
                           provider=expected.get('provider',''),test=expected.get('test',''), estimate_usd=estimate,
                           actual_cost_usd=actual,actual_known_usd=known if selected else None,
                           difference_usd=actual-estimate if actual is not None else None,
                           actual_requests=len(selected),missing_cost_requests=missing,
                           coverage='not run' if not selected else 'unknown charges' if missing else 'observed requests only'))
    extras = {}
    for row in rows:
        if not row['_dry'] and id(row) not in matched:
            key = (row['phase'], row['source_phase'], row['role'], row['model_requested'],
                   row['_provider_requested'] or '', row['test'])
            extras.setdefault(key, []).append(row)
    for key, group in sorted(extras.items()):
        actual, known, missing = totals(group, 'cost_usd')
        result.append(dict(zip(('phase','source_phase','role','model_id','provider','test'),key),
                           scenario='not estimated',estimate_usd=None,actual_cost_usd=actual,
                           actual_known_usd=known,difference_usd=None,actual_requests=len(group),
                           missing_cost_requests=missing,coverage='not in supplied estimate'))
    return result


def manual_summary(credits, hours):
    allowed = {'paid (OpenRouter)', 'sponsor credits', 'sponsor credits (Adaption, from the sprint)', 'free tier'}
    deposits = {}
    for row in credits:
        source = row.get('source','') if row.get('source','') in allowed else 'other source'
        unit = row.get('unit','') if row.get('unit','') in ('USD','credits') else 'other unit'
        amount = number(row.get('amount'))
        if amount is not None:
            deposits[(source,unit)] = deposits.get((source,unit),0)+amount
    work = {}
    for row in hours:
        phase = row.get('phase','')
        if phase not in ('design','data','harness','runs','human check','analysis','writing'):
            phase = 'other phase'
        value = number(row.get('hours'))
        if value is not None:
            work[phase] = work.get(phase,0)+value
    return dict(credits_rows_read=len(credits), author_hours_rows_read=len(hours),
                deposits=[dict(source=s,unit=u,amount=v) for (s,u),v in sorted(deposits.items())],
                author_hours_by_phase=work, credit_source_allocation='not inferable from deposits and request logs',
                notes='Free-text notes, account details and personal identifiers are not exported.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--logs', nargs='+', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--snapshot'); ap.add_argument('--estimate')
    ap.add_argument('--credits'); ap.add_argument('--author-hours')
    args = ap.parse_args()
    try:
        output = Path(args.output).resolve()
        protected = Path(__file__).resolve().parents[1]/'data'
        if output == protected or protected in output.parents:
            raise ValueError('output must be outside data/')
        prices, rows, environments = read_snapshot(args.snapshot), [], []
        for index, path in enumerate(discover(args.logs), 1):
            run_id = 'run-'+str(index)
            rows.extend(request_rows(path, run_id, prices))
            environments.append(environment(path, run_id))
        estimates = csv_rows(args.estimate)
        manual = manual_summary(csv_rows(args.credits), csv_rows(args.author_hours))
        manual.update(unattributed_requests=sum(not r['topic_id'] or not r['model_requested'] for r in rows),
                      estimates_supplied=bool(args.estimate),snapshot_supplied=bool(args.snapshot),
                      historical_environment_missing=sum(not e['python_version'] or not e['git_commit'] for e in environments))
        output.mkdir(parents=True,exist_ok=True)
        save_csv(output/'requests.csv', REQUEST_FIELDS, rows)
        save_csv(output/'summary.csv', SUMMARY_FIELDS, summaries(rows))
        save_csv(output/'estimate_vs_actual.csv', ESTIMATE_FIELDS, compare_estimate(estimates,rows))
        save_csv(output/'environment.csv', ENVIRONMENT_FIELDS, environments)
        (output/'cost_coverage.json').write_text(json.dumps(manual,indent=2)+'\n',encoding='utf-8')
        print(f'Cost files: {len(rows)} requests; {sum(r["_uncertain"] for r in rows)} without recorded response; '
              f'{sum(r["cost_usd"] is None for r in rows)} unknown charges; {sum(r["_dry"] for r in rows)} dry requests.')
    except (OSError, ValueError, KeyError, TypeError) as error:
        ap.error(str(error))


if __name__ == '__main__':
    main()
