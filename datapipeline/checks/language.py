"""A Latin-text heuristic for passages that should be English (rule E; 1.5b, 3.3).

A Latin run is five or more consecutive words with no English function word among them,
at least two of which are Latin function words. English prose rarely goes five words
without "the", "of", "and" or the like; Latin prose has its own function words ("qui",
"ad", "vel") every few words. A short Latin term inside English ("sui iuris", "motu
proprio") is never five words long; a longer one is listed in `APPROVED_PHRASES`.
"""
from __future__ import annotations

import re

MIN_RUN = 5

_ENGLISH = frozenset("""
a about above after against all also although am an and any are as at be because been
before being below between both but by can could did do does each either for from had
has have he her here him his how i if in into is it its may me might more most must my
no nor not of on once only or other our out over own same shall she should so some such
than that the their them then there these they this those though through to too under
unless until up upon very was we were what when where whether which while who whom whose
why will with within without would you your
""".split())

_LATIN = frozenset("""
ab ac ad aliam alii alius alterius alteruter atque aut autem cum de debent debet dum ea
eam eaeque eandem eius eiusdem eiusque enim eo eorum eos esse est et etiam ex firma hac
haec hic hoc huius iam idem iidem ipse ipsa ipsius ita item itemque nec necnon neque nisi
non possunt potest pro quae quam quamvis quidem quilibet quisque quo quod quodsi quoque
qui quibus quorum salvo sed secundum seu si sint sit sive sua suae sub sunt suis suo suum
tamen tantum ubi ut vel vero
""".split())

# Latin terms of art printed inside English text, which are English text (3.3).
APPROVED_PHRASES = ("ratum et non consummatum",)

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")


def latin_runs(text: str, min_run: int = MIN_RUN) -> list[str]:
    """Every Latin run in `text`, as its words joined by spaces."""
    runs: list[str] = []
    current: list[str] = []

    def close() -> None:
        if len(current) >= min_run and sum(w in _LATIN for w in current) >= 2:
            runs.append(" ".join(current))
        current.clear()

    for phrase in APPROVED_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    for word in (w.lower() for w in _WORD.findall(text)):
        if word in _ENGLISH:
            close()
        else:
            current.append(word)
    close()
    return runs
