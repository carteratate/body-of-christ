# Supplemental corpus review by sol

6 October 2026. Fresh agent review, following Carter's request for additional defects. The completed Sol report is the exclusion baseline. I have not opened or searched the other reviewer's report or scratch folder. The original report is unchanged. Scratch is confined to `datapipeline/releases/local/review-sol-followup/`.

## Summary

This fresh pass adds five verified findings covering 193 distinct live passages and 193 build passages, all outside the original Sol report's passage set. Two findings are critical, two high and one medium. The cleanup specifications need expansion: 27 martyrdom passages name the martyr as author; four Summa passages mix a counterargument into an objection; three more Summa articles lack their entire counterargument; 100 canons display the wrong chapter number; and 39 Summa pieces hide replies to additional argument targets.

The affected passages have 13 saved search-result rows, all in canon law. They have no bookmarks, guest results or relevance labels, and no saved reading position targets one of their chapters or anchors. Counts do not reveal distinct users. A saved search-result row is one retained occurrence of a passage in search history.

The 193 count includes 23 existing pieces in three articles whose missing argument has no passage ID. It measures incomplete articles, not 23 false paragraph bodies. The findings are disjoint from one another and from A-001 to A-019. Two prose-reply pieces have different build IDs/anchors under the already-known positional-ID problem; the evidence preserves both identities.

The proposed cleanup is not sufficient as currently specified. This supplement completes its bounded additional checks, but does not certify that every remaining source sentence or historical embedding is correct. Independent Supplement collation and the rest of the core Summa discrepancy review remain unfinished.

| Finding | Severity | Live/build passages | Saved search results |
|---|---|---:|---:|
| B-001: contrary arguments inside objections | critical | 4 / 4 | 0 |
| B-004: martyrdom authors | critical | 27 / 27 | 0 |
| B-002: three omitted counterarguments | high | 23 / 23 | 0 |
| B-003: contiguous canon groups with wrong chapter numbers | high | 100 / 100 | 13 |
| B-005: merged prose replies with different targets | medium | 39 / 39 | 0 |


## Findings

### B-001. Four contrary arguments are merged into the objections they refute

Severity: critical. Status: new cause beyond A-015/A-016, not specified by 1.7. Owner: extend 1.7's reviewed role ledger. Collection: Summa. Four passages in live and four in the build, with zero saved retrieval, bookmark, guest-result or relevance-label rows.

The source introduces a sed contra, the argument against the objections, with "The contrary, however" instead of the standard "On the contrary". Its paragraph has no bold marker. Both the current regular expression and the proposed bold-paragraph walk append it to Objection 3. These are four actual mixed-role passages, distinct from A-016's future regression for an unbold standard marker. They are I-II q.46 a.7, II-II q.56 a.1, II-II q.56 a.2 and II-II q.140 a.2.

I read all four stored passages, source paragraphs and corresponding independent Latin units. Examples: `929cd2d6-2451-5e08-9b69-30de83d9a28f`, I-II q.46 a.7, anchor ending `/article-7-whether-anger-is-only-towards-those-to-whom-one-has-an-obligation-of-justice/2`; `4b2ae941-3e1d-5fb3-bfc7-25bce8d3c439`, II-II q.56 a.1, ending `/article-1-whether-the-precepts-of-the-decalogue-should-have-included-a-precept-of-prudence/2`; and `c2254c93-3c04-5199-bccc-8c9d5908ada4`, II-II q.56 a.2, ending `/article-2-whether-the-prohibitive-precepts-relating-to-the-vices-opposed-to-prudence-are-fittingly-propounded-in-the-old-law/2`. The fourth is `3c401699-a9e5-5688-b87c-c1de75f4c5c9`, II-II q.140 a.2, `/2`. Their current `unit_label` is `Objection 3`. Complete anchors and references are in `live-summa-opponent-sed-contra.json`.

The reader and the models receive Aquinas's counterargument inside text labeled as an objection Aquinas refutes. A reply attachment includes that counterargument as part of its target objection. This is an input error, not a claim that a paid explanation experiment failed. Separate each source paragraph into its proper sed-contra unit through reviewed source corrections. Future check: `roles.summa.variant-sed-contra-boundaries`, inventorying every independently attested sed contra and ensuring it is neither absent nor included in an objection's content. Reproduce `summa-additional.py`; independent evidence includes Corpus Thomisticum's Latin units [35512](https://www.corpusthomisticum.org/sth2040.html#35512), [41370](https://www.corpusthomisticum.org/sth3047.html#41370), [41378](https://www.corpusthomisticum.org/sth3047.html#41378) and [44607](https://www.corpusthomisticum.org/sth3123.html#44607).

### B-004. Two martyrdom narratives credit their dead subjects as authors

Severity: critical. Status: new, omitted from 1.8c and 3.2's author correction tables. Owner: extend 1.8c/3.2. Collection: church-fathers. Twenty-seven live and 27 build passages: 22 in The Martyrdom of Polycarp and five in The Martyrdom of Justin Martyr. No saved retrieval, bookmark, guest-result or relevance-label rows.

Every passage in these two documents names the martyr as the author. The source explicitly identifies the Polycarp narrative as an encyclical from the Church of Smyrna, with its writer Evarestus named in chapter XX. Justin's source introduction states that the narrative's authorship is unknown. The martyr is the subject of each narrative. He did not write the account of his own execution and the events afterward. This differs from the Martyrdom of Ignatius, whose exceptional current label is explicitly settled by D10; that decision does not apply to these two other documents.

I read the source greetings, Polycarp chapters I, XIX–XXII, Justin chapters I–V and the source introductory notice. Examples: `f51ae85d-04d7-56fc-8092-124367c56923`, `the-martyrdom-of-polycarp/chapter-xix`, describes Polycarp's death and heavenly life but names Polycarp as author; `2b304658-698e-5a36-916e-0816c74b4002`, `/chapter-xx`, names the letter's writer while its metadata names Polycarp; and `50107140-f323-50bc-9c1f-cc1e9ac1b9c2`, `the-martyrdom-of-justin-martyr/chapter-v`, narrates Justin's execution and burial but names Justin Martyr as author. All 27 complete references and anchors are in `live-martyrdom-authorship.json` and the build equivalent.

The [Polycarp narrative itself](https://www.newadvent.org/fathers/0102.htm) supplies the institutional sender and named writer. The [vendored edition's Justin notice](https://www.ccel.org/ccel/schaff/anf01.viii.x.html) states its author is unknown. No disputed modern authorship theory is required for this correction. A reader seeking Polycarp's own writings instead receives later narration under his name, and the embedding prefix likewise treats that narration as his writing. Keep these admitted narratives, identify Polycarp's work as the Church of Smyrna's account, and label Justin's narrative Anonymous. The later transcription statements in Polycarp XXII should receive their own provenance treatment without pretending they are Polycarp's words.

Future check: `attribution.church-fathers.martyrdom-narrators`, requiring these two document authors to match their source's narrators and keeping the explicit Ignatius exception separate. Reproduce `fathers-attribution.py`, which writes the entire live/build sets and the source evidence. 1.8c restores the Polycarp greeting but specifies no authorship change; 3.2 lists the Ignatius martyrdom and other anonymous works but omits these two.

### B-002. Three more Summa articles omit their entire sed contra from the vendored edition

Severity: high. Status: known, underestimated relative to A-018's two independent-source omissions; these three omitted units are additional. Owner: extend 1.7 with independent-source collation. Collection: Summa. The three affected articles contain 23 live and 23 build passages: I-II q.88 a.4 has nine, II-II q.182 a.4 has seven, and III q.7 a.10 has seven. Zero saved retrieval, bookmark, guest-result or relevance-label rows point to these 23 passages. The missing units themselves have no current passage IDs.

Each English article moves directly from its final objection into the determination. The independent Leonine Latin inventory includes a substantive sed contra in between. I read all three complete English articles and the three Latin arguments. They concern the infinite difference between mortal and venial sin, Gregory's statement that the active life precedes contemplation in time, and John's association of the fullness of grace with Christ as the Father's only-begotten Son. The English determinations do not supply these omitted argument units. Unlike a combined or unmarked paragraph, the text is absent from the source itself. The [New Advent I-II q.88 edition](https://www.newadvent.org/summa/2088.htm#article4), [II-II q.182 edition](https://www.newadvent.org/summa/3182.htm#article4) and [III q.7 edition](https://www.newadvent.org/summa/4007.htm#article10) share the omissions, so checking only that familiar English copy would miss them too.

Representative existing determination passages are `2b0c3bcd-391d-53ca-b4e9-e6948a1fe9d4`, I-II q.88 a.4; `f0cca040-95af-5a50-b112-32b8784a94e5`, II-II q.182 a.4; and `0d314694-d0a4-54e2-bbbc-358f9858b6cf`, III q.7 a.10. All cite their respective article and have `unit_label='I answer that'`. Complete anchors are in `live-summa-missing-sed-contra.json`. The independent units are [37352](https://www.corpusthomisticum.org/sth2085.html#37352), [46231](https://www.corpusthomisticum.org/sth3179.html#46231) and [47160](https://www.corpusthomisticum.org/sth4002.html#47160).

A user cannot read or retrieve Aquinas's actual counterargument even after a parser rewrite retains every word in the vendored XML. The 23 count describes articles with incomplete integrity; it does not imply 23 false paragraph bodies. Find a verified existing English edition containing these units, respecting the settled prohibition on making our own translation. Future check: `coverage.summa.independent-sed-contra-inventory`, requiring a disposition for each independently attested unit rather than treating absence in the vendored source as zero expected text. Reproduce `summa-additional.py`, which tests all three source boundaries and writes the complete live/build sets and independent evidence.

### B-003. Nineteen contiguous canon groups carry the wrong chapter number

Severity: high. Status: known, underestimated relative to A-002; these 100 passages are disjoint from its 209 collision passages. Owner: extend 1.5a with hierarchy reconstruction, coordinated with 2.1. Collection: canon-law. One hundred live and 100 build passages across 19 contiguous reader groups. They have 13 saved retrieval rows, zero bookmarks, guest-result rows and relevance labels. Distinct users cannot be counted.

A-002 counts noncontiguous chapter-key collisions. A second defect survives even when a key's positions are contiguous: 100 Book VII passages say `Chapter I` although their source chapter is II, III, IV, V or VI. The source table of contents explicitly gives the chapter number. Several body headings omit that numeral and print only the heading's name, which the parser classifies as a title. The builder then forward-fills the last `Chapter I`. This is not a missing-word or canon-text error.

I independently mapped each source table-of-contents link to its named body anchor, kept the numbered hierarchy and joined every present canon to that state. I inspected all 19 affected heading boundaries and their first, middle and final canons. Representative examples: `529f80c2-e30d-5f6c-a5a5-ba4b543f1f9f`, `can/1481`, reference Can. 1481, says "Procurators for Litigation and Advocates — Chapter I", but the source identifies Chapter II. `eb6111cb-710a-5043-b89a-94f4078714ae`, `can/1547`, says "Witnesses and Testimonies — Chapter I", but it is Chapter III. `553c9e4f-58d9-5e05-8ee6-16df1b4c1154`, `can/1584`, says "Presumptions — Chapter I", but it is Chapter VI. Full labels, anchors, references and source contexts for all 100 are in `live-canon-wrong-chapter-number.json` and the build equivalent.

The affected canon ranges are 1481–1490, 1496–1500, 1507–1512, 1539–1586, 1596–1597, 1628–1640, 1645–1648 and 1720–1731. The 1539–1586 run contains multiple distinct article headings, which explains why eight numerical runs occupy 19 current reader groups. No passage in this set belongs to A-002's noncontiguous collision groups.

The reader displays incorrect locations and the embedding prefix carries the incorrect chapter label. The specified canon parser fixes canon segmentation, revisions and footer removal without reconstructing this hierarchy. Rebuild canonical chapter state from the source's table of contents/body correspondence and preserve the actual Title/Chapter/Article levels; do not treat a chapter description as a new title. Future check: `metadata.canon-law.chapter-number-agreement`, comparing each canon's chapter ordinal with the source hierarchy, including every contiguous group. The 17-collision check alone cannot catch these cases. Reproduce `canon-toc.py`, which writes the complete 1,747-canon source map, heading events and both affected sets. Its deliberately narrow finding criterion requires both an explicit source chapter number and a conflicting displayed chapter number.

### B-005. Thirty-nine pieces merge prose replies to different argument targets

Severity: medium. Status: known, underestimated relative to A-015's 27 explicit marker/number defects and A-017's counterargument target scope; these 39 pieces are disjoint from every existing Sol finding ID. Owner: extend 1.7's argument-target model. Collection: Summa. Thirty-nine live and 39 build passages, with no saved retrieval, bookmark, guest-result or relevance-label rows.

Aquinas often answers an objection with a prose formula rather than a bold numbered marker. Thirty-eight current pieces are labeled `Reply to Objection N` but also contain a separate source paragraph explicitly answering a different numbered objection. One further piece includes separate replies to both arguments under the sed contra, Aquinas's argument against the objections, while labeled reply 3. The independent Latin structure identifies that separate reply target. The proposed walk appends every unmarked paragraph to its preceding part, so its new precise `ad N` citation would still omit the extra target. Five of the 38 ordinary-target pieces explicitly answer two objections together; a correct representation must preserve both rather than invent one numbered reply.

I read all 40 explicit source target paragraphs represented in these 39 pieces and their corresponding independent Latin replies. The final script scans all 11,097 unbold core source paragraphs rather than relying on the initial 189 candidates. Full current passages and source/Latin context are in the evidence output; representative pieces were read in full. Examples: `a9bd2d02-33f1-5fcc-936e-d5ba3d05a9af`, I q.62 a.4, anchor ending `/article-4-whether-an-angel-merits-his-beatitude/6`, labeled reply 2 but ending with the source's explicit reply to objection 3; `82944123-779d-5871-a6fb-aebe3c62f757`, I q.76 a.1, `/10`, labeled reply 1 but containing the answer to objections 2 and 3; and `71672eb3-b4f6-5e05-8fa9-e5fe0465e8de`, III q.25 a.2, `/5`, labeled reply 1 but also answering objections 2 and 3. Full article references are in `live-prose-replies-wrong-target.json`.

The counterargument case is I q.66 a.1: live `1840a1a7-9f11-5fb4-a8bc-c3337bedf305`, anchor ending `/article-1-whether-formlessness-of-created-matter-preceded-in-time-its-formation/7`; build `2b4f7ecc-d63e-5e49-ac49-a3b1bd1b15a7`, same article `/8`. Its ordinary reply 3 is followed by answers to the first and second contrary arguments. The independent source calls those `ad 4` and `ad 5` (units 31202/31203), not ordinary replies 1/2. I read both English paragraphs and complete Latin counterparts; the evidence explicitly distinguishes counterargument targets. Another identity shift affects I-II q.102 a.6: live `fb614962-1f34-519d-9da7-4f81d74e915d` `/16`, build `3ab89440-914c-55f6-83a9-906ec1ce0887` `/17`. Those shifts are evidence identities, not a new identity finding.

The user receives an attachment to the preceding numbered argument alone, and a search for the omitted reply cannot find an independently targeted passage. This finding does not claim Aquinas's prose is false or that all 189 broad candidates are defects. Its narrow count requires an explicit named different target, a manually verified independent Latin reply, a current numbered reply label and one unique content match in each corpus. The two counterargument replies use their actual Latin `ad 4/ad 5` counterparts; matching their prose ordinals to ordinary `ad 1/ad 2` would be wrong. Standard shorthand `Reply OBJ` cases from A-015, determination passages, ambiguous references and every previously reported ID are excluded.

Use source-bounded target metadata or joint reply labels, packing short formulas with enough preceding explanation to make sense. Future check: `context.summa.prose-reply-target-agreement`, comparing every formal source reply target with the rendered/stitched targets, allowing joint replies. Reproduce `prose-replies.py`; its 40 reviewed source paragraphs are not merely inferred from a count deficit. Other prose formulas remain candidates until their role and counterpart are established.

## Coverage map

This pass reused the original live/build rows and independent core Summa inventory. It did not rebuild adapters, repeat production exports, run paid models or touch production Postgres. The completed Sol report remains the baseline for areas not reexamined here. The other reviewer's materials were not accessed.

| Collection | Fresh examination and disposition |
|---|---|
| summa | All 11,097 unbold core source paragraphs scanned for explicit reply-target formulas; 40 paragraphs verified in B-005. Independent sed-contra census and article boundaries establish B-001/B-002. Existing formal `Reply OBJ` cases, including the four Supplement examples, were checked against A-015 and excluded. The remaining 263 broad discrepancy candidates were not fully dispositioned. The Supplement's 446 vendored article containers were inventoried, but independent bulk comparison failed. |
| canon-law | Table-of-contents links joined to named body headings; all 1,747 current canons have source counterparts. Explicit source/display chapter ordinals compared throughout, yielding B-003. All 19 affected group boundaries were inspected. This is not certification of every higher-level Title/Part/Section key. An earlier 240-candidate heuristic was rejected because it misclassified all-capital chapter descriptions. |
| church-fathers | Both martyrdom source narratives, greetings and authorship notices establish B-004. Selected Justin Dialogue speaker boundaries and imperial appendices were inspected; no further defect was proved. Hadrian's rescript is intentionally introduced as a quotation, not automatically a wrong-author passage. Spurious appended imperial material remains a provenance question. |
| medieval | Selected Cur Deus Homo speaker continuations and Anselm/Boso turns inspected. Boso's objections are explicitly framed in the text; two unprefixed continuations do not by themselves prove false attribution or heterodox standalone doctrine. Existing book-key problems remain planned. No additional verified finding. |
| bible | Original Sol coverage reused; no fresh verse or genre certification. |
| catechism | Original Sol coverage reused; no fresh paragraph or update certification. |
| councils | Original Sol coverage reused; no fresh edition/body collation. |
| encyclicals | Original Sol coverage reused; no additional independent source collation. |
| apostolic-exhortations | Original Sol coverage reused; no additional independent source collation. |
| papal-documents | Original Sol coverage reused; no additional independent source collation. |

| Hunt area | Fresh result and limits |
|---|---|
| Search index against reader store | Original exhaustive payload comparison and bounded vector checks reused. No new vector query or provenance claim. New author/role/chapter defects matter to embedding prefixes and stored display text, but historical embedding inputs remain unprovable from payload alone. |
| Metadata and labels | B-003/B-004; all counted rows validated against both cached corpora. No fresh full title/year/translation census. |
| Text quality inside passages | Source-boundary and missing-unit integrity in B-001/B-002/B-005. III q.22 a.5's longer Latin reply was checked against the following unbold English paragraph: its content is present, so it is a role-boundary defect within B-005, not another source omission. No repeat global OCR/entity/markup scan. |
| Whether a passage can be found and understood | Actual source-role and attachment inputs inspected. No paid retrieval/explanation experiment. Broad count mismatches, source notes already scheduled for removal and plausible speaker false positives were not promoted to findings. |
| Duplicates and overlaps | Quoted imperial material inspected for false attribution; existing duplicate/vector findings reused. No new corpus-wide near-duplicate pass. |
| Reader and links | Contiguous wrong canon chapter labels checked, and live/build identities preserved. Saved reading positions checked against the entire supplemental union: none affected. Stored `document_chapters` is absent from the snapshot, so no new assertion about the actual stored outline. |
| Corpus scope and trust | Martyr subject versus narrator verified; D10's Ignatius exception preserved. No new exclusion or authenticity decision based merely on a dialogue participant. |
| Recurrence and future interactions | Every finding has a new check ID and named planned owner. Bold-only Summa parsing preserves the new role defects; collision-only canon checks miss the new ordinal defects. Joint and contrary-argument replies need real target metadata, not invented ordinary objection numbers. |
| Saved user data | Every affected live ID checked against counts; 13 retrievals, zero bookmarks/guest results/labels. No individual identities examined. |

No additional verified finding means precisely that: it is not an assurance that every sentence or metadata field in that area is correct.

## Questions for Carter

1. **Should the three additionally omitted Summa counterarguments be release blockers until an existing English edition supplies them?** Option A requires verified existing English source text before publishing those complete articles. Option B explicitly records the omissions and retains incomplete articles, which falls short of the stated final-cleanup goal. Recommendation: A; add the three units to the existing independent-source recovery work alongside A-018, without making an original translation.
2. **Should the reviewed Summa target ledger distinguish joint replies and replies to the sed contra?** Option A stores real source targets, allowing multiple arguments and contrary-argument targets to travel into stitching and role formatting. Option B relies on one `Reply to Objection N` label, preserving these ambiguities. Recommendation: A, coordinated across 1.7, source facts and context assembly.

These are disposition choices for the cleanup, not authorization requests for work performed by this reviewer. Canon ordinal restoration and correcting the two narrative authors need no new doctrinal scope decision.

## Reproduction

Scratch root: `datapipeline/releases/local/review-sol-followup/`. Run these commands from the repository root. Scripts read the existing `review-sol/live-rows.json`, `build-rows.json`, `english-core-structure.json`, `latin-core-structure.json`, original finding union and the October 6 snapshot. Their source evidence and full passage bodies stay in gitignored scratch, not this public report.

```bash
PATH="$PWD/datapipeline/.venv/bin:$PATH" python3 datapipeline/releases/local/review-sol-followup/canon-toc.py
python3 datapipeline/releases/local/review-sol-followup/summa-additional.py
PATH="$PWD/datapipeline/.venv/bin:$PATH" python3 datapipeline/releases/local/review-sol-followup/fathers-attribution.py
python3 datapipeline/releases/local/review-sol-followup/prose-replies.py
python3 datapipeline/releases/local/review-sol-followup/verify-findings.py
```

| Script/output | Purpose | Measured elapsed time |
|---|---|---:|
| `canon-toc.py`, `canon-toc-inventory.json`, `canon-toc-events.json` | Independently numbered source hierarchy and complete B-003 sets | 0.72 s |
| `summa-additional.py`, `summa-missing-independent-evidence.json` | B-001/B-002 complete sets and independent core witnesses | 6.72 s |
| `fathers-attribution.py`, `source-martyrdom-authorship.json` | B-004 complete sets, narratives and notices | 0.57 s |
| `prose-replies.py` | B-005 complete sets with reviewed source/Latin targets; initial candidate-dependent version took 49.59 s, final complete-source scan is faster because content normalization is cached | about 2.5 s |
| `verify-findings.py`, `verification-summary.json`, live/build finding unions | Verify every counted row, equal live/build content sets, original-report exclusion, references and report example IDs | about 0.4 s |
| `canon-hierarchy.py` | Discarded preliminary heuristic; its 240 candidates are **not findings** | 0.72 s |
| `supplement-inventory.py`, `supplement-summary.json` | Attempted independent New Advent Supplement comparison; all 99 requests returned HTTP 403, zero comparator pages were obtained | 11.48 s |
| `finalize-report.py` | Assemble this final report from saved findings and coverage | under 1 s |

The failed Supplement comparator's empty difference list proves nothing. Do not rerun its network requests merely to reproduce a blocked comparator. The vendored 446-container inventory is retained as `english-supplement.json`; the corresponding independent inventory is empty. No original Sol artifact was overwritten.

`verification-summary.json` confirms 193 distinct affected IDs per corpus, no live/build-ID overlap with the respective original Sol finding unions, and validates every example ID printed here. All finding evidence files begin `live-` or `build-` and retain full anchors/references. The original positional-ID finding explains the two changed B-005 identities; comparing IDs alone would conceal their equal content.

## Next

This additional pass is complete within the scope recorded above. Broader certification still requires:

- Complete the remaining implicit core Summa discrepancy review, separating source omissions, valid joint replies and edition differences.
- Obtain an independent Supplement edition or readable scan and compare it with the 446 vendored article containers; the failed bulk download is not a clean result.
- Finish all canon hierarchy levels and obtain stored reader outlines in an augmented snapshot, as already requested by the original report.
- Resolve the five supplemental findings and run their regression checks through the planned staged release; extend the corpus target ledger before assigning precise reply citations.
- Review appended imperial notices and remaining dialogue speaker provenance if retaining those source blocks; do not count the current unverified candidates as defects.
