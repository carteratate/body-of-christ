"""Hard validation for Pass 2 (classification) and Pass 3 (annotation assembly).

Grounding/kind enum membership is already enforced by the `Literal` types on
`Label` (enrichment/schema.py) at Pydantic parse time — a bad enum value never
reaches this module, it raises `pydantic.ValidationError` first. This module
checks everything Pydantic *can't*: cross-referencing labels against facets,
verifying explicit-grounding quotes against the actual passage text, and
parsing/matching the annotation's segment headers against Pass 2's labels.
"""
from __future__ import annotations

import re
import string

import tiktoken

from enrichment.schema import GenFacet, Label

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


_BANNED_OPENERS = ("thus", "therefore", "hence", "in this way")
_LEADING_QUOTE_BRACKET_RE = re.compile(r'^[\s"\'’“‘(\[]+')
_WORD_RE = re.compile(r"[A-Za-z']+")


def _word_count(text: str) -> int:
    return len(text.translate(_PUNCTUATION_TABLE).split())


def _strip_leading_quotes_and_brackets(s: str) -> str:
    return _LEADING_QUOTE_BRACKET_RE.sub("", s)


def _starts_with_banned_opener(sentence: str) -> bool:
    stripped = _strip_leading_quotes_and_brackets(sentence).casefold()
    return any(stripped.startswith(opener) for opener in _BANNED_OPENERS)


def _has_concrete_referent(takeaway: str, passage_content: str) -> bool:
    for sentence in split_sentences(takeaway) or [takeaway]:
        words = _WORD_RE.findall(sentence)
        for i, w in enumerate(words):
            if i == 0:
                continue
            if w[:1].isupper():
                return True  # capitalized, non-sentence-initial -> proxy proper noun
    normalized_passage = normalize_for_containment(passage_content)
    for w in _WORD_RE.findall(takeaway):
        if len(w) >= 6 and w.casefold() in normalized_passage:
            return True
    return False


def check_takeaway(takeaway: str, working_text: str, passage_content: str) -> list[str]:
    """Returns a list of failed-check descriptions (empty if the takeaway passes
    every check). Each description starts with one of the fixed tags —
    sentence_count, word_count, banned_opener, concreteness, anti_copy — which
    the pilot diff-report script parses to build per-check statistics."""
    failures: list[str] = []

    sentences = split_sentences(takeaway)
    if len(sentences) > 2:
        failures.append(f"sentence_count: takeaway has {len(sentences)} sentences (max 2)")

    wc = _word_count(takeaway)
    if not (30 <= wc <= 70):
        failures.append(f"word_count: takeaway has {wc} words (expected 30-70)")

    for sentence in sentences:
        if _starts_with_banned_opener(sentence):
            failures.append(f"banned_opener: sentence begins with a banned opener: {sentence!r}")

    if not _has_concrete_referent(takeaway, passage_content):
        failures.append(
            "concreteness: no capitalized non-initial token (proxy proper noun) and no "
            "content word >=6 chars shared with the passage"
        )

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


def validate_evidence_style(labels: list[Label]) -> list[str]:
    """Soft warnings (never raises) for settled/inferential evidence that looks
    stuffed: too long, semicolon-joined, or citing more than one reference."""
    warnings: list[str] = []
    for i, lab in enumerate(labels):
        if lab.grounding not in ("settled", "inferential"):
            continue
        wc = _word_count(lab.evidence)
        if wc > 25:
            warnings.append(f"label[{i}] evidence_length: evidence is {wc} words (soft cap ~25)")
        if ";" in lab.evidence:
            warnings.append(f"label[{i}] evidence_semicolon: evidence contains a semicolon")
        citations = _CITATION_RE.findall(lab.evidence)
        if len(citations) > 1:
            warnings.append(
                f"label[{i}] evidence_citations: {len(citations)} citation-like tokens (soft cap 1)"
            )
    return warnings


def validate_classification(facets: list[GenFacet], labels: list[Label], content: str) -> None:
    """Raises ValidationFailedError if `labels` doesn't validly correspond to `facets`."""
    if len(labels) != len(facets):
        raise ValidationFailedError(
            [f"expected {len(facets)} labels (one per facet), got {len(labels)}"]
        )

    errors: list[str] = []
    normalized_content = normalize_for_containment(content)
    for i, label in enumerate(labels):
        if not label.evidence or not label.evidence.strip():
            errors.append(f"label[{i}]: evidence must be non-empty")
            continue
        if label.grounding == "explicit":
            normalized_evidence = normalize_for_containment(label.evidence)
            if normalized_evidence not in normalized_content:
                errors.append(
                    f"label[{i}]: grounding=explicit requires evidence to be a verbatim "
                    f"quote from the passage, but {label.evidence!r} was not found"
                )

    if errors:
        raise ValidationFailedError(errors)


def _kind_header(kind: str, kind_secondary: str | None) -> str:
    if kind_secondary:
        return f"{kind}/{kind_secondary}"
    return kind


def validate_annotation(facets_with_labels: list[dict], annotation: str) -> list[str]:
    """Raises ValidationFailedError on hard failures (missing SUMMARY, segment count
    or label mismatch). Returns a list of soft warnings (e.g. length outside the
    soft 400-600 token target) when the annotation is otherwise valid.
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

    if errors:
        raise ValidationFailedError(errors)

    warnings: list[str] = []
    token_count = len(_TOKENIZER.encode(annotation))
    if not (400 <= token_count <= 600):
        warnings.append(f"annotation is ~{token_count} tokens, outside the soft 400-600 target")
    return warnings
