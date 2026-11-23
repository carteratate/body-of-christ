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
  and `code` for the Catechism and the Code; a Church Fathers work's from
  `FATHERS_GENRES` (3.2); otherwise none.
- `form`: how the papal chancery issued a papal document, `bull` or `brief`, from its
  `metadata["form"]` (1.3b, `papal_genres.csv`; issue #330); none where none is recorded,
  and for every other document.
- `issuer`, `issuer_label` (D11): the pope from `metadata["pope"]`; the council a council
  document comes from; the Holy See for the Catechism and the Code; otherwise none.
- `year`, `date_display`: the adapter's, with the corrections below, and the Church
  Fathers' from Quasten's Patrology (`FATHERS_DATES`, 3.2).
- `source_credit`: the rights row's `credit_line`, exactly (0.2). A document that also
  holds texts from another edition names both (`COMBINED_CREDITS`). A document held for
  permission (an open `document` removal) shows nowhere and has none.
- `translation`: the edition or translator shown to users, empty where the credit line
  already names the translation ("Translated by …", "Translation from …", "Official
  English version …"), so an opened passage does not say it twice (Carter's answer 7A).
  Only a credit naming just where the text came from (CCEL, eBible, the © line, "Text:",
  the USCCB notice) leaves the translation line.
- `notes`: the adapter's (an extract's omitted paragraphs, 1.3d; the Code's held canons;
  3.3's omitted Latin), or 3.2's (`attributions.DOCUMENTS`). A document given both fails.
- `attribution_note`: 3.2's (`attributions.DOCUMENTS`).
- `superseded_by`, `superseded_note`: no rule sets them yet; a value already in the
  registry is kept (5.4).
"""
from __future__ import annotations

import re

import attributions
import card_notes
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
    # Stromata III, which ANF left in Latin, in Chadwick's English (#399; Carter, 21 Nov
    # 2026).
    "church-fathers/second-century/vi.iv":
        "Sourced via CCEL.org; Book III translated by Henry Chadwick (1954)",
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

# The Church Fathers' dates and genres (3.2; Carter, 14 and 15 Nov 2026, Decision log
# "Dates and genres of the Fathers (2.3)"). Each date is the one J. Quasten's Patrology
# gives for the work (vol. II in English, Westminster 1953; vols. I to III in the Spanish
# edition, BAC); a work Quasten does not date has none. `year` is the sortable start,
# `date_display` what readers see. By works.json work_id: (year, date_display, where).
_CF = "church-fathers/"
FATHERS_DATES = {
    _CF + "apostolic-fathers/ii.ii": (96, "c. 96", "I, Clement of Rome"),
    _CF + "apostolic-fathers/iv.ii": (110, "c. 110 to 135",
                                      "I, Polycarp (Harrison's two letters)"),
    _CF + "apostolic-fathers/iv.iv": (156, "156", "I, Polycarp, The Martyrdom"),
    **{_CF + f"apostolic-fathers/v.{n}": (110, "c. 110", "I, Ignatius; Polycarp")
       for n in ("ii", "iii", "iv", "v", "vi", "vii", "viii")},
    _CF + "apostolic-fathers/vi.ii": (130, "c. 130 to 138", "I, The Epistle of Barnabas"),
    _CF + "apostolic-fathers/vii.ii": (130, "c. 130", "I, Papias"),
    _CF + "apostolic-fathers/viii.ii": (148, "148 to 161", "I, Justin, the Apologies"),
    _CF + "apostolic-fathers/viii.iii": (148, "148 to 161", "I, Justin, the Apologies"),
    _CF + "apostolic-fathers/viii.xi": (165, "c. 165", "I, Justin, his death"),
    _CF + "second-century/ii.ii": (140, "c. 140 to 150", "I, The Shepherd of Hermas"),
    _CF + "second-century/ii.iii": (140, "c. 140 to 150", "I, The Shepherd of Hermas"),
    _CF + "second-century/ii.iv": (140, "c. 140 to 150", "I, The Shepherd of Hermas"),
    _CF + "second-century/iv.ii": (180, "shortly after 180", "I, Theophilus"),
    _CF + "second-century/v.ii": (177, "c. 177", "I, Athenagoras, the Plea"),
    _CF + "third-fourth-century/viii.iii": (None, "1st century", "I, The Didache"),
    _CF + "third-century/iii.v": (200, "200 to 206", "II, Tertullian, To His Wife"),
    _CF + "third-century-2/iv.iv": (249, "249 to 258", "II, Cyprian, his episcopate"),
    _CF + "third-century-2/iv.v": (249, "249 to 257", "II, Cyprian, the treatises"),
    _CF + "third-century-2/iv.vi": (256, "256", "II, Cyprian, the synod of September 256"),
    _CF + "third-century-2/vii.iii": (253, "253 to 257", "II, Ad Novatianum"),
    _CF + "third-century-2/vii.iv": (256, "256 to 258", "II, De rebaptismate"),
    _CF + "third-century-3/v.v": (221, "c. 221", "II, Julius Africanus, the Chronicles"),
    _CF + "third-century-3/vi.x": (268, "268", "II, Paul of Samosata and Malchion"),
    _CF + "third-century-3/ix.iv": (306, "306", "II, Peter of Alexandria"),
    _CF + "third-century-3/vii.iii": (325, "c. 325 to 350", "II (Spanish), Hegemonius"),
    _CF + "third-century-3/vii.iv": (325, "c. 325 to 350", "II (Spanish), Hegemonius"),
    _CF + "third-century-3/x.iii": (324, "c. 324", "II (Spanish), Alexander of Alexandria"),
    _CF + "third-fourth-century/iii.ii": (304, "304 to 313", "II, Lactantius"),
    _CF + "third-fourth-century/iii.iii": (313, "313 to 314", "II, Lactantius"),
    _CF + "third-fourth-century/iii.iv": (303, "303 to 304", "II, Lactantius"),
    _CF + "incarnation": (318, "c. 318", "II (Spanish), Athanasius"),
    _CF + "city-of-god/iv": (413, "413 to 426", "III (Spanish), Augustine"),
    _CF + "city-of-god/v": (397, "397 to 427", "III (Spanish), Augustine"),
    _CF + "confessions": (397, "397 to 400", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv": (399, "399 to 420", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv.ii": (421, "c. 421", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv.iii": (400, "c. 400", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv.iv": (393, "393", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv.v": (399, "after 399", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/iv.vi": (391, "391", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.ii": (401, "c. 401", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.iii": (401, "c. 401", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.iv": (414, "c. 414", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.v": (395, "395", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.vi": (420, "420 to 421", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.vii": (401, "c. 401", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.viii": (415, "415", "III (Spanish), Augustine"),
    _CF + "on-the-holy-trinity/v.ix": (424, "424 to 425", "III (Spanish), Augustine"),
}
# Works inside a container, by (work_id, work_key), as FATHERS_DATES.
FATHERS_WORK_DATES = {
    (_CF + "third-century-2/iii.iv", "iii.iv.ii.i"): (200, "c. 200", "II, Hippolytus"),
    (_CF + "third-century-2/iii.iv", "iii.iv.i.x"): (204, "c. 204", "II, Hippolytus"),
    (_CF + "third-century-2/v.iii", "v.iii.iii"): (None, "late 2nd century",
                                                   "II, The Muratorian Fragment"),
}
# Genres from 2.1's writer genres (Carter, 15 Nov 2026): letters, treatises (apologies
# and dialogues too), commentaries, sermons, poems, manuals, law for church orders, and
# `other` for the Confessions, the Shepherd, martyr accounts, the council's acts and the
# chronicle. A volume of works of differing kinds, or of fragments of lost works of
# several kinds, has none.
_LETTER = ("apostolic-fathers/ii.ii", "apostolic-fathers/iii.ii", "apostolic-fathers/iv.ii",
           *(f"apostolic-fathers/v.{n}" for n in ("ii", "iii", "iv", "v", "vi", "vii",
                                                  "viii", "x", "xi", "xii")),
           "apostolic-fathers/vi.ii", "third-century-2/iv.iv", "third-century-3/v.iii",
           "third-century-3/ix.iv", "third-century-3/x.iii", "third-century-3/vi.vii",
           "third-century-3/vi.viii", "third-century-3/vi.x")
_TREATISE = ("apostolic-fathers/viii.ii", "apostolic-fathers/viii.iii",
             "apostolic-fathers/viii.iv", "apostolic-fathers/viii.v",
             "apostolic-fathers/viii.vi", "apostolic-fathers/viii.vii",
             "apostolic-fathers/viii.viii",
             *(f"apostolic-fathers/ix.{n}" for n in ("ii", "iii", "iv", "vi", "vii")),
             "second-century/iv.ii", "second-century/v.ii", "second-century/v.iii",
             "second-century/vi.ii", "second-century/vi.iii", "second-century/vi.iv",
             "third-century-2/iv.v", "third-century-2/iv.vii", "third-century-2/vii.iii",
             "third-century-2/vii.iv", "third-century-3/vii.iii", "third-century-3/vii.iv",
             "third-century-3/xi.iii", "third-century-3/xi.v", "third-century/iii.iii",
             "third-century/iii.v", "third-century/iv.iii", "third-fourth-century/iii.ii",
             "third-fourth-century/iii.iii", "third-fourth-century/iii.iv",
             "third-fourth-century/iii.v", "third-fourth-century/v.ii", "incarnation",
             "city-of-god/iv", "city-of-god/v", "on-the-holy-trinity/iv",
             *(f"on-the-holy-trinity/{k}" for k in ("iv.iii", "iv.iv", "iv.v", "iv.vi", "v",
                                                     "v.ii", "v.iii", "v.iv", "v.v", "v.vi",
                                                     "v.vii", "v.viii", "v.ix")))
FATHERS_GENRES = {
    **{_CF + k: "letter" for k in _LETTER},
    **{_CF + k: "treatise" for k in _TREATISE},
    **{_CF + k: "commentary" for k in ("third-fourth-century/vi.ii", "third-century-3/iv.iv")},
    **{_CF + k: "sermon" for k in ("on-the-holy-trinity/iv.vii", "third-century-3/xi.ix",
                                   "third-century-3/xi.x")},
    _CF + "third-century/v.ii": "poem",
    _CF + "third-fourth-century/iii.vi": "poem",
    _CF + "on-the-holy-trinity/iv.ii": "manual",
    _CF + "third-fourth-century/viii.iii": "manual",
    _CF + "third-fourth-century/ix.ix": "law",
    **{_CF + k: "other" for k in ("confessions", "second-century/ii.ii", "second-century/ii.iii",
                                  "second-century/ii.iv", "apostolic-fathers/iv.iv",
                                  "apostolic-fathers/v.xxv", "apostolic-fathers/viii.xi",
                                  "third-century-2/iv.vi", "third-century-3/v.v")},
}
# Works inside a container, by (work_id, work_key).
FATHERS_WORK_GENRES = {
    (_CF + "third-century-2/iii.iv", "iii.iv.ii.i"): "treatise",
    (_CF + "third-century-2/iii.iv", "iii.iv.i.x"): "commentary",
    (_CF + "third-century-2/iii.v", "iii.v.iv"): "law",
    (_CF + "third-century-2/iii.v", "iii.v.v"): "law",
    (_CF + "third-fourth-century/ix.ix", "ix.ix.vi"): "law",
    (_CF + "third-century-2/v.iii", "v.iii.iii"): "other",
    (_CF + "third-century-3/iii.iv", "iii.iv.v"): "sermon",
    (_CF + "third-century-3/iii.iv", "iii.iv.vi"): "sermon",
    (_CF + "third-century-3/iii.iii", "iii.iii.ii"): "commentary",
    (_CF + "third-century-3/iii.iii", "iii.iii.iii"): "letter",
}


# A work's date where it is not a Father's (4.4): the Summa's Supplement and its appendix
# were compiled after Aquinas died in 1274 (Carter, 20 Nov 2026), and their header says
# so in place of the Summa's "1265 to 1274".
WORK_DATES = {
    ("summa", "XP"): (None, "compiled after 1274", "Decision log, Supplement date (4.4)"),
    ("summa", "vii"): (None, "compiled after 1274", "Decision log, Supplement date (4.4)"),
}


def work_facts(work_id: str, work_key: str) -> dict:
    """A container work's date and genre (3.2, 4.4), for its works.json row."""
    year, display, _ = {**FATHERS_WORK_DATES, **WORK_DATES}.get(
        (work_id, work_key), (None, None, None))
    return {"year": year, "date_display": display,
            "genre": FATHERS_WORK_GENRES.get((work_id, work_key))}


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
# A credit line that names only where the text came from; every other one already says
# whose translation it is.
_SOURCE_ONLY = re.compile(r"^(Sourced via|Public domain\.|\u00a9 |Text: |Excerpts from )")

KEPT = ("superseded_by", "superseded_note")


def credit_names_translation(credit: str | None) -> bool:
    return bool(credit) and not _SOURCE_ONLY.match(credit)


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


def _genre(document: Document, work_id: str) -> str | None:
    if work_id in FATHERS_GENRES:
        return FATHERS_GENRES[work_id]
    if document.collection in PAPAL_COLLECTIONS:
        return (document.metadata or {}).get("genre")
    return {"catechism": "catechism", "canon-law": "code"}.get(document.collection)


def _form(document: Document) -> str | None:
    if document.collection in PAPAL_COLLECTIONS:
        return (document.metadata or {}).get("form")
    return None


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
        "genre": _genre(document, work_id),
        "form": _form(document),
        "issuer": issuer,
        "issuer_label": label,
        "year": YEAR.get(work_id, document.year),
        "date_display": DATE_DISPLAY.get(work_id, document.date_display),
        **({"year": FATHERS_DATES[work_id][0], "date_display": FATHERS_DATES[work_id][1]}
           if work_id in FATHERS_DATES else {}),
        "translation": _translation(document, key, credit),
        "source_credit": credit,
        "attribution_note": None,
        "notes": document.notes,
        "superseded_by": None,
        "superseded_note": None,
    }
    labels = attributions.DOCUMENTS.get(work_id, {})
    if labels.get("notes"):
        if facts["notes"]:
            raise ValueError(f"{work_id}: notes from the adapter and from 3.2's labels")
        facts["notes"] = labels["notes"]
    facts["attribution_note"] = labels.get("attribution_note")
    for k in KEPT:
        if entry.get(k) is not None:
            facts[k] = entry[k]
    return facts


def card_translator(facts: dict) -> str | None:
    """The translator the result card names (4.4), written once into works.json from the
    credit line or the translation (`card_notes.card_translator`), where the Library and
    the overview keep reading `translation` and `source_credit` as 2.3 set them."""
    return card_notes.card_translator(facts.get("source_credit"), facts.get("translation"))
