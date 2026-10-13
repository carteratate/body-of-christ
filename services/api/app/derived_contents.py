"""A stopgap Summa contents tree, derived from today's chapter list (issue #251).

The Summa adapter will emit its own tree (Part > Treatise > Question > Article, #254)
once the 1.7 adapter rework is published. Until a stored tree exists, /toc derives
Part > Question > Article from the current chapter keys and labels so the reader can
show the Parts now. Delete this module, and its call in routes/documents.py, once the
Summa is published with a stored tree.

Today's chapters look like:
    key   summa/<part-slug>/<question-slug>/<article-slug>
    label "Question 3 - Of the Simplicity of God (EIGHT ARTICLES) — Article 1 - Whether God is a body?"
Three of 3,120 labels differ: an article title with no "Article N - " prefix, and two
appendix articles under "Two Articles on Purgatory", a question with no number. A key
or label this module cannot read makes it return None, and the reader keeps the flat list.
"""
from __future__ import annotations

import re

from app.models.documents import ContentsNode

# Ordered: "first-part-of-the-second-part..." must be tried before "first-part".
_PARTS: tuple[tuple[str, str, str], ...] = (
    ("first-part-of-the-second-part", "I-II", "First Part of the Second Part"),
    ("second-part-of-the-second-part", "II-II", "Second Part of the Second Part"),
    ("first-part", "I", "First Part"),
    ("third-part", "III", "Third Part"),
    ("supplement", "Suppl.", "Supplement to the Third Part"),
    ("appendix", "App.", "Appendix"),
)
_QUESTION = re.compile(r"^Question (\d+) - (.+?)\s*(?:\(([A-Za-z ]+ ARTICLES?)\))?$", re.I)
_ARTICLE = re.compile(r"^Article (\d+) - (.+)$")
# Where the source put a treatise heading in place of a question title: its range
# ("Evil Habits, i.e. Vices and Sins (Qq. 71–89)") and outline letter ("(D) By Sins...").
_TREATISE_RANGE = re.compile(r"\s*\(Qq?\.\s*[\d–-]+\)$")
_OUTLINE_LETTER = re.compile(r"^\([A-Z]\)\s+")
_SMALL = frozenset({"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of",
                    "on", "or", "the", "to", "with"})


def _part(slug: str) -> tuple[str, str] | None:
    for prefix, numeral, name in _PARTS:
        if slug == prefix or slug.startswith(prefix + "-"):
            return numeral, name
    return None


_CAPITALS = re.compile(r"[A-Z][A-Z']+")
_ROMAN = re.compile(r"[IVXLC]+")


def _uncap(title: str) -> str:
    """Title-case words the source prints in capitals, whole headings ("OF DULIA") or
    parts of them ("Of the Name of the Holy Ghost, AS GIFT"), and turn its "---" into a
    dash. Roman numerals stay as they are."""
    title = " ".join(title.replace("---", " — ").split())

    def fix(match: re.Match[str]) -> str:
        word = match.group(0)
        if _ROMAN.fullmatch(word):
            return word
        lower = word.lower()
        first = match.start() == 0
        return lower if not first and lower in _SMALL else lower[:1].upper() + lower[1:]

    return _CAPITALS.sub(fix, title)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def derive_summa_contents(chapters: list[tuple[str, str | None]]) -> list[ContentsNode] | None:
    """Part > Question > Article from (chapter_key, chapter_label) pairs in reading order."""
    parts: list[ContentsNode] = []
    part_questions: dict[str, list[int]] = {}
    seen: set[str] = set()
    last_question_slug: str | None = None
    for chapter_key, chapter_label in chapters:
        segments = chapter_key.split("/")
        if len(segments) != 4 or segments[0] != "summa" or not chapter_label:
            return None
        _, part_slug, question_slug, _article_slug = segments
        part = _part(part_slug)
        question_text, sep, article_text = chapter_label.partition(" — ")
        if part is None or not sep:
            return None

        # Keys are short citation-like paths ("I-II/q1/a1"), not the 188-character
        # chapter keys, which every node already carries once as chapter_key.
        numeral, name = part
        if not parts or parts[-1].key != numeral:
            if numeral in seen:            # a Part that comes back later: not reading order
                return None
            seen.add(numeral)
            parts.append(ContentsNode(
                key=numeral, kind="part", label=name, short_label=f"{numeral} · {name}",
                chapter_key=chapter_key, children=[]))
            part_questions[numeral] = []
            last_question_slug = None
        questions = parts[-1].children

        if question_slug != last_question_slug:
            last_question_slug = question_slug
            match = _QUESTION.match(question_text)
            if match:
                title = _OUTLINE_LETTER.sub("", _TREATISE_RANGE.sub("", match.group(2)))
                number, title = match.group(1), _uncap(title)
                short_label = f"Q. {number} · {title}"
                question_key = f"{numeral}/q{number}"
                part_questions[numeral].append(int(number))
            else:
                title = short_label = _uncap(question_text)
                question_key = f"{numeral}/{question_slug}"
            if question_key in seen:       # a question that comes back later
                return None
            seen.add(question_key)
            questions.append(ContentsNode(
                key=question_key, kind="question", label=title, short_label=short_label,
                chapter_key=chapter_key, children=[]))
        question = questions[-1]

        match = _ARTICLE.match(article_text)
        title = _uncap(match.group(2) if match else article_text)
        short_label = f"Art. {match.group(1)} · {title}" if match else title
        article_key = f"{question.key}/a{match.group(1)}" if match else None
        if article_key is None or article_key in seen:
            # Unnumbered, or a number the source repeats (I q.114 has two "Article 4"s):
            # the chapter's own slug is unique within its question.
            article_key = f"{question.key}/{_article_slug}"
        if article_key in seen:
            return None
        seen.add(article_key)
        question.children.append(ContentsNode(
            key=article_key, kind="article", label=title, short_label=short_label,
            chapter_key=chapter_key, children=[]))

    for part in parts:
        numbers = part_questions[part.key]
        if numbers:
            low, high = min(numbers), max(numbers)
            part.range_label = f"Q. {low}" if low == high else f"Qq. {low}–{high}"
        for question in part.children:
            question.range_label = _count(len(question.children), "article")
    return parts or None
