"""Document facts (corpus-cleanup 2.3): each document's genre, issuer, date, translation,
source credit and notes, as the work registry holds them.

`derive` computes one document's facts from an adapter's build (before the registry's
facts are applied), its rights-inventory row and its works.json entry.
`scripts/document_facts_registry.py` writes them into `registry/works.json`, and the
build sets them on every Document (`registry.apply_document_facts`), so the registry
wins over the adapter. The stage writes them into `staging.documents` (2.2w), and they
reach live at the Phase 4 apply (D7).

The rules, from the spec and Carter's answers of 13 Nov 2026 (Decision log "Source
credits for document facts (2.3)"):

- `genre`: a papal document's `metadata["genre"]` (1.3b, `papal_genres.csv`); `catechism`
  and `code` for the Catechism and the Code; otherwise none.
- `issuer`, `issuer_label` (D11): the pope from `metadata["pope"]`; the council a council
  document comes from; the Holy See for the Catechism and the Code; otherwise none.
- `year`, `date_display`: the adapter's, with the corrections below.
- `source_credit`: the rights row's `credit_line`, exactly (0.2). A document that also
  holds texts from another edition names both (`COMBINED_CREDITS`). A document held for
  permission (an open `document` removal) shows nowhere and has none.
- `translation`: the edition or translator shown to users, empty where the credit line
  already names the translation ("Translated by …", "Translation from …"), so an opened
  passage does not say it twice (Carter's answer 7A).
- `notes`: the adapter's (an extract's omitted paragraphs, 1.3d; the Code's held canons).
- `attribution_note`, `superseded_by`, `superseded_note`: no rule sets them yet; a value
  already in the registry is kept (3.2, 5.4).
"""
from __future__ import annotations

import re

import identity
from model import Document

PAPAL_COLLECTIONS = ("encyclicals", "apostolic-exhortations", "papal-documents")
HOLY_SEE = ("holy-see", "Holy See")
VATICAN_CREDIT = "© Dicastery for Communication – Libreria Editrice Vaticana"

# A dating line the build's year disagrees with (C-05): the source's own date wins.
YEAR = {
    # Dated 27 April 1859, in the thirteenth year of Pius IX; the manifest says 1858.
    "encyclicals/cum-sancta-mater-ecclesia": 1859,
    # Written 1265 to 1274; the adapter sets no year.
    "summa": 1265,
}
DATE_DISPLAY = {"summa": "1265 to 1274"}

# One credit naming every edition a document holds (Carter's answer 5A). Each starts
# with the main row's credit line, which `test_document_facts` checks.
COMBINED_CREDITS = {
    "councils/ecum-03-council-of-ephesus":
        "Sourced via CCEL.org; Nestorius's second letter to Cyril translated by James "
        "Chrystal (1895)",
    "councils/ecum-07-second-council-of-nicaea":
        "Sourced via CCEL.org; the four anathemas concerning holy images from Hefele's "
        "History of the Councils, translated by William R. Clark (1896)",
    "councils/ecum-08-fourth-council-of-constantinople":
        "Translated by H. J. Schroeder (1937); five canons and an extract of canon 17 by "
        "Roy J. Deferrari (1957)",
    "councils/ecum-13-first-council-of-lyons":
        "Translated by H. J. Schroeder (1937); the bull deposing Frederick II and "
        "constitution I 7 by J. A. Giles (1853)",
    "councils/ecum-16-council-of-constance":
        "Translated by H. J. Schroeder (1937); the condemned articles of Wyclif and Hus and "
        "two extracts by Roy J. Deferrari (1957)",
    "councils/ecum-17-council-of-basel-ferrara-florence":
        "Translated by H. J. Schroeder (1937); the extracts of three decrees by Roy J. "
        "Deferrari (1957)",
    "councils/ecum-18-fifth-lateran-council":
        "Translated by H. J. Schroeder (1937); an extract of Pastor aeternus gregem by "
        "Roy J. Deferrari (1957)",
}

ANF = "Ante-Nicene Fathers (1885-1896)"
NPNF1 = "Nicene and Post-Nicene Fathers, Series I"
NPNF2 = "Nicene and Post-Nicene Fathers, Series II"
# The translation line by source file (the source key before `#`), where the adapter's
# own value is not the one shown.
TRANSLATION = {
    "church-fathers/apostolic fathers.xml": ANF,
    "church-fathers/second-century.xml": ANF,
    "church-fathers/third-century.xml": ANF,
    "church-fathers/third-century-2.xml": ANF,
    "church-fathers/third-century-3.xml": ANF,
    "church-fathers/third-fourth-century.xml": ANF,
    "church-fathers/city-of-god.xml": NPNF1,
    "church-fathers/on-the-holy-trinity.xml": NPNF1,
    "church-fathers/npnf204.xml": NPNF2,
    "church-fathers/confessions.xml": "E. B. Pusey (1838)",
    "medieval/consolation-of-philosophy.xml": "W. V. Cooper (1902)",
    "medieval/imitation-of-christ.xml": "Aloysius Croft and Harold Bolton (1940)",
    "summa": "Fathers of the English Dominican Province (1920)",
    "catechism": "United States edition (1997)",
}
# Anselm's three works share one file.
TRANSLATION_BY_KEY = {
    "medieval/proslogium-monologium-and-cur-deus-homo.xml#iii": "Sidney Norton Deane (1903)",
    "medieval/proslogium-monologium-and-cur-deus-homo.xml#iv": "Sidney Norton Deane (1903)",
    "medieval/proslogium-monologium-and-cur-deus-homo.xml#vi": "James Gardiner Vose (1854-1855)",
}
# Councils 1 to 7 come from Percival's volume of the Nicene and Post-Nicene Fathers.
_PERCIVAL = re.compile(r"^councils/ecum-0[1-7]-")
# A credit line that already says whose translation it is.
_NAMES_TRANSLATION = re.compile(r"^Translat(ed|ion)\b")

KEPT = ("attribution_note", "superseded_by", "superseded_note")


def credit_names_translation(credit: str | None) -> bool:
    return bool(credit and _NAMES_TRANSLATION.match(credit))


def issuer_slug(label: str) -> str:
    return identity.slugify(label)


def _issuer(document: Document) -> tuple[str | None, str | None]:
    meta = document.metadata or {}
    if document.collection in PAPAL_COLLECTIONS:
        pope = meta.get("pope")
        return (issuer_slug(pope), pope) if pope else (None, None)
    if document.collection == "councils":
        label = meta.get("council") or document.title
        return issuer_slug(label), label
    if document.collection in ("catechism", "canon-law"):
        return HOLY_SEE
    return None, None


def _genre(document: Document) -> str | None:
    if document.collection in PAPAL_COLLECTIONS:
        return (document.metadata or {}).get("genre")
    return {"catechism": "catechism", "canon-law": "code"}.get(document.collection)


def _translation(document: Document, key: str, credit: str | None) -> str:
    if credit_names_translation(credit):
        return ""
    if credit == VATICAN_CREDIT:
        return "Vatican English"
    if key in TRANSLATION_BY_KEY:
        return TRANSLATION_BY_KEY[key]
    if key.split("#")[0] in TRANSLATION:
        return TRANSLATION[key.split("#")[0]]
    if _PERCIVAL.match(key):
        return NPNF2
    return document.translation or ""


def source_credit(work_id: str, row: dict | None) -> str | None:
    if work_id in COMBINED_CREDITS:
        return COMBINED_CREDITS[work_id]
    return (row or {}).get("credit_line")


def derive(document: Document, row: dict | None, entry: dict) -> dict:
    """The facts of one built document (as the adapter built it), given its rights row
    and works.json entry, in `registry.FACT_FIELDS` order."""
    key = entry["source_key"]
    work_id = entry["work_id"]
    credit = source_credit(work_id, row)
    issuer, label = _issuer(document)
    facts = {
        "genre": _genre(document),
        "issuer": issuer,
        "issuer_label": label,
        "year": YEAR.get(work_id, document.year),
        "date_display": DATE_DISPLAY.get(work_id, document.date_display),
        "translation": _translation(document, key, credit),
        "source_credit": credit,
        "attribution_note": None,
        "notes": document.notes,
        "superseded_by": None,
        "superseded_note": None,
    }
    for k in KEPT:
        if entry.get(k) is not None:
            facts[k] = entry[k]
    return facts
