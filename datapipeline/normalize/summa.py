"""Expand the Summa's cryptic reference apparatus into readable prose."""
from __future__ import annotations

import re

PART_NAMES = {
    "FP": "First Part",
    "FS": "First Part of the Second Part",
    "SS": "Second Part of the Second Part",
    "SP": "Second Part",
    "TP": "Third Part",
    "XP": "Supplement",
}

# Order matters: drop bracket-star notes first, then expand tokens.
# The bracket-star body may itself contain one level of nested brackets
# (e.g. "[*Cf. FP, Q[12]]"), so allow a complete "[...]" group inside.
_BRACKET_STAR = re.compile(r"\s*\[\*(?:[^\[\]]|\[[^\]]*\])*\]")
_QQ_RANGE = re.compile(r"QQ\[(\d+)\]\s*-\s*\[?(\d+)\]?")
# A source cross-reference number left in brackets (C-22): a lone "QQ[83]", a number
# after a comma or semicolon ("De Anima iii, 21,[22]", "Mat. 1:20;[2]:13"), and the
# Sentences' distinction ("Sent. iv, D[29]").
_CROSS_REF = re.compile(r"\b(QQ|D)\[(\d+)\]|([,;])\s*\[(\d+)\]")
_AA_PAIR = re.compile(r"AA\[(\d+)\]\s*,\s*(\d+)")
_AA = re.compile(r"AA\[(\d+)\]")
_Q = re.compile(r"\bQ\[(\d+)\]")
_A = re.compile(r"\bA\[(\d+)\]")
_OBJ = re.compile(r"\bOBJ\[(\d+)\]")
_LABEL_PERIOD = re.compile(r"\b(Question|Article|Reply|Objection)\.\s*")
_PART_TOKEN = re.compile(r"\b(FP|FS|SS|SP|TP|XP)\b")


def expand_apparatus(text: str) -> str:
    text = _BRACKET_STAR.sub("", text)
    text = _QQ_RANGE.sub(r"Qq. \1–\2", text)
    text = _CROSS_REF.sub(lambda m: f"{'Qq' if m[1] == 'QQ' else 'D'}. {m[2]}" if m[1]
                          else f"{m[3]} {m[4]}", text)
    text = _AA_PAIR.sub(r"Aa. \1, \2", text)
    text = _AA.sub(r"Aa. \1", text)
    text = _Q.sub(r"Q. \1", text)
    text = _A.sub(r"A. \1", text)
    text = _OBJ.sub(r"Objection \1", text)
    text = _LABEL_PERIOD.sub(r"\1 ", text)
    text = _PART_TOKEN.sub(lambda m: PART_NAMES[m.group(1)], text)
    return text
