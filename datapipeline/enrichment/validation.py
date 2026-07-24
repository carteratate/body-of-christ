"""Hard validation for Pass 2 (classification) and Pass 3 (annotation assembly).

Grounding/kind enum membership is already enforced by the `Literal` types on
`Label` (enrichment/schema.py) at Pydantic parse time — a bad enum value never
reaches this module, it raises `pydantic.ValidationError` first. This module
checks everything Pydantic *can't*: cross-referencing labels against facets,
verifying explicit-grounding quotes against the actual passage text, and
parsing/matching the annotation's segment headers against Pass 2's labels.
"""
from __future__ import annotations

import math
import re
import string

import tiktoken

from enrichment.schema import GenFacet, IdentifiedFacet, Label

_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Source texts (e.g. the WEB Bible) use typographic Unicode punctuation
# (curly quotes, em/en dashes, ellipsis) that `string.punctuation` (ASCII-only)
# doesn't cover. Without these, a passage's curly apostrophe and a model's
# straight apostrophe normalize to two different strings and a correct
# verbatim quote is wrongly rejected as not-found.
_TYPOGRAPHIC_PUNCTUATION = "‘’“”–—…·"
_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation + _TYPOGRAPHIC_PUNCTUATION)

_SEGMENT_HEADER_RE = re.compile(
    r"^\[([A-Za-z]+)(?:/([A-Za-z]+))?\s*\|\s*([A-Za-z]+)\]:", re.MULTILINE
)

# Conservative sentence splitter for theological prose full of abbreviations and
# scripture/citation references (St., cf., v., ch., 1 Cor. 11:23) — a naive split
# on ". " would badly overcount sentences in this domain. This deliberately
# under-splits rather than over-splits: it only needs to count sentences well
# enough to catch runaway takeaways, not to be a general-purpose tokenizer.
_ABBREVIATIONS = {
    "st", "sts", "mr", "mrs", "dr", "rev", "fr", "prof", "vs", "etc", "cf",
    "v", "vv", "ch", "chs", "no", "vol", "col", "p", "pp", "ed", "eds", "trans", "cent",
    # biblical book abbreviations commonly written with a trailing period
    "gen", "ex", "exod", "lev", "num", "deut", "josh", "judg", "ruth", "sam", "kgs",
    "chr", "ezra", "neh", "esth", "job", "ps", "psa", "prov", "eccl", "song", "isa",
    "jer", "lam", "ezek", "dan", "hos", "joel", "amos", "obad", "jon", "mic", "nah",
    "hab", "zeph", "hag", "zech", "mal", "matt", "mk", "lk", "jn", "acts", "rom",
    "cor", "gal", "eph", "phil", "col", "thess", "tim", "titus", "phlm", "heb",
    "jas", "pet", "jude", "rev",
    # scholastic/patristic
    "q", "qq", "a", "aa", "ad", "obj", "resp", "sc",
}

# Split candidates: sentence-ending punctuation (optionally followed by a closing
# quote/bracket, e.g. `see."`) then whitespace, then either a capital letter or an
# opening quote/bracket (a lowercase or digit continuation, e.g. "Cor. 11:23",
# never triggers a split attempt at all).
_SENTENCE_SPLIT_RE = re.compile(r'([.!?])(["\'’”)\]]*)\s+(?=[A-Z"‘“(\[])')
_TRAILING_WORD_RE = re.compile(r"([A-Za-z]+)$")


def _ends_in_abbreviation(text_before_punct: str) -> bool:
    m = _TRAILING_WORD_RE.search(text_before_punct)
    return bool(m) and m.group(1).lower() in _ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Splits `text` into sentences, skipping split points that immediately
    follow a known abbreviation (so "St. Paul" or "cf. Genesis" don't count as
    two sentences)."""
    sentences: list[str] = []
    pos = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        end = m.end(2)  # include the punctuation mark and any closing quote/bracket
        before = text[pos:m.start()]
        if _ends_in_abbreviation(before):
            continue
        sentences.append(text[pos:end].strip())
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        sentences.append(tail)
    return sentences


class ValidationFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def normalize_for_containment(s: str) -> str:
    """Casefold, strip punctuation, and collapse whitespace for substring checks."""
    s = s.translate(_PUNCTUATION_TABLE).casefold()
    return " ".join(s.split())


def _word_count(text: str) -> int:
    return len(text.translate(_PUNCTUATION_TABLE).split())


def check_takeaway(takeaway: str, working_text: str, passage_content: str) -> list[str]:
    """Returns a list of failed-check descriptions (empty if the takeaway passes
    every check). Each description starts with one of the fixed tags —
    sentence_count, anti_copy — which the pilot diff-report script parses to
    build per-check statistics.

    Every check here has to correspond to something the Pass 1 prompt actually
    asks for (enrichment/prompts/base.py); a hard failure the model was never
    told to avoid burns an Opus retry and then drops the chunk. Three checks
    were removed for that reason when the prompt loosened:

    - word_count and banned_opener mirrored "30-70 words" and "no Thus/
      Therefore/In this way", neither of which the prompt states any more.
    - concreteness required either a capitalized non-initial token or a >=6
      char word shared verbatim with the passage. It was safe only while the
      prompt carried the "keep the concrete referents" bullet, which is also
      gone. It matched by exact substring, so inflection alone could fail a
      good takeaway ("weeping/laughing" against a passage reading "to weep...
      to laugh"), and abstract synthesis over poetic or wisdom literature has
      neither a proper noun nor shared vocabulary to offer.

    `sentence_count` stays because the prompt does state a range (2-4).
    """
    failures: list[str] = []

    sentences = split_sentences(takeaway)
    if len(sentences) > 4:
        failures.append(f"sentence_count: takeaway has {len(sentences)} sentences (max 4)")

    normalized_takeaway = normalize_for_containment(takeaway)
    normalized_working_text = normalize_for_containment(working_text)
    if normalized_takeaway and normalized_takeaway in normalized_working_text:
        failures.append("anti_copy: takeaway is a contiguous substring of the working text")

    return failures


def validate_generation(facets: list[GenFacet], passage_content: str) -> None:
    """Raises ValidationFailedError if any facet's takeaway fails check_takeaway()."""
    errors: list[str] = []
    for i, f in enumerate(facets):
        for failure in check_takeaway(f.takeaway, f.text, passage_content):
            errors.append(f"facet[{i}] {failure}")
    if errors:
        raise ValidationFailedError(errors)


# Citation-like tokens: "CCC 613" or a book-chapter-verse reference like
# "John 19:36" / "1 Cor 11:23". Crude on purpose — this only gates a soft
# stuffing warning, not a hard failure.
_CITATION_RE = re.compile(r"\bCCC\s*\d+\b|\b(?:[1-3]\s?)?[A-Z][a-zA-Z]+\.?\s+\d+:\d+\b")

# Words/phrases that, when they appear in a `settled` label's evidence, signal
# the reasoning actually depends on tradition, an external text, or a
# synthesis step — i.e. it reads like inferential evidence mislabeled as
# settled, since settled requires one step from THIS passage's own words
# alone (enrichment/prompts/classification.py's grounding rules).
_TRADITION_SIGNAL_RE = re.compile(
    r"\b(tradition(?:ally)?|synthesis|argument|external(?:ly)?|assumes?|"
    r"implies?|presuppos\w*|elsewhere|magisterium|read together with|"
    r"in light of|connects? to|depends? on)\b",
    re.IGNORECASE,
)


def validate_evidence_style(labels: list[Label]) -> list[str]:
    """Soft warnings (never raises), grounding-aware:

    - explicit: no warnings here. Contiguous-span containment is a HARD check
      in validate_classification (punctuation/whitespace-normalized
      containment, not byte-for-byte verbatim) — there is nothing further to
      warn about for this tier.
    - settled: warns on stuffed evidence (long, semicolon-joined, or multiple
      citation-like tokens) AND on a new consistency signal — language in the
      evidence itself (tradition, synthesis, an external connection) that
      suggests the label actually depends on more than THIS passage's own
      wording, i.e. it may really be inferential.
    - inferential: warns on length/semicolon stuffing only. Citing an outside
      reference is expected for a claim that already requires an external
      connection, so citation count is never penalized here.
    """
    warnings: list[str] = []
    for i, lab in enumerate(labels):
        if lab.grounding not in ("settled", "inferential"):
            continue

        wc = _word_count(lab.evidence)
        if wc > 25:
            warnings.append(f"label[{i}] evidence_length: evidence is {wc} words (soft cap ~25)")
        if ";" in lab.evidence:
            warnings.append(f"label[{i}] evidence_semicolon: evidence contains a semicolon")

        if lab.grounding == "settled":
            if _TRADITION_SIGNAL_RE.search(lab.evidence):
                warnings.append(
                    f"label[{i}] settled_consistency: evidence for a 'settled' label names "
                    f"tradition/synthesis/an external connection ({lab.evidence!r}) — settled "
                    f"requires one step from THIS passage's own words alone; consider whether "
                    f"this should be inferential instead"
                )
            citations = _CITATION_RE.findall(lab.evidence)
            if len(citations) > 1:
                warnings.append(
                    f"label[{i}] evidence_citations: {len(citations)} citation-like tokens "
                    f"(soft cap 1) — citing multiple external references from a 'settled' label "
                    f"suggests it actually needs an outside connection, i.e. inferential"
                )
    return warnings


def validate_classification(facets: list[IdentifiedFacet], labels: list[Label], content: str) -> None:
    """Raises ValidationFailedError if `labels` doesn't validly correspond to
    `facets`. Identity between a label and its facet is established solely by
    `facet_id` — never by array position. A bijection is required: every
    facet gets exactly one label, every label references a facet that was
    actually supplied, and no facet_id repeats. Reordering by Pass 2 is fine
    (see `reorder_labels_by_facet_id`); missing, duplicate, or unknown ids are
    not — they are hard failures, never silently repaired.
    """
    if len(labels) != len(facets):
        raise ValidationFailedError(
            [f"expected {len(facets)} labels (one per facet), got {len(labels)}"]
        )

    expected_ids = [f.id for f in facets]
    provided_ids = [label.facet_id for label in labels]

    id_errors: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for fid in provided_ids:
        if fid in seen:
            duplicates.add(fid)
        seen.add(fid)
    if duplicates:
        id_errors.append(f"duplicate facet_id(s) in labels: {sorted(duplicates)}")

    missing = set(expected_ids) - set(provided_ids)
    if missing:
        id_errors.append(f"missing classification for facet_id(s): {sorted(missing)}")

    unknown = set(provided_ids) - set(expected_ids)
    if unknown:
        id_errors.append(f"label(s) reference unknown facet_id(s): {sorted(unknown)}")

    if id_errors:
        raise ValidationFailedError(id_errors)

    errors: list[str] = []
    normalized_content = normalize_for_containment(content)
    for label in labels:
        if not label.evidence or not label.evidence.strip():
            errors.append(f"label[{label.facet_id}]: evidence must be non-empty")
            continue
        if label.grounding == "explicit":
            normalized_evidence = normalize_for_containment(label.evidence)
            if normalized_evidence not in normalized_content:
                # Surgical, per-facet retry guidance (not a generic message):
                # names the exact failing facet_id, states the contiguous-span
                # rule precisely (punctuation/whitespace-normalized containment,
                # not byte-for-byte verbatim), and gives the two concrete ways
                # to fix just that facet, while reminding the model the full
                # ID bijection across every supplied facet is still required.
                # This text becomes the retry_errors context for the one retry
                # attempt (_call_with_retry), so it must be self-sufficient.
                errors.append(
                    f"Facet {label.facet_id} failed: grounding=explicit requires evidence to be "
                    f"ONE contiguous span from the passage (punctuation/whitespace-normalized "
                    f"containment, not byte-for-byte verbatim, but never two separate sentences or "
                    f"spans stitched together). Evidence given for {label.facet_id}: "
                    f"{label.evidence!r} — this was not found as a single contiguous span. "
                    f"Reclassify {label.facet_id} only: either give one contiguous span that "
                    f"directly states its complete central claim, or lower its grounding to "
                    f"settled or inferential. Return a complete labels array with exactly one "
                    f"label per every supplied facet ID — the full ID bijection is still required."
                )

    if errors:
        raise ValidationFailedError(errors)


def reorder_labels_by_facet_id(facets: list[IdentifiedFacet], labels: list[Label]) -> list[Label]:
    """Realigns `labels` into `facets`' order by joining on `facet_id`. Must
    only be called after `validate_classification` has confirmed a 1:1
    facet_id correspondence — this performs no validation of its own, and
    trusts the caller that every facet id in `facets` has exactly one
    matching label."""
    by_id = {label.facet_id: label for label in labels}
    return [by_id[f.id] for f in facets]


def _kind_header(kind: str, kind_secondary: str | None) -> str:
    if kind_secondary:
        return f"{kind}/{kind_secondary}"
    return kind


_ANNOTATION_HARD_MAX_TOKENS = 800
# Facet-aware length target: ~30-60 tokens for the summary line plus ~35-55
# tokens per facet segment (normally one sentence — see
# enrichment/prompts/annotation.py), i.e. roughly 45 + 45*facet_count as a
# midpoint. A short, complete annotation below this is fine (no warning); the
# soft threshold below only fires when the annotation runs materially over it.
#
# Soft threshold = max(target + 75, ceil(target * 1.25)): a flat +75-token
# margin dominates for small facet counts (where a fixed cushion matters more
# than a percentage), and a 25%-over-target margin dominates once the target
# itself gets large (so the warning still means something at high facet
# counts instead of granting an ever-larger flat allowance). Chosen so the
# threshold stays comfortably under the fixed 800-token hard cap even at
# MAX_FACETS (12 facets -> target 585, threshold max(660, 732) = 732 < 800).


def _annotation_soft_threshold(target: int) -> int:
    return max(target + 75, math.ceil(target * 1.25))


def annotation_token_count(annotation: str) -> int:
    """Shared token-counting helper so validate_annotation and batch telemetry
    (enrichment/telemetry.py) always agree on how an annotation's length is
    measured."""
    return len(_TOKENIZER.encode(annotation))


def annotation_target_tokens(facet_count: int) -> int:
    """Facet-aware token target: ~30-60 tokens of summary plus ~35-55 tokens
    per facet segment (normally one sentence), collapsed to a single guidance
    number both the Pass 3 prompt and this validator agree on."""
    return 45 + (45 * facet_count)


def validate_annotation(facets_with_labels: list[dict], annotation: str) -> list[str]:
    """Raises ValidationFailedError on hard failures (missing SUMMARY, segment count
    or label mismatch, or exceeding the 800-token hard maximum). Returns a list of
    soft warnings (e.g. length materially above the facet-aware token target) when
    the annotation is otherwise valid. A concise, complete annotation shorter than
    the target is never warned about.
    """
    errors: list[str] = []

    if "SUMMARY:" not in annotation:
        errors.append("missing required 'SUMMARY:' line")

    segments = _SEGMENT_HEADER_RE.findall(annotation)

    if len(segments) != len(facets_with_labels):
        errors.append(
            f"expected {len(facets_with_labels)} segments (one per facet), got {len(segments)}"
        )
    else:
        for i, ((kind, kind_secondary, grounding), facet) in enumerate(zip(segments, facets_with_labels)):
            expected_kind = facet["kind"].lower()
            expected_secondary = (facet.get("kind_secondary") or None)
            expected_secondary = expected_secondary.lower() if expected_secondary else None
            expected_grounding = facet["grounding"].lower()

            got_kind = kind.lower()
            got_secondary = kind_secondary.lower() if kind_secondary else None
            got_grounding = grounding.lower()

            if (got_kind, got_secondary, got_grounding) != (expected_kind, expected_secondary, expected_grounding):
                errors.append(
                    f"segment[{i}]: label mismatch — expected "
                    f"[{_kind_header(expected_kind, expected_secondary)} | {expected_grounding}], "
                    f"got [{_kind_header(got_kind, got_secondary)} | {got_grounding}]"
                )

    token_count = annotation_token_count(annotation)
    if token_count > _ANNOTATION_HARD_MAX_TOKENS:
        errors.append(
            f"annotation is ~{token_count} tokens, exceeding the hard maximum of "
            f"{_ANNOTATION_HARD_MAX_TOKENS} tokens")

    if errors:
        raise ValidationFailedError(errors)

    warnings: list[str] = []
    target = annotation_target_tokens(len(facets_with_labels))
    threshold = _annotation_soft_threshold(target)
    if token_count > threshold:
        warnings.append(
            f"annotation is ~{token_count} tokens, materially above the facet-aware "
            f"target of ~{target} tokens (soft threshold ~{threshold}) for "
            f"{len(facets_with_labels)} facet(s)")
    return warnings
