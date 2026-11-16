import csv, sys, json, collections, datetime as dt
src, start = sys.argv[1], dt.date.fromisoformat(sys.argv[2])
DATA = {"Falsification/Fabrication of Data","Falsification/Fabrication of Image","Falsification/Fabrication of Results",
 "Error in Data","Error in Analyses","Error in Results and/or Conclusions","Results Not Reproducible","Manipulation of Images",
 "Paper Mill","Unreliable Data","Unreliable Results and/or Conclusions","Contamination of Cell Lines/Tissues",
 "Duplication of/in Image","Concerns/Issues about Data","Concerns/Issues about Results and/or Conclusions",
 "Concerns/Issues about Image","Unreliable Image","Error in Image"}
TYPES = {"Research Article","Clinical Study"}
def d(s):
    try: return dt.datetime.strptime(s.split()[0],'%m/%d/%Y').date()
    except: return None
rows=list(csv.DictReader(open(src,encoding='utf-8',errors='replace')))
steps=[]; cur=rows
def keep(name,f):
    global cur
    cur=[r for r in cur if f(r)]; steps.append((name,len(cur)))
keep('all records',lambda r:True)
keep('full retraction',lambda r:r['RetractionNature']=='Retraction')
keep(f'retracted on/after {start}',lambda r:(d(r['RetractionDate']) or dt.date.min)>=start)
keep('published >= 1 year before',lambda r:d(r['OriginalPaperDate']) and (d(r['RetractionDate'])-d(r['OriginalPaperDate'])).days>=365)
keep('research article / clinical study',lambda r:any(t.strip() in TYPES for t in r['ArticleType'].split(';')))
keep('health subject (HSC)',lambda r:'(HSC)' in r['Subject'])
keep('data-invalidating reason',lambda r:any(x.strip().lstrip('+') in DATA for x in r['Reason'].split(';')))
keep('has original DOI',lambda r:r['OriginalPaperDOI'].strip() not in ('','unavailable','Unavailable'))
for n,c in steps: print(f'{c:7d}  {n}')
out=[{'id':r['Record ID'],'doi':r['OriginalPaperDOI'].strip().lower(),'title':r['Title'],'journal':r['Journal'],
      'publisher':r['Publisher'],'country':r['Country'],'authors':r['Author'],'rdate':str(d(r['RetractionDate'])),
      'odate':str(d(r['OriginalPaperDate'])),'reasons':r['Reason'],'subject':r['Subject'],'type':r['ArticleType']} for r in cur]
json.dump(out,open(sys.argv[3],'w'),indent=1)
print('journals:',len({o['journal'] for o in out}),'| top publishers:',collections.Counter(o['publisher'] for o in out).most_common(5))
print('top journals:',collections.Counter(o['journal'] for o in out).most_common(6))
print('countries:',collections.Counter(o['country'].split(';')[0] for o in out).most_common(6))
