"""Scripture references in translators' notes (1.10b).

ANF and NPNF translators mark which verse a Father quotes with a note such as
"Matt. xxiv. 15." Those references are kept as the passage's footnotes, as the
Catechism's are (#279); every other note is editor material and stays out (rule G,
as Carter revised it on 31 Oct 2026). A note that opens with a reference and goes on
to a remark ("Ps. xxxiv. 8, where Clem. has read…") keeps the reference only.
"""
from __future__ import annotations

import re

# Book names as the ANF and NPNF notes print them (measured on the vendored sources).
_BOOKS = (
    "Genesis|Gen|Exodus|Exod|Ex|Leviticus|Levit|Lev|Numbers|Numb|Num|Deuteronomy|Deut|"
    "Joshua|Josh|Judges|Judg|Ruth|Samuel|Sam|Kings|Chronicles|Chron|Ezra|Nehemiah|Neh|"
    "Esdras|Esdr|Tobit|Tob|Judith|Esther|Esth|Maccabees|Macc|Mac|Job|Psalms|Psalm|Ps|"
    "Proverbs|Prov|Ecclesiastes|Eccles|Eccl|Song of Solomon|Song of Sol|Canticles|Cant|"
    "Wisdom of Solomon|Wisdom of Sol|Wisd\\. of Solom|Wisd\\. of Sol|Wisd\\. Solom|"
    "Wisdom|Wisd|Wis|Ecclesiasticus|Ecclus|Sirach|Isaiah|Isa|Is|Jeremiah|Jer|"
    "Lamentations|Lam|Baruch|Bar|Ezekiel|Ezek|Daniel|Dan|Hosea|Hos|Joel|Amos|Obadiah|Obad|"
    "Jonah|Jon|Micah|Mic|Nahum|Nah|Habakkuk|Habak|Hab|Zephaniah|Zeph|Sophon|Haggai|Hagg|"
    "Hag|Zechariah|Zech|Malachi|Mal|Matthew|Matt|Mark|Luke|John|Acts of Apostles|Acts|"
    "Romans|Rom|Corinthians|Cor|Galatians|Gal|Ephesians|Ephes|Eph|Philippians|Philipp|Phil|"
    "Colossians|Col|Thessalonians|Thess|Timothy|Tim|Titus|Tit|Philemon|Philem|Hebrews|Heb|"
    "James|Jas|Peter|Pet|Jude|Revelation|Rev|Apocalypse|Apoc"
)
_BOOK = rf"(?:(?:[1-4]|I{{1,3}})\s?)?(?:St\.\s)?(?:{_BOOKS})\.?"
_ROMAN = r"[ivxlc]+"
_VERSES = r"\d+(?:\s?[-–]\s?\d+)?(?:\s?f{1,2}\.?)?"
# "xxiv. 15", "xxiv. 15–17", "xxiv. 15, 17", "cxxxvii." (a whole chapter)
_CHAPTER_VERSES = rf"{_ROMAN}\.(?:\s?{_VERSES}(?:\s?,\s?{_VERSES})*)?"
_TAG = r"(?:\s?\((?:LXX|Sept|Vulg)\.?\)|,\s?(?:LXX|Sept|Vulg)\.?)?"
_ONE = rf"(?:{_BOOK}\s{_CHAPTER_VERSES}|{_CHAPTER_VERSES}|ver\.\s{_VERSES}){_TAG}"
_LEAD = r"(?:(?:Cf|Comp|Compare|See|Vid)\.?\s)?"
_REFERENCE = re.compile(rf"^\[?{_LEAD}{_BOOK}\s{_CHAPTER_VERSES}{_TAG}"
                        rf"(?:\s?(?:;|,|:|and)\s?{_LEAD}{_ONE})*")


def scripture_reference(note: str) -> str | None:
    """The scripture reference a translator's note opens with, as printed, or None when
    the note is not a scripture reference."""
    text = " ".join(note.split())
    m = _REFERENCE.match(text)
    if not m:
        return None
    ref = m.group(0).rstrip(" ,;").lstrip("[")
    rest = text[m.end():]
    # "Ps. xliii. 20 (LXX.)." keeps its tag; anything after the reference is a remark.
    if rest[:1] not in ("", ".", " ", ",", ";", "]", ")"):
        return None
    return ref if ref.endswith(".") else ref + "."
