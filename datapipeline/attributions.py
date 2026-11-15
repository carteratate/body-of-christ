"""Labels, certainty and notes for works that stay (corpus-cleanup 3.2).

Rule H: a work is credited the way the Church's own texts cite it, then by the Clavis,
and a doubtful one carries a certainty label (genuine, disputed, pseudonymous,
anonymous). The wording was approved by Carter on 15 Nov 2026 (Decision log "Labels,
certainty and notes (3.2)"). `scripts/document_facts_registry.py` writes these into
`registry/works.json` from a build, and the build applies them
(`registry.apply_document_facts`), so the registry wins over the adapter. A document or
work the build no longer emits (3.1's removals) loses them on the rerun.

- `DOCUMENTS`, by works.json `work_id`: `credited_as` (the author shown, where it differs
  from the adapter's), `certainty`, `clavis`, `basis` (the research line it rests on),
  `attribution_note` (who wrote it) and `notes` (anything else, such as where fragments
  were preserved). The keys go to the entry's `attribution` and to its facts.
- `WORKS`, by (`work_id`, `work_key`): the same for a work inside a container (D6),
  written onto the entry's `works` row; `author` replaces the adapter's.
- `PASSAGE_NOTES`, by (`work_id`, chapter key): a note on every passage of one chapter,
  written onto the passage registry rows (`note`, one of the registry's overrides).
"""
from __future__ import annotations

MEMO = "docs/research/2026-09-28-rule-1-authorship-verification.md"
R1 = "docs/research/R1-rule-a-dating.md"
PLAN = "docs/2026-09-28-corpus-cleanup-plan.md"

_DOUBTFUL = "Its attribution to {} is doubtful."
_SMYRNA = ("A letter of the Church of Smyrna on Polycarp's death; its writer, Evarestus, is "
           "named in chapter XX.")
_REBAPTISM_COUNCIL = "Its ruling on rebaptizing heretics was not adopted by the Church."
_REBAPTISM_VIEW = "Its view on rebaptizing heretics was not adopted by the Church."
_COMPILED = "Compiled after Aquinas's death from his earlier writings."
_CATENAE = "catenae, medieval chains of comments on Scripture"
_LATER = "Preserved in quotations by later writers."

DOCUMENTS: dict[str, dict] = {
    # Pseudo-Justin (plan, "Labels for works that stay"; Decision log "Cohortatio").
    "church-fathers/apostolic-fathers/viii.vi": {
        "credited_as": "Pseudo-Justin", "certainty": "pseudonymous", "clavis": "CPG 1083",
        "attribution_note": "Not by Justin Martyr. Riedweg (1994) proposes Marcellus of "
                            "Ancyra, with a question mark.",
        "basis": f"{MEMO} §3, Cohortatio ad Graecos"},
    "church-fathers/apostolic-fathers/viii.vii": {
        "credited_as": "Pseudo-Justin", "certainty": "pseudonymous", "clavis": "CPG 1084",
        "attribution_note": "Not by Justin Martyr; date uncertain.",
        "basis": f"{MEMO} §3, De monarchia"},
    "church-fathers/apostolic-fathers/viii.v": {
        "credited_as": "Pseudo-Justin", "certainty": "pseudonymous", "clavis": "CPG 1082",
        "attribution_note": "Not by Justin Martyr.",
        "basis": f"{MEMO} §3, Oratio ad Graecos"},
    "church-fathers/apostolic-fathers/viii.viii": {
        "certainty": "disputed", "clavis": "CPG 1081",
        "attribution_note": "Authorship disputed; Heimgartner (2001) assigns it to "
                            "Athenagoras.",
        "notes": "Preserved in the Sacra Parallela, a collection of quotations attributed "
                 "to John of Damascus.",
        "basis": f"{MEMO} §3, De resurrectione"},
    # Anonymous works (plan, "Labels"; Decision log "Unknown authors").
    "church-fathers/third-fourth-century/viii.iii": {
        "credited_as": "Anonymous", "certainty": "anonymous",
        "basis": f"{PLAN}, Labels for works that stay (the Didache)"},
    "church-fathers/apostolic-fathers/iii.ii": {
        "credited_as": "Anonymous", "certainty": "anonymous", "clavis": "CPG 1112",
        "basis": f"{MEMO} §10, Epistle to Diognetus"},
    "church-fathers/apostolic-fathers/vi.ii": {
        "credited_as": "Pseudo-Barnabas", "certainty": "pseudonymous",
        "basis": f"{PLAN}, Labels for works that stay"},
    # Hegemonius (Photius, Library, codex 85).
    "church-fathers/third-century-3/vii.iii": {
        "credited_as": "Hegemonius", "certainty": "genuine",
        "attribution_note": "Written by Hegemonius; Archelaus is the bishop who debates "
                            "Mani in it.",
        "basis": f"{MEMO} §10, Acts of Archelaus"},
    "church-fathers/third-century-3/vii.iv": {
        "credited_as": "Hegemonius", "certainty": "genuine",
        "attribution_note": "Written by Hegemonius; Archelaus is the bishop who debates "
                            "Mani in it.",
        "notes": "Preserved in Cyril of Jerusalem's Catechetical Lectures.",
        "basis": f"{MEMO} §10, Acts of Archelaus"},
    # Doubtful works (plan, "Labels"; the ANF editors' judgments in works.json agree).
    "church-fathers/third-century-3/xi.ix": {
        "certainty": "disputed", "attribution_note": _DOUBTFUL.format("Methodius"),
        "basis": f"{PLAN}, Labels for works that stay"},
    "church-fathers/third-century-3/xi.x": {
        "certainty": "disputed", "attribution_note": _DOUBTFUL.format("Methodius"),
        "notes": _LATER, "basis": f"{PLAN}, Labels for works that stay"},
    "church-fathers/third-century-3/vi.ix": {
        "certainty": "disputed", "attribution_note": _DOUBTFUL.format("Pamphilus"),
        "basis": f"{PLAN}, Labels for works that stay"},
    # Notes on works that stay as credited (plan, "Labels"; D10).
    "church-fathers/apostolic-fathers/v.xxv": {
        "attribution_note": "A legendary account.",
        "basis": f"{PLAN}, Labels for works that stay; D10"},
    "church-fathers/third-century-2/iv.vi": {
        "certainty": "genuine", "notes": _REBAPTISM_COUNCIL,
        "basis": f"{PLAN}, Labels for works that stay"},
    "church-fathers/third-fourth-century/vi.ii": {
        "credited_as": "Victorinus of Pettau", "certainty": "genuine",
        "attribution_note": "This is Jerome's revision of the commentary: he replaced "
                            "Victorinus's comments on the thousand-year reign (Revelation "
                            "20 to 22) with his own.",
        "basis": f"{MEMO} §8, Victorinus of Pettau; the text's chapter 20 is the "
                 "non-millenarian reading Jerome substituted"},
    # Martyrdoms (C-15).
    "church-fathers/apostolic-fathers/iv.iv": {
        "credited_as": "Church of Smyrna", "certainty": "genuine", "attribution_note": _SMYRNA,
        "basis": "The Martyrdom of Polycarp, chapter XX (C-15)"},
    "church-fathers/apostolic-fathers/viii.xi": {
        "credited_as": "Anonymous", "certainty": "anonymous",
        "attribution_note": "An account of the trial and death of Justin and his "
                            "companions; its author is unknown.",
        "basis": "The ANF editor's notice on the Martyrdom of Justin (C-15)"},
    # Fragment collections: where the fragments were preserved (Decision log "Fragment
    # collections (3.2)", 9 Oct 2026), from the ANF editors' source notes.
    "church-fathers/apostolic-fathers/vii.ii": {
        "notes": "Preserved in quotations by later writers, chiefly Irenaeus (Against "
                 "Heresies) and Eusebius (Church History).",
        "basis": "ANF 1, Fragments of Papias, the editor's source notes"},
    "church-fathers/apostolic-fathers/viii.ix": {
        "notes": "Preserved in quotations by later writers, among them Tatian, Irenaeus, "
                 "Methodius and the Sacra Parallela attributed to John of Damascus.",
        "basis": "ANF 1, Other Fragments of Justin, the editor's source notes"},
    "church-fathers/apostolic-fathers/ix.viii": {
        "notes": f"Preserved chiefly in Eusebius (Church History) and in {_CATENAE}.",
        "basis": "ANF 1, Fragments of Irenaeus, the editor's source notes"},
    "church-fathers/third-century-2/v.iii": {
        "notes": "Preserved in Eusebius, Church History.",
        "basis": "ANF 5, Fragments of Caius, the editor's source notes"},
    "church-fathers/third-century-3/iv.iii": {
        "notes": "Preserved chiefly in Eusebius (Church History and Preparation for the "
                 "Gospel) and Athanasius.",
        "basis": "ANF 6, Dionysius, Extant Fragments, the editor's source notes"},
    "church-fathers/third-century-3/iv.iv": {
        "notes": f"Preserved in {_CATENAE}.",
        "basis": "ANF 6, Dionysius, Exegetical Fragments, the editor's source notes"},
    "church-fathers/third-century-3/v.v": {
        "notes": "Preserved chiefly in George Syncellus's Chronography and in Eusebius.",
        "basis": "ANF 6, Julius Africanus, Chronography, the editor's source notes"},
    "church-fathers/third-century-3/xi.v": {
        "notes": "Preserved chiefly in Photius's Library and Epiphanius's Panarion.",
        "basis": "ANF 6, Methodius, Discourse on the Resurrection, the editor's notes"},
    "church-fathers/third-century-3/xi.vi": {
        "notes": "Preserved in Photius's Library and other later collections.",
        "basis": "ANF 6, Fragments of Methodius, the editor's source notes"},
    "church-fathers/third-century-3/xi.xi": {
        "notes": "Preserved in catenae and the Sacra Parallela.",
        "basis": "ANF 6, Some Other Fragments of Methodius, the editor's source notes"},
    "church-fathers/third-century-3/xi.xii": {
        "notes": _LATER, "basis": "ANF 6, Two Fragments, Uncertain, the editor's notes"},
    "church-fathers/third-century-3/ix.vi": {
        "notes": _LATER, "basis": "ANF 6, Fragments of Peter, the editor's source notes"},
}

# Letters by others in Cyprian's Epistles (C-02): 1.8c credits each to its sender and
# titles it; 3.2 marks them genuine. Epistles XXV and XXIX leave under 3.1, XXX too.
_CYPRIAN_SENDERS = ("iv.iv.ii", "iv.iv.xvi", "iv.iv.xviii", "iv.iv.xx", "iv.iv.xxi",
                    "iv.iv.xxxviii", "iv.iv.xlv", "iv.iv.xlvii", "iv.iv.xlix",
                    "iv.iv.lxxiv", "iv.iv.lxxvii", "iv.iv.lxxviii", "iv.iv.lxxix")
_EPISTLES = "church-fathers/third-century-2/iv.iv"
_GREGORY_DUBIOUS = "church-fathers/third-century-3/iii.iv"
_HIPPOLYTUS_APPENDIX = "church-fathers/third-century-2/iii.v"
_PSEUDO_GREGORY = {"author": "Pseudo-Gregory Thaumaturgus", "certainty": "pseudonymous"}
_PSEUDO_HIPPOLYTUS = {"author": "Pseudo-Hippolytus", "certainty": "pseudonymous",
                      "basis": f"{PLAN}, Labels for works that stay; {R1} §2, Hippolytus"}

WORKS: dict[tuple[str, str], dict] = {
    (_GREGORY_DUBIOUS, "iii.iv.iii"): {
        **_PSEUDO_GREGORY, "clavis_ref": "CPG 1772",
        "attribution_note": "Not by Gregory Thaumaturgus.", "basis": f"{MEMO} §4"},
    (_GREGORY_DUBIOUS, "iii.iv.iv"): {
        "author": "Gregory Thaumaturgus", "certainty": "disputed", "clavis_ref": "CPG 1773",
        "basis": f"{MEMO} §4"},
    (_GREGORY_DUBIOUS, "iii.iv.v"): {
        **_PSEUDO_GREGORY, "clavis_ref": "CPG 1775–1776", "basis": f"{MEMO} §4"},
    (_GREGORY_DUBIOUS, "iii.iv.vi"): {
        **_PSEUDO_GREGORY, "clavis_ref": "CPG 1777", "basis": f"{MEMO} §4"},
    # Not in the plan; printed among the dubious writings (Carter, 15 Nov 2026).
    (_GREGORY_DUBIOUS, "iii.iv.ii"): {
        "author": "Gregory Thaumaturgus", "certainty": "disputed", "clavis_ref": "CPG 1787",
        "basis": f"{MEMO} §4"},
    (_GREGORY_DUBIOUS, "iii.iv.vii"): {
        "author": "Gregory Thaumaturgus", "certainty": "disputed",
        "basis": "ANF 6 prints it among the Dubious or Spurious Writings"},
    (_HIPPOLYTUS_APPENDIX, "iii.v.i"): {
        **_PSEUDO_HIPPOLYTUS,
        "basis": _PSEUDO_HIPPOLYTUS["basis"] + "; 7th century (A. Whealey, Byzantion 66, "
                                               "1996), so rule C keeps it"},
    # The lists of the Twelve and the Seventy Apostles (iii.v.ii, iii.v.iii) leave under
    # rule C, rm-7001 to rm-7003 (Carter, 15 Nov 2026).
    (_HIPPOLYTUS_APPENDIX, "iii.v.iv"): {
        "author": "Anonymous", "certainty": "anonymous", "clavis_ref": "CPG 1742",
        "attribution_note": "An Egyptian church order, about 336 to 340.",
        "basis": f"{MEMO} §10, Canons of Hippolytus"},
    (_HIPPOLYTUS_APPENDIX, "iii.v.v"): {
        "author": "Anonymous", "certainty": "anonymous",
        "basis": "A church order; its title says it was wrongly ascribed to Hippolytus"},
    # An editor's judgment rule G removed, kept as a note (plan rule G; Carter, 15 Nov
    # 2026). The plan overrides the others 1.8a copied (works.json editorial_judgments).
    ("church-fathers/third-century-3/iii.iii", "iii.iii.iii"): {
        "notes": "The eleventh canon is a later addition.",
        "basis": "ANF 6, the editor's elucidation: a genuine epistle, all but the eleventh "
                 "canon"},
    ("church-fathers/third-century-2/iv.vii", "iv.vii.iii"): {
        "author": "Anonymous", "certainty": "anonymous",
        "basis": f"{PLAN}, Decision log, Cyprian's two anonymous treatises kept as "
                 "anonymous"},
    ("church-fathers/third-century-2/iv.vii", "iv.vii.v"): {
        "author": "Anonymous", "certainty": "anonymous",
        "basis": f"{PLAN}, Decision log, Cyprian's two anonymous treatises kept as "
                 "anonymous"},
    ("church-fathers/third-century-2/v.iii", "v.iii.iii"): {
        "author": "Anonymous", "certainty": "anonymous",
        "attribution_note": "Its author is unknown; the editors printed it with Caius's "
                            "fragments on one scholar's guess.",
        "basis": f"{MEMO} §10, Muratorian author"},
    ("church-fathers/third-fourth-century/iii.vi", "iii.vi.ii"): {
        "author": "Lactantius", "certainty": "disputed",
        "attribution_note": _DOUBTFUL.format("Lactantius"),
        "basis": f"{PLAN}, Labels for works that stay"},
    # A received work under rule D (D10), not "Anonymous".
    ("church-fathers/third-fourth-century/ix.ix", "ix.ix.vi"): {
        "author": "Attributed to the Apostles", "certainty": "pseudonymous",
        "attribution_note": "Compiled about 380. The Latin West received canons 1 to 50 "
                            "through Dionysius Exiguus; all 85 were confirmed by the "
                            "Council in Trullo (canon 2) and Nicaea II (canon 1).",
        "basis": f"{PLAN}, Decision log, Apostolic Canons; D10; {MEMO} §5, §6"},
    ("summa", "XP"): {"author": "Thomas Aquinas", "certainty": "genuine",
                      "attribution_note": _COMPILED,
                      "basis": f"{PLAN}, Labels for works that stay"},
    ("summa", "vii"): {"author": "Thomas Aquinas", "certainty": "genuine",
                       "attribution_note": _COMPILED,
                       "basis": f"{PLAN}, Labels for works that stay"},
    **{(_EPISTLES, key): {"certainty": "genuine",
                          "basis": "1.8c's sender, from the letter's title line and greeting"}
       for key in _CYPRIAN_SENDERS},
}
WORKS[(_EPISTLES, "iv.iv.lxxiv")]["notes"] = _REBAPTISM_VIEW

PASSAGE_NOTES: dict[tuple[str, str], str] = {
    ("church-fathers/apostolic-fathers/iii.ii", key):
        "Chapters 11 and 12 are a later addition by another hand."
    for key in ("iii.ii.xi", "iii.ii.xii")
}

# Fields the registry's `attribution` object takes from DOCUMENTS; the rest are facts.
ATTRIBUTION_KEYS = ("credited_as", "certainty", "clavis", "basis")
# Fields of a works.json `works` row this module sets (model.Work's label fields).
WORK_LABEL_KEYS = ("author", "certainty", "attribution_note", "notes", "clavis_ref")
