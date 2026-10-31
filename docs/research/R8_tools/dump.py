"""Write each older papal document's site text to <out>/<slug>.txt and a docs.json beside <out>.
usage (from datapipeline/): .venv/bin/python ../docs/research/R8_tools/dump.py <out>"""
import json, sys, os
sys.path.insert(0, '.')
from ingest import encyclicals, papal_documents
out = sys.argv[1]
rows = []
for mod, coll in ((encyclicals, 'encyclicals'), (papal_documents, 'papal-documents')):
    man = json.load(open(os.path.join(mod._SRC, 'manifest.json')))
    for e in man:
        if coll == 'encyclicals' and e['year'] >= 1878: continue
        if coll == 'papal-documents' and e['slug'] not in ('exsurge-domine','sublimis-deus','unam-sanctam'): continue
        d = mod.build_document(e)
        txt = "\n\n".join(f"[{p.unit_label or p.reference}] {p.content}" for p in d.passages)
        open(os.path.join(out, e['slug']+'.txt'),'w').write(txt)
        rows.append(dict(slug=e['slug'], title=d.title, author=e['author'], year=e['year'], url=e['url'], words=len(txt.split()), passages=len(d.passages)))
json.dump(rows, open(os.path.join(out,'..','docs.json'),'w'), indent=1)
print(len(rows), sum(r['words'] for r in rows), sum(r['passages'] for r in rows))
for r in sorted(rows, key=lambda r: r['year']): print(r['year'], r['author'], '|', r['title'], r['words'])
