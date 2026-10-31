"""Does a text contain another translation of a site document?
usage: xlate.py <slug> <ia_id|file> [...more]
Content words (stopwords and very common words removed, crude stemming) of the site text
vs. every window of the candidate of the same length. Reports the best window's share of
the site's distinct content words, and of its content-word pairs within a 6-word span,
plus where the window starts (word offset, and the page if a [page N] marker exists)."""
import re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare import get_text, site_paras, norm
STOP = set("""a about above after again against all also although am among an and any are as at be because been
before being below between both but by can could did do does doing down during each either even ever every few for
from further had has have having he her here hers him his how however i if in into is it its itself just let may me
might more most much must my nay neither no nor not now o of off on once only or other ought our ours ourselves out
over own same say said shall she should since so some such than that the their theirs them themselves then there
these they this those though thus thy thee thou to too under until unto up upon us very was we were what when where
whereas whereby wherefore whether which while who whom whose why will with within without would ye yet you your
hath doth unto yea one two three things thing made make great also many well every day year venerable brethren
brother brothers given rome peter pope holy apostolic benediction""".split())
def stem(w):
    for suf in ("ings", "ing", "ies", "ied", "es", "ed", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf): return w[: -len(suf)]
    return w
def content(words): return [stem(w) for w in words if w not in STOP and len(w) > 2]
def pairs(cw, span=6):
    return {(cw[i], cw[j]) for i in range(len(cw)) for j in range(i + 1, min(len(cw), i + span))}
def score(slug, src):
    site = content(norm(" ".join(t for _, t in site_paras(slug))))
    cand = content(norm(get_text(src)))
    vocab = set(site); sp = pairs(site)
    n = len(site); best = (0, 0, 0)
    if not cand: return best
    step = max(50, n // 8)
    for st in range(0, max(1, len(cand) - n // 2), step):
        win = cand[st: st + int(n * 1.3)]
        vw = len(vocab & set(win)) / len(vocab)
        if vw > best[0] - 0.15:
            pw = len(sp & pairs(win)) / len(sp)
            if pw > best[1]: best = (vw, pw, st)
    return best
if __name__ == "__main__":
    slug = sys.argv[1]
    for src in sys.argv[2:]:
        try:
            vw, pw, st = score(slug, src)
            print(f"{slug:28} {src:45} words={vw:5.1%} pairs={pw:5.1%} at={st}")
        except Exception as e:
            print(f"{slug:28} {src:45} ERR {e}")
