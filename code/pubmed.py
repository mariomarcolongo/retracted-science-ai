# Fill missing abstracts from PubMed (NCBI E-utilities). No email or personal data is sent.
import csv, json, sys, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
csvf, poolf, outf = sys.argv[1:4]
pool = json.load(open(poolf))
pmid_by_id = {r['Record ID']: r['OriginalPaperPubMedID'].strip() for r in csv.DictReader(open(csvf, encoding='utf-8', errors='replace'))}
BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
def get(url):
    for a in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'research-script'}), timeout=60).read()
        except Exception as e:
            print('retry', e); time.sleep(2 + 2 * a)
    raise SystemExit('failed: ' + url)
need = [p for p in pool if not (p['oa'] and p['oa']['has_abstract'])]
print('missing abstract in OpenAlex:', len(need))
found_by_doi = 0
for p in need:
    pm = pmid_by_id.get(p['id'], '')
    if not pm or pm == '0':
        q = urllib.parse.urlencode({'db': 'pubmed', 'term': p['doi'] + '[doi]', 'retmode': 'json', 'tool': 'research-script'})
        ids = json.loads(get(BASE + 'esearch.fcgi?' + q))['esearchresult']['idlist']
        pm = ids[0] if len(ids) == 1 else ''
        found_by_doi += bool(pm)
        time.sleep(0.4)
    p['pmid'] = pm or None
with_pmid = [p for p in need if p.get('pmid')]
print('PMID from Retraction Watch:', len(with_pmid) - found_by_doi, '| found by DOI search:', found_by_doi, '| no PMID:', len(need) - len(with_pmid))
got = 0
for i in range(0, len(with_pmid), 100):
    chunk = with_pmid[i:i + 100]
    q = urllib.parse.urlencode({'db': 'pubmed', 'id': ','.join(p['pmid'] for p in chunk), 'retmode': 'xml', 'tool': 'research-script'})
    root = ET.fromstring(get(BASE + 'efetch.fcgi?' + q))
    by = {}
    for art in root.iter('PubmedArticle'):
        pid = art.findtext('.//PMID')
        parts = [''.join(t.itertext()).strip() for t in art.iter('AbstractText')]
        lang = art.findtext('.//Language')
        by[pid] = (' '.join(x for x in parts if x), lang)
    for p in chunk:
        ab, lang = by.get(p['pmid'], ('', None))
        p['pubmed_abstract'] = ab or None
        p['pubmed_lang'] = lang
        got += bool(ab)
    time.sleep(0.4)
print('abstracts recovered from PubMed:', got)
json.dump(pool, open(outf, 'w'), indent=1)
