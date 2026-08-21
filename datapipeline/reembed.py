"""Classify store drift, and decide whose VECTOR is actually wrong.

The payload reconcile fixes text. It cannot fix a vector — `set_payload` writes
payload only — so a point whose stored vector was built from different text than its
Postgres row stays wrong after any sync. Those need re-embedding.

The whole difficulty is that "the stores disagree" is far too broad a trigger.
Measured against the live corpus (2026-08-21), with the cosine between each stored
vector and one rebuilt from today's Postgres row — a control group of `in_sync` points
reproduces at a median of 1.0000 with 1,928 of 1,930 sampled at >= 0.998
(two long councils passages sit near 0.92), so the method is sound:

    category            count   where            reproduction cosine (median)
    marker_prefix      26,581   summa            0.940-0.998  (0.977)
    label_drift           235   enc/a-e/papal    0.857-0.999  (0.988)
    minor_text             29   councils/summa   0.869-0.993  (0.943)
    content_unrelated      86   a-e 78/summa 8   0.388-0.904  (0.587)
    blank_source           21   summa            unrepairable, see below

`content_unrelated`'s median 0.587 is the signature of a vector built from a different
passage — no other category comes near it.

But the selection is NOT a similarity threshold, and it would be dishonest to describe
it as one. Two things make similarity useless as the rule here:

  - Medians hide the shape. `label_drift`'s 0.988 is bimodal: 137 off-by-one range
    labels ("Paragraphs 2-20" vs "1-20") sit at ~0.994, while 86 Evangelii Nuntiandi
    points whose Qdrant label is a wholly different heading sit at ~0.930 — WORSE than
    the refused marker_prefix. A single threshold would split that cluster arbitrarily.
  - `minor_text` (median 0.943) also reproduces worse than `marker_prefix` (0.977), so
    a similarity rule would refuse points this selects and select points it refuses.

The actual rule is cost:

  - fix everything whose repair is cheap and makes the point exactly right (350 points)
  - refuse the one category where the identical marginal gain costs 75x more and turns
    a bounded repair into a corpus-wide rewrite (26,581 points, all one collection)

`marker_prefix` is also the one category whose drift is a KNOWN, deliberate,
already-understood transformation — commit 16f6d27 moved the marker out of `content`
into `unit_label` — rather than an unexplained divergence. Refusing it is a decision
about blast radius, not a claim that its vectors are better than the ones being fixed.

⚠️  RUN THIS BEFORE `reconcile_qdrant_payloads.py --fields content`.
That sync overwrites Qdrant `content` with the Postgres row — the signal this module
classifies on. Simulated against the live corpus, running it first would:

  - permanently hide 54 points: 25 of the 86 `content_unrelated` (17 of them Gaudete
    in Domino, whose vectors were built from footnotes) and ALL 29 `minor_text`
  - leave 296 still selectable, because the other 61 `content_unrelated` points also
    have a drifted `chapter_label` and the reconcile does not sync that field

The second half is what makes this dangerous. The tool would not report "nothing to
do" — it would report `selected=296`, a healthy-looking number, while 54 points became
undetectable. The evidence and the defect live in the same field, so repairing the
evidence first is unrecoverable without re-deriving the ids from a backup.

TWO DRIFT AXES, because both feed the embedding input:
  content        the passage text
  chapter_label  the embedding PREFIX (see backfill_vectors.legacy_prefix)

A point drifted on either axis was embedded from an input today's row would not
reproduce.
"""
from __future__ import annotations

# Ordered by severity. `classify` returns the first that applies, so a point drifted on
# both axes reports the more serious one.
BLANK_SOURCE = "blank_source"
CONTENT_UNRELATED = "content_unrelated"
LABEL_DRIFT = "label_drift"
MINOR_TEXT = "minor_text"
MARKER_PREFIX = "marker_prefix"
IN_SYNC = "in_sync"

# Re-embedded by default. TWO categories are deliberately absent.
#
# `marker_prefix` — 26,581 Summa points whose repair would be as marginal as the
# `label_drift` points this DOES select (median reproduction 0.977 vs 0.988), for 113x
# the writes. Refused on blast radius, not on vector quality; see the module docstring.
#
# `blank_source` — 21 Summa chunks hold content='' in Postgres while Qdrant holds
# usable text. There is nothing to rebuild a vector FROM: embedding a blank passage
# yields a vector of the bare prefix, which would be worse than the stale-but-real
# vector already stored. These are an ingest defect to fix upstream, and no category
# selection may include them (see `needs_reembed`).
DEFAULT_CATEGORIES: frozenset[str] = frozenset({CONTENT_UNRELATED, LABEL_DRIFT, MINOR_TEXT})

# The dialectical markers `ingest/summa.py` moved out of `content` into `unit_label`.
# A Qdrant payload that still leads with one is a pre-16f6d27 copy of the same passage,
# not a different passage.
_MARKERS = ("Reply to Objection", "Objection", "I answer that", "On the contrary")

# Above this Jaccard overlap of word sets, two texts are the same passage edited;
# below it they are different passages.
#
# Measured over all 54,027 live points: `content_unrelated` tops out at 0.326, and of
# the points whose ONLY route to "same passage" is this rule (n=10, the rest also match
# a prefix/suffix test) the minimum is 0.652. So the empty band is (0.326, 0.652) and
# 0.5 sits inside it — but with roughly 4x less margin than a first reading of the
# distribution suggests, because most same-passage drifts never reach this rule at all.
# Moving it anywhere in that band changes nothing; moving it outside would only relabel
# points that are selected either way.
_SAME_PASSAGE_OVERLAP = 0.5


def _strip_marker(qdrant_content: str) -> str | None:
    """The text after a leading dialectical marker, or None if there is no marker."""
    for marker in _MARKERS:
        if qdrant_content.startswith(marker):
            return qdrant_content[len(marker):].lstrip(" 0123456789")
    return None


def _word_overlap(a: str, b: str) -> float:
    left, right = set(a.lower().split()), set(b.lower().split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def classify(
    pg_content: str,
    qdrant_content: str,
    pg_label: str | None,
    qdrant_label: str | None,
) -> str:
    """Which drift category this point falls in.

    A blank Postgres passage is checked FIRST: it is unrepairable rather than merely
    drifted, and every same-passage test below would misread it, because the empty
    string is a prefix of every string.

    Content is judged next because it is the more serious axis: a point built from
    unrelated text is wrong regardless of its prefix. Label drift follows, so a point
    whose text matches but whose prefix moved is still caught — its vector was embedded
    behind a different heading.

    `marker_prefix` is returned only when the label ALSO matches. A Summa point that is
    a benign marker-strip but whose label moved would otherwise be filed as benign and
    skipped, when in fact its prefix changed.
    """
    if not pg_content.strip():
        return BLANK_SOURCE

    stripped = _strip_marker(qdrant_content)
    label_differs = pg_label != qdrant_label

    if pg_content != qdrant_content:
        # Guarded against the empty payload for the same reason: "" is a prefix of
        # everything, so an unguarded startswith would file a blank Qdrant copy as a
        # benign "trailing text added" and leave the point broken.
        # Both tests, not either. The overlap conjunct carries the real load — sweeping
        # the prefix width over 1..2000 characters changes no live classification, so
        # the prefix test is currently inert and kept as a cheap structural guard. The
        # overlap test is what stops an older revision that merely shares an opening
        # sentence being filed as MARKER_PREFIX and therefore REFUSED. Every one of the 26,581 live marker strips passes both (26,561 are
        # byte-identical after the marker; the other 20 differ only at a truncation
        # boundary, overlap 0.935-1.000), so requiring both costs nothing today and
        # closes the one path by which a genuinely stale point could be skipped.
        is_marker_strip = (
            stripped is not None and bool(stripped)
            and stripped.startswith(pg_content[:40])
            and _word_overlap(pg_content, stripped) > _SAME_PASSAGE_OVERLAP
        )
        same_passage = bool(qdrant_content.strip()) and (
            is_marker_strip
            or qdrant_content.startswith(pg_content)   # trailing text removed
            or pg_content.startswith(qdrant_content)   # trailing text added
            or _word_overlap(pg_content, qdrant_content) > _SAME_PASSAGE_OVERLAP
        )
        if not same_passage:
            return CONTENT_UNRELATED
        if label_differs:
            return LABEL_DRIFT
        return MARKER_PREFIX if is_marker_strip else MINOR_TEXT

    return LABEL_DRIFT if label_differs else IN_SYNC


def needs_reembed(category: str, categories: frozenset[str] = DEFAULT_CATEGORIES) -> bool:
    """Whether a point in this category should be re-embedded under this selection.

    `blank_source` is refused unconditionally, whatever the caller passes: rebuilding a
    vector from an empty passage would overwrite a real-if-stale vector with one built
    from the prefix alone. No selection may opt into that.
    """
    if category in (IN_SYNC, BLANK_SOURCE):
        return False
    return category in categories
