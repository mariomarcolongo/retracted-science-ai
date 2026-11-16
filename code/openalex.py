"""Enrich pool records with OpenAlex metadata (paper Appendix F, Table F1).

Usage: python3 -I code/openalex.py POOL.json OUTPUT.json
Stop without writing output if any batch cannot be retrieved after three attempts.
"""
import json, sys, time, urllib.request, urllib.parse
pool=json.load(open(sys.argv[1])); out=sys.argv[2]
dois=[p['doi'] for p in pool]
res={}
for i in range(0,len(dois),40):
    chunk=dois[i:i+40]
    q=urllib.parse.urlencode({'filter':'doi:'+'|'.join(chunk),'per-page':'50',
        'select':'doi,display_name,cited_by_count,language,type,primary_topic,abstract_inverted_index,authorships,publication_year,is_retracted'})
    req=urllib.request.Request('https://api.openalex.org/works?'+q,headers={'User-Agent':'research-script'})
    for attempt in range(3):
        try:
            data=json.load(urllib.request.urlopen(req,timeout=60)); break
        except Exception as e:
            print('retry',e); time.sleep(3)
    else:
        raise SystemExit('OpenAlex batch failed after three attempts; no output written')
    for w in data['results']:
        d=(w.get('doi') or '').replace('https://doi.org/','').lower()
        pt=w.get('primary_topic') or {}
        res[d]={'cites':w['cited_by_count'],'lang':w.get('language'),'oa_type':w.get('type'),
                'has_abstract':bool(w.get('abstract_inverted_index')),'is_retracted':w.get('is_retracted'),
                'topic':pt.get('display_name'),'field':(pt.get('field') or {}).get('display_name'),
                'subfield':(pt.get('subfield') or {}).get('display_name'),
                'first_author':(w['authorships'][0]['author']['display_name'] if w.get('authorships') else None)}
    time.sleep(0.3)
for p in pool: p['oa']=res.get(p['doi'])
json.dump(pool,open(out,'w'),indent=1)
print('matched',sum(1 for p in pool if p['oa']),'of',len(pool))
