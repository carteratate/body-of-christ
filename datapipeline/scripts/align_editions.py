"""Align two editions of a document paragraph by paragraph (corpus-cleanup 1.3c, 1.3d).

    cd datapipeline
    python3 scripts/align_editions.py --snapshot releases/snapshots/<date>
                                      --collection encyclicals [--slug <slug> ...]
                                      [--out <file.md>]

A document whose translation is replaced keeps a unit's anchor and ID only where the new
edition's unit is the same paragraph (D1). Two translations share few word sequences, so
the release report's text similarity cannot judge that. This compares what translations
keep: the rarer words of each paragraph (names, Latin, technical terms), its numbers and
citations, and its length, and finds the best order-keeping pairing of the live units
with the built ones, letting one paragraph pair with two (a paragraph one edition splits).

Each live unit then has one of these results:
  `match`     paired with the built unit of the same anchor;
  `mismatch`  paired, but with a built unit of another anchor, or with two;
  `unpaired`  no built unit holds it.
Both editions are built by their own printed numbering, without the document's entry in
`ingest/papal_anchors.json`: which live anchor a built unit carries is what the reviewed
alignment decides. The report lists every unit that is not a plain match, with both
editions' opening words, for a person to review. It reads the live snapshot (gitignored), so it holds passage text
only in the local file it writes; the PR quotes only the anchors and scores.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from typing import NamedTuple

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

_WORD = re.compile(r"[A-Za-zÀ-ÿ]+|\d+")
# Words every translation of a papal text repeats; they carry no paragraph's identity.
_STOP = frozenset("""
the and of to in a that is which it be for this as with by not are his he we our or on
from but all they their its was have has who were them so also an at those these such
one may can will would should must more no there what when been being than into any only
other even then him upon itself because own same very most same through while whom do
us church god christ man men holy faith life lord things thing great order every same
""".split())
_STEM = 6
# A paragraph this much longer than its partner is unlikely to be the same one.
_LENGTH_WEIGHT = 0.35
# What leaving a unit unpaired costs, against a pair's score in 0..1.
_SKIP = 0.15
# One unit may pair with up to this many of the other edition's.
_MOST = 4
_MOVES = [(1, 1), (1, 0), (0, 1)] + [m for k in range(2, _MOST + 1) for m in ((k, 1), (1, k))]
# A pair scoring under this is no evidence of identity.
MIN_SCORE = 0.08


class Unit(NamedTuple):
    anchor: str
    text: str


class Pair(NamedTuple):
    old: tuple[str, ...]     # live unit anchors (one, or two merged)
    new: tuple[str, ...]     # built unit anchors (one, or two split)
    score: float


def _terms(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text):
        if w.isdigit():
            out.append("#" + w)
            continue
        lw = w.lower()
        if len(lw) < 4 or lw in _STOP:
            continue
        out.append(lw[:_STEM])
    return out


def _vectors(units: list[Unit], df: Counter, n_docs: int) -> list[dict[str, float]]:
    vectors = []
    for u in units:
        tf = Counter(_terms(u.text))
        v = {t: (1 + math.log(c)) * math.log((n_docs + 1) / (df[t] + 0.5)) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vectors.append({t: x / norm for t, x in v.items()})
    return vectors


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _merged(vectors: list[dict[str, float]]) -> dict[str, float]:
    if len(vectors) == 1:
        return vectors[0]
    m: dict[str, float] = {}
    for v in vectors:
        for t, x in v.items():
            m[t] = m.get(t, 0.0) + x
    norm = math.sqrt(sum(x * x for x in m.values())) or 1.0
    return {t: x / norm for t, x in m.items()}


def _length_penalty(a: int, b: int) -> float:
    if not a or not b:
        return 1.0
    return min(1.0, abs(math.log(a / b)) * _LENGTH_WEIGHT)


def align(old: list[Unit], new: list[Unit]) -> list[Pair]:
    """The order-keeping pairing of `old` with `new` of greatest total score, allowing a
    unit to pair with one, with up to `_MOST` of the other edition's, or with none."""
    df: Counter = Counter()
    for u in old + new:
        df.update(set(_terms(u.text)))
    n_docs = len(old) + len(new)
    vo, vn = _vectors(old, df, n_docs), _vectors(new, df, n_docs)
    lo, ln = [len(u.text) for u in old], [len(u.text) for u in new]

    def score(i0: int, i1: int, j0: int, j1: int) -> float:
        a = _merged(vo[i0:i1])
        b = _merged(vn[j0:j1])
        # Each unit of a merge must share words with the other side, or it is no part of
        # the pair (a heading, a unit the other edition lacks).
        if any(_cos(v, b) < MIN_SCORE for v in vo[i0:i1]) \
                or any(_cos(a, v) < MIN_SCORE for v in vn[j0:j1]):
            if i1 - i0 > 1 or j1 - j0 > 1:
                return -math.inf
        s = _cos(a, b) - _length_penalty(sum(lo[i0:i1]), sum(ln[j0:j1])) * 0.5
        # Pairing several with one must beat the plain pair by a margin.
        return s - 0.05 * ((i1 - i0) + (j1 - j0) - 2)

    n, m = len(old), len(new)
    best = [[-math.inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            here = best[i][j]
            if here == -math.inf:
                continue
            for di, dj in _MOVES:
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                gain = -_SKIP if di == 0 or dj == 0 else score(i, ii, j, jj)
                if here + gain > best[ii][jj]:
                    best[ii][jj] = here + gain
                    back[ii][jj] = (di, dj)
    pairs: list[Pair] = []
    i, j = n, m
    while i or j:
        di, dj = back[i][j]
        i0, j0 = i - di, j - dj
        s = 0.0 if di == 0 or dj == 0 else score(i0, i, j0, j)
        pairs.append(Pair(tuple(u.anchor for u in old[i0:i]),
                          tuple(u.anchor for u in new[j0:j]), round(s, 3)))
        i, j = i0, j0
    return pairs[::-1]


def outcomes(pairs: list[Pair]) -> list[dict]:
    """One row per pair that is not a plain match of one anchor with itself."""
    rows = []
    for p in pairs:
        if len(p.old) == 1 and p.new == p.old and p.score >= MIN_SCORE:
            continue
        kind = ("unpaired" if not p.new else "new-only" if not p.old
                else "weak" if p.new == p.old else "mismatch")
        rows.append({"old": list(p.old), "new": list(p.new), "score": p.score, "kind": kind})
    return rows


def units_of(passages, anchor_of, text_of) -> list[Unit]:
    from identity import unit_anchor

    out: dict[str, list[str]] = {}
    for p in passages:
        out.setdefault(unit_anchor(anchor_of(p)), []).append(text_of(p))
    return [Unit(a, " ".join(t)) for a, t in out.items()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", required=True, help="a papal collection")
    ap.add_argument("--old-file", default="{slug}.html",
                    help="the old edition's file in the collection's sources, by slug")
    ap.add_argument("--slug", action="append",
                    help="limit to these slugs (default: every manifest entry whose file "
                         "is not the old edition's)")
    ap.add_argument("--out", help="write the review list, with opening words, here")
    args = ap.parse_args(argv)

    from checks.report import placeholder_credentials

    placeholder_credentials()
    from ingest import papal_common

    src = os.path.join(DATAPIPELINE, "sources", args.collection)
    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as f:
        manifest = {e["slug"]: e for e in json.load(f)}
    slugs = args.slug or [s for s, e in manifest.items()
                          if e["file"] != args.old_file.format(slug=s)
                          and os.path.exists(os.path.join(src, args.old_file.format(slug=s)))]
    lines = ["# Paragraph alignment", ""]
    total = 0
    for slug in slugs:
        entry = manifest[slug]
        # Each edition by its own numbering: the anchors a unit takes over from the live
        # text (papal_anchors.json) are what this alignment decides, not an input to it.
        overrides = papal_common._UNIT_ANCHORS.pop(slug, None)
        try:
            before = papal_common.build_document(
                dict(entry, file=args.old_file.format(slug=slug)), args.collection, src)
            after = papal_common.build_document(entry, args.collection, src)
        finally:
            if overrides is not None:
                papal_common._UNIT_ANCHORS[slug] = overrides
        old = units_of(before.passages, lambda p: p.anchor, lambda p: p.content)
        new = units_of(after.passages, lambda p: p.anchor, lambda p: p.content)
        rows = outcomes(align(old, new))
        total += len(rows)
        print(f"{slug}: {len(old)} old units, {len(new)} new, {len(rows)} to review")
        olds, news = {u.anchor: u.text for u in old}, {u.anchor: u.text for u in new}
        lines += [f"## {slug}", ""]
        for r in rows:
            print(f"  {r['kind']:9} {' + '.join(r['old']) or '-':40} -> "
                  f"{' + '.join(r['new']) or '-':40} {r['score']:.2f}")
            lines.append(f"- {r['kind']}: {' + '.join(r['old']) or '-'} -> "
                         f"{' + '.join(r['new']) or '-'} (score {r['score']:.2f})")
            for a in r["old"]:
                lines.append(f"  - old `{a}`: {olds[a][:200]!r}")
            for a in r["new"]:
                lines.append(f"  - new `{a}`: {news[a][:200]!r}")
        lines.append("")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print(f"{total} rows to review")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
