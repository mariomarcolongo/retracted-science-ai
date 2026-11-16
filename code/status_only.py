"""Offline SQ-only analysis; ancillary judge fields remain unresolved.

Run: python3 -I code/status_only.py
Uses the author's exported categorical decisions without requiring prose reasons.
Does not produce full-form settled labels or forged-notice experiment results.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adjudicate import load_judgments, decision_code
from human_check import load_labels
from scoring_common import checked_items, terminal_runs, answer_id, sha_file, write_csv, write_jsonl
from stats_common import agreement, wilson
import outcomes

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('asserted_status', 'conflicting_assertions', 'refusal')


def classify(form, side, usable=True):
    if not usable or form['refusal']:
        return None
    status = form['asserted_status']
    if status in ('uncertain', 'not stated') or form['conflicting_assertions']:
        return 'uncertain'
    return 'correct' if status == ('retracted' if side == 'R' else 'not retracted') else 'incorrect'


def main():
    base = ROOT / 'results/status-question'
    export = base / 'status-review/author-status-decisions.csv'
    with export.open(encoding='utf-8-sig') as f:
        decisions_list = list(csv.DictReader(f))
    decisions = {r['code']: r for r in decisions_list}
    assert len(decisions) == len(decisions_list), 'Duplicate author decisions'
    # Later author corrections live in their own file so the original export and its hash stay intact.
    corrections_path = base / 'status-review/author-status-corrections.csv'
    corrections = []
    if corrections_path.exists():
        with corrections_path.open(encoding='utf-8-sig') as f:
            corrections = list(csv.DictReader(f))
        for c in corrections:
            d = decisions[c['code']]
            assert d['field'] == c['field'] and c['reason'].strip(), 'Correction needs a matching field and a reason'
            d['decision'] = c['decision']
    groups, retraction_dates = {}, []
    inputs = [export, Path(__file__).resolve()] + ([corrections_path] if corrections else [])
    for group in ('draw', 'pilot'):
        p = ROOT / f'data/work/{group}/targets.json'
        inputs.append(p)
        for row in json.loads(p.read_text()):
            assert str(row['id']) not in groups
            groups[str(row['id'])] = 'main' if group == 'draw' else 'pilot'
            retraction_dates.append(str(row['retraction_date'])[:10])
    assert Counter(groups.values()) == {'main': 25, 'pilot': 3}
    records, humans, raw, used = [], {}, {}, set()
    ancillary = Counter()
    for batch, folder in (('main', 'status-question'), ('deepseek', 'status-question-deepseek')):
        rundir = ROOT / 'data/logs' / folder
        items_path = ROOT / 'data/work/check_items.json'
        items, manifest = checked_items(items_path, rundir)
        runs = terminal_runs(rundir)
        forms, names, _, _ = load_judgments(rundir, manifest, runs)
        hp = base / batch / 'human/labels.csv'
        inputs.extend([items_path, hp, hp.parent/'sample-map.json', rundir/'runs.jsonl', rundir/'manifest.json', rundir/'judging/manifest.json', rundir/'judging/judging.jsonl'])
        humans.update({h['answer_id']: h['form'] for h in load_labels(hp)})
        mp = base / batch / 'mechanical/mechanical.jsonl'
        inputs.append(mp)
        mechanical = {m['answer_id']: m for m in map(json.loads, mp.read_text().splitlines())}
        for run in runs:
            aid = answer_id(run)
            assert run['test'] == 'SQ' and run['pair_id'] in groups
            row = {k: run[k] for k in ('model_name', 'pair_id', 'side', 'usable')}
            row.update(answer_id=aid, sample=groups[run['pair_id']], batch=batch,
                       operational_outcome=run['outcome'], adjudicated_fields=[], ancillary_fields_adjudicated=False)
            if run['usable']:
                left, right = [forms[aid][n] for n in names]
                raw[aid] = (left, right)
                final = {}
                for field in FIELDS:
                    values = [left[field], right[field]]
                    final[field] = values[0]
                    if values[0] != values[1]:
                        code = decision_code(aid, field, values)
                        d = decisions[code]
                        assert d['batch'] == batch and d['field'] == field
                        assert field == 'asserted_status', 'Additional outcome field requires author adjudication'
                        assert d['decision'] in ('retracted', 'not retracted', 'reinstated', 'other notice', 'uncertain', 'not stated')
                        final[field] = d['decision']
                        used.add(code)
                        row['adjudicated_fields'].append(field)
                row.update(final)
                row['status_question_outcome'] = classify(final, run['side'])
                # Every outcome must equal the frozen scoring (outcomes.derive) on the same settled outcome fields;
                # ancillary fields cannot change the status-question outcome there.
                frozen = outcomes.derive(mechanical[aid], {**left, **final})
                assert frozen['status_question_outcome'] == row['status_question_outcome'], aid
                assert mechanical[aid]['side'] == run['side'] and frozen['usable'] == (not final['refusal']), aid
                if final['refusal']:
                    row['operational_outcome'] = 'refusal'
                records.append(row)
            else:
                row.update({f: None for f in FIELDS})
                row['status_question_outcome'] = None
                records.append(row)
        with (base/batch/'adjudication/decisions.csv').open() as f:
            ancillary.update(r['field'] for r in csv.DictReader(f) if r['field'] not in FIELDS)
    assert used == set(decisions), 'Stale or unused author decision'
    assert len(records) == 504 and len({r['answer_id'] for r in records}) == 504
    counts = Counter((r['model_name'], r['sample'], r['side']) for r in records)
    assert len(counts) == 36 and all(n == (25 if sample == 'main' else 3) for (_, sample, _), n in counts.items())
    by_id = {r['answer_id']: r for r in records}
    assert len(humans) == 36 and set(humans) <= set(by_id)
    checks = []
    # Human vs each raw judge is the comparison the protocol pre-specifies (human_check.py);
    # human vs final is not independent where the author also adjudicated.
    pair = {'human_vs_final': lambda aid: (humans[aid], by_id[aid]),
            'human_vs_judge_1': lambda aid: (humans[aid], raw[aid][0]),
            'human_vs_judge_2': lambda aid: (humans[aid], raw[aid][1]),
            'judge_1_vs_judge_2': lambda aid: raw[aid]}
    for comparison in pair:
        ids = sorted(raw if comparison == 'judge_1_vs_judge_2' else humans)
        for field in (*FIELDS, 'status_question_outcome'):
            a, b = [], []
            for aid in ids:
                left, right = pair[comparison](aid)
                value = lambda form: classify(form, by_id[aid]['side']) if field == 'status_question_outcome' else form[field]
                a.append(value(left)); b.append(value(right))
            stats = agreement(a, b)
            checks.append(dict(comparison=comparison, field=field, **stats))
    field_checks = [r for r in checks if r['comparison'] == 'human_vs_final' and r['field'] in FIELDS]
    validated = all((r['kappa'] is not None and r['kappa'] >= .7) or (r['kappa'] is None and r['agreement'] == 1) for r in field_checks)
    tables = []
    for (model, sample, side), total in sorted(counts.items()):
        rs = [r for r in records if (r['model_name'], r['sample'], r['side']) == (model, sample, side)]
        usable = [r for r in rs if r['status_question_outcome'] is not None]
        for outcome in ('correct', 'incorrect', 'uncertain'):
            n = sum(r['status_question_outcome'] == outcome for r in usable)
            low, high = wilson(n, len(usable))
            tables.append(dict(model=model, sample=sample, side=side, outcome=outcome, count=n,
                denominator=len(usable), total_runs=total, operational_missing=total-len(usable),
                proportion=n/len(usable) if usable else None, ci_low=low, ci_high=high,
                validated_by_pooled_human_check=validated))
    # Same as analysis.status_tables: pairs where both the retracted paper and its control are answered correctly.
    both = []
    for (model, sample) in sorted({(r['model_name'], r['sample']) for r in records}):
        side = {s: {r['pair_id']: r for r in records if (r['model_name'], r['sample'], r['side']) == (model, sample, s)} for s in 'RK'}
        eligible = [p for p in set(side['R']) & set(side['K'])
                    if side['R'][p]['status_question_outcome'] is not None and side['K'][p]['status_question_outcome'] is not None]
        yes = sum(side['R'][p]['status_question_outcome'] == side['K'][p]['status_question_outcome'] == 'correct' for p in eligible)
        low, high = wilson(yes, len(eligible))
        both.append(dict(model=model, sample=sample, count=yes, n=len(eligible), ci_low=low, ci_high=high,
                         omitted=len(set(side['R']) | set(side['K'])) - len(eligible)))
    out = base / 'status-only'
    out.mkdir(exist_ok=True)
    write_csv(out/'both_correct.csv', both)
    write_jsonl(out/'outcomes.jsonl', records)
    write_csv(out/'rates.csv', tables)
    write_jsonl(out/'agreement.jsonl', checks)
    write_csv(out/'agreement.csv', [{k:v for k,v in r.items() if k != 'contingency'} for r in checks])
    write_jsonl(out/'human-scored.jsonl', [dict(answer_id=aid, model_name=by_id[aid]['model_name'], sample=by_id[aid]['sample'], side=by_id[aid]['side'], status_question_outcome=classify(form, by_id[aid]['side']), **{f:form[f] for f in FIELDS}) for aid, form in sorted(humans.items())])
    summary = dict(total_runs=len(records), usable_answers=sum(r['usable'] for r in records), author_decisions=len(used),
        human_forms=len(humans), validated_by_pooled_human_check=validated, unresolved_ancillary_field_disagreements=dict(ancillary),
        scope='SQ only; no ancillary or forged-notice outcomes', rationale_collected=False,
        denominator='Non-refusal usable answers, with operational missing reported separately; main and pilot separated.',
        input_sha256={str(p.relative_to(ROOT)):sha_file(p) for p in sorted(set(inputs))})
    (out/'manifest.json').write_text(json.dumps(summary, indent=2)+'\n')
    def agr(comparison, field='asserted_status'):
        r = next(c for c in checks if c['comparison'] == comparison and c['field'] == field)
        k = 'undefined' if r['kappa'] is None else f"{r['kappa']:.2f}"
        return f"{round(r['agreement']*r['n'])}/{r['n']} (kappa {k})"
    def called_retracted(model, sample, side):
        rs = [r for r in records if (r['model_name'], r['sample'], r['side']) == (model, sample, side)
              and r['status_question_outcome'] is not None]
        n = sum(r['asserted_status'] == 'retracted' and not r['conflicting_assertions'] for r in rs)
        return n, len(rs)
    first, last = min(retraction_dates), max(retraction_dates)
    lines = ['# Status-question results', '',
        'Offline analysis of the nine tested API configurations. Main sample: 25 pairs; pilot: 3 separate pairs. '
        '504 terminal runs, 503 usable answers. One Qwen control answer in the main sample was cut off without usable text.', '',
        'Counts below are correct / incorrect / uncertain. Operational missing answers are excluded from these denominators '
        'and reported separately in rates.csv. “Correct” is relative to the sampled status classification; '
        'control status is bounded by the screening and registry snapshot.', '']
    for sample in ('main', 'pilot'):
        lines += [f'## {sample.title()} sample', '', '| Model | Retracted papers: C / I / U | Control papers: C / I / U |',
                  '|---|---:|---:|']
        for model in sorted({r['model_name'] for r in records}):
            cells = []
            for side in ('R', 'K'):
                cell = [r for r in tables if (r['model'], r['sample'], r['side']) == (model, sample, side)]
                cells.append(' / '.join(str(r['count']) for r in cell) + f" (n={cell[0]['denominator']})")
            lines.append(f'| {model} | {cells[0]} | {cells[1]} |')
        lines.append('')
    lines += ['## Reading the retracted-paper column', '',
        f'Every retracted paper in both samples was retracted between {first} and {last}, after every published training '
        'cutoff (the latest is June 2026). Four models publish no cutoff: Seed 2.0 Lite (released 10 Mar 2026), Qwen3.8 Flash '
        '(26 Aug 2026), DeepSeek V4.1 Flash (10 Sep 2026, updated 17 Oct) and ERNIE 5.5 Flash (11 Nov 2026); for the last three, '
        'exposure to some of these retractions cannot be ruled out. For models with a published cutoff, a “correct” answer on '
        'a retracted paper cannot reflect knowledge of the notice; for the others it is unlikely to, and a retraction year '
        'before 2026 is wrong in every case. For papers retracted after the cutoff, “uncertain” is the expected '
        'well-calibrated answer on both sides. The same holds in the other direction: a definite “not retracted” '
        'cannot reflect knowledge of the current record either, so a model that says “not retracted” to everything scores '
        'well on controls and fails every retracted paper (false reassurance). The informative comparison is how often a model '
        'calls a paper retracted when it is retracted versus when it is a control: similar rates mean no discrimination.', '',
        '| Model | Called retracted: retracted papers | Called retracted: control papers | Both correct (pairs) |',
        '|---|---:|---:|---:|']
    for model in sorted({r['model_name'] for r in records}):
        (a, n), (b, m) = called_retracted(model, 'main', 'R'), called_retracted(model, 'main', 'K')
        both_row = next(x for x in both if (x['model'], x['sample']) == (model, 'main'))
        lines.append(f'| {model} | {a}/{n} | {b}/{m} | {both_row["count"]}/{both_row["n"]} |')
    lines += ['', 'Main sample only; denominators are non-refusal usable answers. “Both correct” counts pairs where the '
              'retracted paper is called retracted and its control not retracted (both_correct.csv, with Wilson intervals).', '']
    lines += ['## Scoring and limitations', '',
        f'The author resolved {len(used)} asserted-status disagreements categorically; no written rationales were collected. '
        + (f'{len(corrections)} decision(s) were later corrected by the author for consistency, with a written reason, in '
           'status-review/author-status-corrections.csv; the original export is unchanged. ' if corrections else '') +
        'No disagreements on refusal or conflicting assertions required adjudication. '
        'The original independent 36-answer human check is preserved separately from adjudication.', '',
        f'Human agreement on asserted status against the final label, which the frozen D66 gate uses: {agr("human_vs_final")}; '
        f'against each raw judge: judge 1 {agr("human_vs_judge_1")}, judge 2 {agr("human_vs_judge_2")}. '
        f'Refusal: judge 1 {agr("human_vs_judge_1", "refusal")}, judge 2 {agr("human_vs_judge_2", "refusal")}; '
        f'conflicting assertions: judge 1 {agr("human_vs_judge_1", "conflicting_assertions")}, '
        f'judge 2 {agr("human_vs_judge_2", "conflicting_assertions")} (kappa is undefined where labels are constant). '
        'This meets the pre-existing pooled human-check rule, but does not independently verify every answer or factual claim.', '',
        f'Raw judge agreement on asserted status is {agr("judge_1_vs_judge_2")}. '
        'Uncertainty and no stated status map to the uncertain outcome under the existing scoring rule. '
        'Refusals and unusable answers are operational missing, not uncertain.', '',
        'The dedicated status-only workflow leaves 429 ancillary disagreements unresolved: source 204, '
        'claimed checks 159, notice details 66. No ancillary outcomes are reported or implicitly settled. '
        'Omission of written rationales and separation from the original full-form pipeline are disclosed workflow changes.', '',
        'Per-model, per-side Wilson 95% intervals are in rates.csv. Main and pilot are not pooled. '
        'High accuracy on retracted papers alone does not establish discrimination: a model can call controls retracted too. '
        'These results do not establish absence of training knowledge and do not evaluate simulated retrieval, tools or forged notices.', '',
        'Reproduce: `python3 -I code/status_only.py`. Input hashes are recorded in manifest.json. '
        'No paid calls or external retrieval are needed.', '']
    (out/'RESULTS.md').write_text('\n'.join(lines))
    print(json.dumps({k:v for k,v in summary.items() if k != 'input_sha256'}, indent=2))
    for r in checks:
        print({k:v for k,v in r.items() if k != 'contingency'})


if __name__ == '__main__':
    main()
