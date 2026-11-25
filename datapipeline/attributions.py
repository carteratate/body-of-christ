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
    # On Loving God: the translation credit is 1.9's and 2.3's (R5); 3.2's table marks
    # the attribution genuine.
    "medieval/on-loving-god": {
        "certainty": "genuine",
        "basis": f"{PLAN}, Decision log, On Loving God translation; docs/research/"
                 "R5-on-loving-god.md"},
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
    # Its note sits on canon XI alone (PASSAGE_NOTES), the passage it is true of (4.4).
    ("church-fathers/third-century-3/iii.iii", "iii.iii.iii"): {
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
        # Empty, not null: a work's null field falls back to its document's, and Caius's
        # "Preserved in Eusebius" does not hold for the Fragment.
        "notes": "",
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
    # Their header says "compiled after 1274" (`document_facts.WORK_DATES`), so the note
    # 3.2 gave them goes (4.4, Carter, 20 Nov 2026).
    ("summa", "XP"): {"author": "Thomas Aquinas", "certainty": "genuine",
                      "basis": f"{PLAN}, Labels for works that stay"},
    ("summa", "vii"): {"author": "Thomas Aquinas", "certainty": "genuine",
                       "basis": f"{PLAN}, Labels for works that stay"},
    **{(_EPISTLES, key): {"certainty": "genuine",
                          "basis": "1.8c's sender, from the letter's title line and greeting"}
       for key in _CYPRIAN_SENDERS},
}
WORKS[(_EPISTLES, "iv.iv.lxxiv")]["notes"] = _REBAPTISM_VIEW

# --------------------------------------------------------------------------- 5.6a: Basil

# NPNF2-08 (5.6a, #205). Rule H's sources for Basil's letters, read for 5.6a: Quasten's
# Patrology in its Spanish edition, vol. II (BAC 1978; English vol. III), pp. 244-249, and
# P. J. Fedwick's list of Basil's works with its Dubia and Spuria ("The Works of Basil of
# Caesarea", in Fedwick, ed., Basil of Caesarea: Christian, Humanist, Ascetic, Toronto
# 1981, which follows the Clavis, CPG 2900). The research and each letter's line are in
# R1's 5.6a addendum.
R1_BASIL = f"{R1}, 5.6a addendum (Basil)"
QUASTEN_BASIL = "Quasten, Patrología II (BAC 1978), pp. 244-249"
FEDWICK = "Fedwick (1981), The Works of Basil of Caesarea, Spuria"
_BASIL_LETTERS = "church-fathers/npnf208/ix"
for _work_id, _clavis in (("church-fathers/npnf208/vii", "CPG 2839"),
                          ("church-fathers/npnf208/viii", "CPG 2835"),
                          (_BASIL_LETTERS, "CPG 2900")):
    DOCUMENTS[_work_id] = {"certainty": "genuine", "clavis": _clavis, "basis": R1_BASIL}
_NOT_BASIL = "Transmitted among Basil's letters, but not his."
_NYSSA = "Transmitted among Basil's letters; scholars now assign it to Gregory of Nyssa."
_NAZIANZUS = ("Transmitted among Basil's letters; Fedwick (1981) assigns it to Gregory of "
              "Nazianzus.")
# By the letter's div in NPNF2-08 (Letter N is not div N: the volume skips and merges some).
BASIL_LETTER_LABELS = {
    # Letter 8, to the Caesareans: Evagrius Ponticus's (Bousset, Melcher; Quasten; Fedwick,
    # Spuria). It stays, labelled as his, by Carter's decision of 24 Nov 2026 (Decision log
    # "Basil's Letter 8 (5.6a)"), though rule A, limit 1 would leave it out.
    "ix.ix": {"author": "Evagrius Ponticus", "certainty": "disputed",
              "attribution_note": "Scholars now give this letter to Evagrius Ponticus, whose "
                                  "teachings the Second Council of Nicaea condemned.",
              "basis": f"{QUASTEN_BASIL} (Bousset, Melcher); {FEDWICK}; Decision log, "
                       "Basil's Letter 8 (5.6a)"},
    # Gregory of Nyssa: Letters 10, 16, 38 and 189.
    "ix.xi": {"author": "Gregory of Nyssa", "certainty": "disputed",
              "attribution_note": _NYSSA,
              "basis": f"{QUASTEN_BASIL} (Pasquali); {FEDWICK}"},
    "ix.xvii": {"author": "Gregory of Nyssa", "certainty": "genuine",
                "attribution_note": "An extract from Gregory of Nyssa's Against Eunomius, "
                                    "transmitted among Basil's letters.",
                "basis": f"{QUASTEN_BASIL}; {FEDWICK}"},
    "ix.xxxix": {"author": "Gregory of Nyssa", "certainty": "disputed", "clavis_ref": "CPG 3196",
                 "attribution_note": _NYSSA, "basis": f"{QUASTEN_BASIL}; {FEDWICK}"},
    "ix.cxc": {"author": "Gregory of Nyssa", "certainty": "disputed",
               "attribution_note": _NYSSA, "basis": f"{QUASTEN_BASIL}; {FEDWICK}"},
    # Gregory of Nazianzus: Letters 47 and 169 to 171 (166 and 321 print no text; 167, his
    # Letter 66, is retired as a duplicate of his own copy in NPNF2-07).
    "ix.xlviii": {"author": "Gregory of Nazianzus", "certainty": "disputed",
                  "attribution_note": "Transmitted among Basil's letters, but written about "
                                      "him; the Benedictine editors give it to Gregory of "
                                      "Nazianzus's father, written in his son's hand.",
                  "basis": f"{FEDWICK} (compares Gregory of Nazianzus, Letter 42); "
                           "NPNF2-08's note on Letter 47"},
    **{div: {"author": "Gregory of Nazianzus", "certainty": "disputed",
             "attribution_note": _NAZIANZUS, "basis": FEDWICK}
       for div in ("ix.clxx", "ix.clxxi", "ix.clxxii")},
    # Basil's own letters to Libanius: Quasten counts 335 to 346 authentic, Fedwick lists
    # these among the Dubia (342 among the Spuria). Limit 2 passes them as a Doctor's.
    **{div: {"author": "Basil", "certainty": "disputed",
             "attribution_note": _DOUBTFUL.format("Basil"),
             "basis": f"{QUASTEN_BASIL}; Fedwick (1981), Dubia and Spuria"}
       for div in ("ix.cccxxx", "ix.cccxxxii", "ix.cccxxxiv", "ix.cccxxxvii", "ix.cccxxxix")},
    # Letter 187, the governor Antipater's reply to Letter 186, by its title line, as
    # 1.8c credits Cyprian's correspondents. No source records him as other than a
    # Christian, so rule A presumes him in communion.
    "ix.clxxxviii": {"author": "Antipater", "certainty": "genuine",
                     "basis": "NPNF2-08's title line, \"Antipater to Basil\""},
    # Pseudo-Basil: spurious letters whose writer no source names a heretic (rule B keeps
    # them, labelled).
    **{div: {"author": "Pseudo-Basil", "certainty": "pseudonymous",
             "attribution_note": _NOT_BASIL, "basis": f"{QUASTEN_BASIL}; {FEDWICK}"}
       for div in ("ix.xlii", "ix.xliii", "ix.xliv", "ix.xlv", "ix.xlvi", "ix.li",
                   "ix.lxxxii", "ix.ccclvii")},
    # The Libanius letters Fedwick lists as spurious; Quasten calls the letters after 346
    # but 358 "spurious, or at least doubtful".
    **{div: {"author": "Pseudo-Basil", "certainty": "pseudonymous",
             "attribution_note": _NOT_BASIL, "basis": f"{FEDWICK}; {QUASTEN_BASIL}"}
       for div in ("ix.cccxliii", "ix.cccxlv", "ix.cccxlvi", "ix.cccxlviii", "ix.cccli",
                   "ix.cccliv")},
    # Letter 197's second section, on Dionysius's relics (`_LETTER_PARTS`).
    "ix.cxcviii/2": {"author": "Pseudo-Basil", "certainty": "pseudonymous",
                     "attribution_note": "A later addition to Basil's letter to Ambrose.",
                     "basis": f"{QUASTEN_BASIL} (Cavallin 1945); {FEDWICK}"},
    # Letter 360, on images: spurious, but quoted by the Second Council of Nicaea, so a
    # received work that stays under rule D.
    "ix.ccclv": {"author": "Pseudo-Basil", "certainty": "pseudonymous",
                 "attribution_note": "Not by Basil. The Second Council of Nicaea (787) "
                                     "quoted it as his.",
                 "basis": f"{QUASTEN_BASIL}; {FEDWICK}; rule D (quoted in Nicaea II, act "
                          "4)"},
}
WORKS.update({(_BASIL_LETTERS, div): labels for div, labels in BASIL_LETTER_LABELS.items()})
# ---------------------------------------------------------- 5.6a: Cyril and Gregory

# NPNF2-07 (5.6a, #205). Both are Doctors; the volume prints only their own works. The
# Mystagogical Lectures' authorship is disputed (Quasten, Patrología II, pp. 404-407: one
# manuscript gives them to Cyril's successor John and three to Cyril and John; the evidence
# decides nothing); the
# Catechism cites them as Cyril's ("St. Cyril of Jerusalem, Catech. myst."), so rule H
# credits him and the certainty says the rest.
R1_NPNF207 = f"{R1}, 5.6a addendum (Cyril and Gregory of Nazianzus)"
for _work_id in ("church-fathers/npnf207/ii", "church-fathers/npnf207/iii",
                 "church-fathers/npnf207/iv"):
    DOCUMENTS[_work_id] = {"certainty": "genuine", "basis": R1_NPNF207}
WORKS[("church-fathers/npnf207/ii", "ii.iv")] = {
    "author": "Cyril of Jerusalem", "certainty": "genuine", "basis": R1_NPNF207}
WORKS[("church-fathers/npnf207/ii", "ii.xxiii")] = {
    "author": "Cyril of Jerusalem", "certainty": "disputed",
    "attribution_note": "Some manuscripts give these lectures to Cyril's successor, John of "
                        "Jerusalem; the Catechism cites them as Cyril's.",
    "basis": f"Quasten, Patrología II (BAC 1978), pp. 404-407; CCC, footnotes citing "
             f"\"Catech. myst.\"; {R1_NPNF207}"}

# ---------------------------------------------------------- 5.6a: Leo and Gregory the Great

# NPNF2-12 and NPNF2-13 (5.6a, #205). Both are Doctors. The letters to them that their
# collections keep are credited to their senders in the build (`_NPNF_SENDERS`); Barmby's
# notes judge four of Gregory's Register doubtful or spurious, labelled here.
R1_LEO_GREGORY = f"{R1}, 5.6a addendum (Leo and Gregory the Great)"
for _work_id, _clavis in (("church-fathers/npnf212/ii.iv", "CPL 1656"),
                          ("church-fathers/npnf212/ii.v", "CPL 1657"),
                          ("church-fathers/npnf212/iii.iv", "CPL 1712"),
                          ("church-fathers/npnf212/iii.v", "CPL 1714"),
                          ("church-fathers/npnf213/ii", "CPL 1714")):
    DOCUMENTS[_work_id] = {"certainty": "genuine", "clavis": _clavis, "basis": R1_LEO_GREGORY}
_BARMBY = "Barmby, NPNF2-13, note to the letter"
_AUTUN = ("Its genuineness, or at least its freedom from later additions, is disputed; the "
          "Benedictine editors defend it.")
WORKS.update({
    # Book IX, 61: Recared's letter, which may be a forgery built on Gregory's to him (IX, 122).
    ("church-fathers/npnf213/ii", "ii.v.xxx"): {
        "author": "Recared", "certainty": "disputed",
        "attribution_note": "Its genuineness is doubted: it may be a forgery based on "
                            "Gregory's letter to Recared.",
        "basis": _BARMBY},
    # Book XIII, 8 and 9: privileges for Queen Brunhild's foundations at Autun.
    **{("church-fathers/npnf213/ii", div): {
        "author": "Gregory the Great", "certainty": "disputed", "attribution_note": _AUTUN,
        "basis": f"{_BARMBY} (Book XIII, 10, on all three)"}
       for div in ("ii.ix.v", "ii.ix.vi")},
    # Book XIV, 17: the reply to Felix of Messana, which Jaffé lists among the spurious.
    ("church-fathers/npnf213/ii", "ii.x.viii"): {
        "author": "Pseudo-Gregory the Great", "certainty": "pseudonymous",
        "attribution_note": "Not by Gregory: an imitation of his style, judged spurious.",
        "basis": f"{_BARMBY}; Jaffé, Regesta Pontificum Romanorum, spuria"},
})

# The Creed of Nicaea Letter 125 quotes in Greek is cut under rule E
# (`ingest.church_fathers.NOT_ENGLISH`).
_CREED_NOTE = ("The Creed of Nicaea, which this letter quotes in full, is omitted: the "
               "translator left it in Greek.")

PASSAGE_NOTES: dict[tuple[str, str], str] = {
    **{("church-fathers/apostolic-fathers/iii.ii", key):
       "Chapters 11 and 12 are a later addition by another hand."
       for key in ("iii.ii.xi", "iii.ii.xii")},
    # The Canonical Epistle's eleventh canon (ANF 6's elucidation; 3.2, moved by 4.4).
    ("church-fathers/third-century-3/iii.iii", "iii.iii.iii.xi"):
        "This canon is a later addition.",
    (_BASIL_LETTERS, "ix.cxxvi"): _CREED_NOTE,
}

# Fields the registry's `attribution` object takes from DOCUMENTS; the rest are facts.
ATTRIBUTION_KEYS = ("credited_as", "certainty", "clavis", "basis")
# Fields of a works.json `works` row this module sets (model.Work's label fields).
WORK_LABEL_KEYS = ("author", "certainty", "attribution_note", "notes", "clavis_ref")
