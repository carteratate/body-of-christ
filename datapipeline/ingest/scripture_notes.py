"""Scripture references in translators' notes (1.10b).

ANF and NPNF translators mark which verse a Father quotes with a note such as
"Matt. xxiv. 15." Those references are kept as the passage's footnotes, as the
Catechism's are (#279); every other note is editor material and stays out (rule G,
as Carter revised it on 31 Oct 2026). A note that opens with a reference and goes on
to a remark ("Ps. xxxiv. 8, where Clem. has read…") keeps the reference only.
"""
from __future__ import annotations

import re

# Book names as the ANF and NPNF notes print them (measured on the vendored sources), and
# Schaff's "Coloss." (1.2d).
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
    "Colossians|Coloss|Col|Thessalonians|Thess|Timothy|Tim|Titus|Tit|Philemon|Philem|"
    "Hebrews|Heb|James|Jas|Peter|Pet|Jude|Revelation|Rev|Apocalypse|Apoc"
)
_BOOK = rf"(?:(?:[1-4]|I{{1,3}})\s?)?(?:St\.\s)?(?:{_BOOKS})\.?"
_ROMAN = r"[ivxlc]+"
_VERSES = r"\d+(?:\s?[-–]\s?\d+)?(?:\s?f{1,2}\.?)?"
# A further verse, never the number of a book that follows ("16, 1 Cor. vi. 19").
_MORE_VERSES = rf"(?:\s?,\s?(?!(?:[1-4])\s?(?:{_BOOKS})\b){_VERSES})*"
# "xxiv. 15", "xxiv. 15–17", "xxiv. 15, 17", "cxxxvii." (a whole chapter), and the
# Arabic form some volumes use ("17:21", "17:21-23").
_CHAPTER_VERSES = (rf"(?:{_ROMAN}\.(?:\s?{_VERSES}{_MORE_VERSES})?"
                   rf"|\d+:{_VERSES}{_MORE_VERSES})")
_TAG = r"(?:\s?\((?:LXX|Sept|Vulg)\.?\)|,\s?(?:LXX|Sept|Vulg)\.?)?"
_ONE = rf"(?:{_BOOK}\s{_CHAPTER_VERSES}|{_CHAPTER_VERSES}|ver\.\s{_VERSES}){_TAG}"
_LEAD = r"(?:(?:Cf|Comp|Compare|See|Vid)\.?\s)?"
_REFERENCE = re.compile(rf"^\[?{_LEAD}{_BOOK}\s{_CHAPTER_VERSES}{_TAG}"
                        rf"(?:\s?(?:;|,|:|and)\s?{_LEAD}{_ONE})*")

# The Vulgate's names as the Gutenberg editions print them (5.6b: the Glories of Mary's
# "Joan. xix. 26.", "Eccli. xxiv. 19."; measured on the vendored files), and a chapter
# set off by a comma (Brother Lawrence's "Gal. i, 10; Eph. vi, 5, 6.", the Glories'
# "Cant. 6, 9."); and Hilton's 1901 printing's forms: a whole chapter in Arabic numerals,
# ending the note or before another book, and "St" or "S." without the usual stop ("1 Cor.
# 13.", "St Matt. 5.", "1 St John 4:1.", "S. Matt. 5.", "Jerem. 9.", "Osee 2."). Read only
# for the works that ask for them (`vulgate=True`), so no other collection's footnotes
# change.
_VULGATE_BOOKS = ("Joan|Psal|Luc|Eccli|Matth|Mach|Zacc|Thren|Thr|Ezech|Jac|Sap|Colos|"
                  "Jerem|Osee|Ga")
_V_BOOK = rf"(?:(?:[1-4]|I{{1,3}})\s?)?(?:St\.?\s|S\.\s)?(?:{_VULGATE_BOOKS}|{_BOOKS})\.?"
# "l. 1, c. 10" is a book and chapter of another work ("Rev. l. 1, c. 10": St Bridget's
# Revelations, liber 1, caput 10), not chapter fifty ("Psal. l. 19" is).
_V_CHAPTER_VERSES = (rf"(?:(?!l\.\s?\d+[.,]\s?c\.){_ROMAN}[.,](?:\s?{_VERSES}{_MORE_VERSES})?"
                     rf"|\d+[:,]\s?{_VERSES}{_MORE_VERSES}|\d+(?=\.?$|\s?[;,]\s?(?:[1-4]\s)?[A-Z]))")
_V_ONE = rf"(?:{_V_BOOK}\s{_V_CHAPTER_VERSES}|{_V_CHAPTER_VERSES}|ver\.\s{_VERSES}){_TAG}"
_VULGATE_REFERENCE = re.compile(rf"^\[?{_LEAD}{_V_BOOK}\s{_V_CHAPTER_VERSES}{_TAG}"
                                rf"(?:\s?(?:;|,|:|and)\s?{_LEAD}{_V_ONE})*")


def scripture_reference(note: str, vulgate: bool = False) -> str | None:
    """The scripture reference a translator's note opens with, as printed, or None when
    the note is not a scripture reference. With `vulgate`, the Vulgate's book names and a
    chapter set off by a comma are read too."""
    text = " ".join(note.split())
    m = (_VULGATE_REFERENCE if vulgate else _REFERENCE).match(text)
    if not m:
        return None
    ref = m.group(0).rstrip(" ,;").lstrip("[")
    rest = text[m.end():]
    # "Ps. xliii. 20 (LXX.)." keeps its tag; anything after the reference is a remark.
    if rest[:1] not in ("", ".", " ", ",", ";", ":", "]", ")"):
        return None
    return ref if ref.endswith(".") else ref + "."
