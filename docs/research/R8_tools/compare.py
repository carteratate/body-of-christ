"""Compare a site text with a printing's OCR text by word 4-gram shingles.
usage: compare.py <slug> <ia_identifier | path.txt> [--para]
Fetches <id>_djvu.txt (or uses a local file) into dl/, reports what share of the site's
shingles occur in the printing, overall and per site paragraph."""
import os, re, sys, json, urllib.request, urllib.parse, unicodedata
HERE = os.path.dirname(os.path.abspath(__file__))
def norm(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"-\s*\n\s*", "", t)          # rejoin hyphenated line breaks
    return re.findall(r"[a-z]+", t)
def shingles(w, k=4): return {" ".join(w[i:i+k]) for i in range(len(w) - k + 1)}
def get_text(src):
    if os.path.exists(src): return open(src, errors="ignore").read()
    p = os.path.join(HERE, "dl", src.replace("/", "__") + ".txt")
    if not os.path.exists(p):
        ident, _, fname = src.partition("/")
        if not fname:
            meta = json.load(urllib.request.urlopen(f"https://archive.org/metadata/{ident}", timeout=60))
            fs = [f["name"] for f in meta.get("files", []) if f["name"].endswith("_djvu.txt")]
            if not fs: raise SystemExit(f"no djvu.txt in {ident}: " + ", ".join(f['name'] for f in meta.get('files', [])[:30]))
            fname = fs[0]
        url = f"https://archive.org/download/{ident}/{urllib.parse.quote(fname)}"
        open(p, "wb").write(urllib.request.urlopen(url, timeout=120).read())
    return open(p, errors="ignore").read()
def site_paras(slug):
    raw = open(os.path.join(HERE, "texts", slug + ".txt")).read()
    out = []
    for blk in raw.split("\n\n"):
        m = re.match(r"\[([^\]]*)\]\s*(.*)", blk, re.S)
        if m: out.append((m.group(1), m.group(2)))
    return out
if __name__ == "__main__":
    slug, src = sys.argv[1], sys.argv[2]
    pr = shingles(norm(get_text(src)))
    paras = site_paras(slug)
    tot = hit = 0; rows = []
    for lab, txt in paras:
        s = shingles(norm(txt)); h = len(s & pr)
        tot += len(s); hit += h
        rows.append((lab, len(s), h / len(s) if s else 1.0))
    print(f"{slug} vs {src}: {hit}/{tot} shingles = {hit/tot:.1%}; paragraphs >=60%: {sum(r[2]>=.6 for r in rows)}/{len(rows)}")
    if "--para" in sys.argv:
        for lab, n, f in rows: print(f"  {lab:>12} {n:5d} {f:6.1%}")
    else:
        low = [r for r in rows if r[2] < .6]
        if low: print("  below 60%:", ", ".join(f"{l}={f:.0%}" for l, n, f in low[:40]))
