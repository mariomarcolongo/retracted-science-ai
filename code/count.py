# Count the eligible pool per start date and export candidates as CSV.
# Usage: python3 -I code/count.py data/work/pool_jan_full.json data/work/candidates.csv
# Counts are exploratory, not the final draw. One paper per journal is a seeded random choice.
import csv, json, random, sys, collections

pool = json.load(open(sys.argv[1]))
LAB = {'Molecular Biology', 'Cell Biology', 'Biochemistry', 'Cancer Research', 'Genetics', 'Biomaterials',
       'Materials Chemistry', 'Plant Science', 'Biotechnology', 'Immunology', 'Pharmacology', 'Small Animals',
       'Physiology', 'Endocrinology', 'Biophysics', 'Structural Biology', 'Microbiology', 'Molecular Medicine',
       'Organic Chemistry', 'Drug Discovery', 'Catalysis', 'Polymers and Plastics', 'Food Science'}

def abstract_source(p):
    if p['oa'] and p['oa']['has_abstract'] and p['oa']['lang'] in (None, 'en'):
        return 'openalex'
    if p.get('pubmed_abstract') and p.get('pubmed_lang') in (None, 'eng'):
        return 'pubmed'
    return ''

print('start      | rules | abstract (of which PubMed) | >=5 cites | 1/journal | 2/journal | 1/journal: clinical vs lab')
for start in ['2026-04-01', '2026-06-01', '2026-07-01', '2026-08-01']:
    s = [p for p in pool if p['rdate'] >= start]; n0 = len(s)
    s = [p for p in s if abstract_source(p)]; n1 = len(s); pm = sum(abstract_source(p) == 'pubmed' for p in s)
    s = [p for p in s if p['oa'] and p['oa']['cites'] >= 5]; n2 = len(s)
    byj = collections.defaultdict(list)
    for p in s: byj[p['journal']].append(p)
    rng = random.Random(20261114)
    one = [rng.choice(sorted(v, key=lambda p: p['id'])) for v in sorted(byj.values(), key=lambda v: v[0]['journal'])]
    two = sum(min(2, len(v)) for v in byj.values())
    lab = sum(1 for p in one if p['oa']['subfield'] in LAB)
    print(f"{start} | {n0:5d} | {n1:8d} ({pm:3d})           | {n2:10d} | {len(one):9d} | {two:9d} | {len(one)-lab} clinical/other, {lab} lab")

with open(sys.argv[2], 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['rw_record_id', 'doi', 'pmid', 'title', 'journal', 'publisher', 'country', 'retraction_date',
                'original_date', 'openalex_citations', 'openalex_subfield', 'abstract_source', 'reasons'])
    for p in sorted(pool, key=lambda p: p['rdate']):
        w.writerow([p['id'], p['doi'], p.get('pmid') or '', p['title'], p['journal'], p['publisher'], p['country'],
                    p['rdate'], p['odate'], (p['oa'] or {}).get('cites', ''), (p['oa'] or {}).get('subfield', ''),
                    abstract_source(p), p['reasons']])
print('wrote', sys.argv[2], len(pool), 'rows')
