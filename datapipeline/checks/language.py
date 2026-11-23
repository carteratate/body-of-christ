"""Non-English text in passages that should be English (rule E; 1.5b, 3.3).

A foreign run is five or more consecutive words with no English function word among
them, at least two of which are function words of one other language. English prose
rarely goes five words without "the", "of", "and" or the like; Latin, Italian and French
prose have their own function words ("qui", "ad", "vel"; "che", "della"; "dans", "nous")
every few words. A short term inside English ("sui iuris", "motu proprio") is never five
words long; a longer one is listed in `APPROVED_PHRASES`.

Latin words that also stand alone in a cited title ("De Nup. et Concup.", "Ad Fratres de
Monte Dei") never make a run Latin by themselves, so the Summa's and the Fathers'
citations stay English (3.3). A Latin, Italian or French quotation inside an English
passage that Carter approved is listed, by passage and the sha1 of its words, in
`language_approved.json` (3.3, 14 Nov 2026); `english_only` fails every other run.

Greek and Hebrew script are not checked: in the corpus they are single words and short
glosses printed inside English text, which is English text (3.3).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

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

# Latin function words that also stand alone in a cited title; they do not count (3.3).
_TITLE_WORDS = frozenset("de et ad pro ex".split())

# Not "per", "se" or "lo": Latin's "per se" and English's "lo" would read as Italian.
_ITALIAN = frozenset("""
al alla alle ci che col con da dal dalla degli dei del della delle di e ed gli ha hanno
il io la le loro ma mi nel nella nelle non noi più questa questo si sono sua suo sue
suoi tra una uno è
""".split())

_FRENCH = frozenset("""
au aux avec ce ces cette dans des du elle est la le les leur leurs mais ne nous par pas
pour que qui rien se sont sur un une vous à
""".split())

# Function words by ISO 639 code; a run is the language with the most of them (Latin on a
# tie, since the corpus's foreign text is mostly Latin).
_FUNCTION_WORDS = {"la": _LATIN - _TITLE_WORDS, "it": _ITALIAN, "fr": _FRENCH}

# Latin terms of art printed inside English text, which are English text (1.5b, 3.3).
APPROVED_PHRASES = ("ratum et non consummatum",)

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")

_DIR = os.path.dirname(os.path.abspath(__file__))
APPROVED_PATH = os.path.join(_DIR, "language_approved.json")


def foreign_runs(text: str, min_run: int = MIN_RUN) -> list[tuple[str, str]]:
    """Every foreign run in `text`, as (language, its words joined by spaces)."""
    runs: list[tuple[str, str]] = []
    current: list[str] = []

    def close() -> None:
        if len(current) >= min_run:
            counts = {lang: sum(w in words for w in current)
                      for lang, words in _FUNCTION_WORDS.items()}
            lang = max(counts, key=lambda k: counts[k])   # dicts keep order: Latin first
            if counts[lang] >= 2:
                runs.append((lang, " ".join(current)))
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


def mostly_foreign(text: str) -> bool:
    """Whether `text` is a paragraph a translator left untranslated, not a quotation
    inside English (3.3): foreign runs hold at least half its words, or, for a line too
    short to make a run (a verse, "Et rursus:—"), it has another language's function
    words and no English one."""
    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return False
    if not any(w in _ENGLISH for w in words) and any(
            w in _LATIN or w in _ITALIAN or w in _FRENCH for w in words):
        return True
    return 2 * sum(len(r.split()) for _, r in foreign_runs(text)) >= len(words)


def latin_runs(text: str, min_run: int = MIN_RUN) -> list[str]:
    """Every Latin run in `text`, as its words joined by spaces."""
    return [run for lang, run in foreign_runs(text, min_run) if lang == "la"]


def run_sha1(run: str) -> str:
    return hashlib.sha1(run.encode("utf-8")).hexdigest()


def load_approved(path: str = APPROVED_PATH) -> set[tuple[str, str, str]]:
    """The approved quotations, as (document ID, anchor, sha1 of the run's words)."""
    with open(path, encoding="utf-8") as f:
        return {(e["document_id"], e["anchor"], e["sha1"]) for e in json.load(f)}


def _staged(documents, registry=None):
    """The documents and passages a stage writes: without what the removal registry
    retires (D4). The release report builds through the raw adapters."""
    import registry as reg
    removed = reg.removed_document_ids(registry)
    return [reg.drop_removed(d, registry) for d in documents if d.id not in removed]


def runs_by_passage(documents, registry=None):
    """(document, passage, language, run) for every foreign run in a staged passage."""
    for d in _staged(documents, registry):
        for p in d.passages:
            for lang, run in foreign_runs(p.content):
                yield d, p, lang, run


def english_only(documents, registry=None, approved: set | None = None):
    """`language.english_only` (3.3): (document, passage, detail) for each staged passage
    whose `language` is not English, or that holds a foreign run not approved."""
    approved = load_approved() if approved is None else approved
    out = []
    for d in _staged(documents, registry):
        for p in d.passages:
            if p.language not in (None, "en"):
                out.append((d, p, f"language is {p.language}"))
    for d, p, lang, run in runs_by_passage(documents, registry):
        if (d.id, p.anchor, run_sha1(run)) not in approved:
            out.append((d, p, f"{lang} run of {len(run.split())} words: "
                              f"{' '.join(run.split()[:6])}"))
    return out


def approved_entries(documents, registry=None) -> list[dict]:
    """Every foreign run in the staged build, as `language_approved.json` entries, for
    `--write-approved`. Writing the file approves them: run it only on a list Carter has
    approved, and review the diff."""
    rows = {(d.id, p.anchor, run_sha1(run)): {
        "document_id": d.id, "anchor": p.anchor, "collection": d.collection,
        "title": d.title, "language": lang, "words": len(run.split()),
        "starts": " ".join(run.split()[:6]), "sha1": run_sha1(run)}
        for d, p, lang, run in runs_by_passage(documents, registry)}
    return [rows[k] for k in sorted(rows)]


def main(argv: list[str] | None = None) -> int:
    import argparse
    sys.path.insert(0, os.path.dirname(_DIR))
    from publication import SOURCE_BUILDS
    ap = argparse.ArgumentParser(description="Rule E's foreign-run check over a build (3.3)")
    ap.add_argument("--collection", action="append", choices=sorted(SOURCE_BUILDS))
    ap.add_argument("--write-approved", action="store_true",
                    help="approve every run found (rewrites language_approved.json)")
    args = ap.parse_args(argv)
    collections = args.collection or sorted(SOURCE_BUILDS)
    documents = [d for c in collections for d in SOURCE_BUILDS[c]()]
    if args.write_approved:
        if args.collection:
            ap.error("--write-approved needs every collection")
        with open(APPROVED_PATH, "w", encoding="utf-8") as f:
            json.dump(approved_entries(documents), f, ensure_ascii=False, indent=1)
            f.write("\n")
        return 0
    failures = english_only(documents)
    for d, p, detail in failures:
        print(f"{d.collection}/{d.id}#{p.anchor}: {detail}")
    print(f"{len(failures)} failing passages")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
