# TheoCorpus corpus health, completeness, and retrieval audit

Audit date: 28 September 2026  
Environment: development Supabase project, currently treated as production  
Scope: all ten published collections, their live Supabase rows, Qdrant points, local vendored sources, current source adapters, publication history, and the previously reviewed question set

## Executive assessment

TheoCorpus has excellent storage parity but material source-construction defects.

- Every one of the 54,568 live Supabase passages has a Qdrant point with the same identity. There are no missing points and no orphan points.
- Qdrant payload content and structural metadata match Supabase for all live passages. No nonblank passage has a vector built from stale text.
- Twenty-one Summa passages have blank content in Supabase. Their points exist, but they are not healthy or useful retrieval units.
- The vendored *Nostra Aetate* source is complete. The Vatican II parser drops continuation paragraphs after the first numbered paragraph of a section, then sometimes treats numbered footnotes as sections. This affects all 16 Vatican II documents, not just *Nostra Aetate*.
- A source-driven audit found 436 of 614 numbered Vatican II sections with at least one dropped continuation paragraph, approximately 542,560 omitted characters, and 76 spurious footnote passages. The character count is a parser-based estimate, not a canonical edition diff.
- The live corpus was mostly published in June 2026 and does not reflect the last passage-splitting repairs committed on 22 August. Building every collection with today's adapters produces 54,778 passages, 210 more than live (corrected 5 Oct 2026 by item 0.1c: this line and the table's total row first read 54,776 and 208, but the per-collection rows sum to 54,778), and preserves about 18,747 additional characters. Those later generic fixes still do not repair the Vatican II continuation bug.
- All 54,568 live passages have empty annotation fields. TheoCorpus is therefore retrieving raw passage text only, despite having an enrichment design capable of facets, generated questions, and annotations.
- Corpus metadata is too thin for authority-aware or version-aware retrieval. Only the 16 Vatican II documents have a `document_type`. The live metadata has no consistent authority level, issuing body, approval status, effective version, or supersession relationship.
- Three vendored documents are not in a manifest and therefore cannot be published by the normal collection process: *Amoris Laetitia*, *A New Hope for Lebanon*, and *Ubicumque et Semper*. In addition, the major HTML collections lack recorded source hashes, so their local provenance cannot currently be verified.

The highest-value action is to repair and republish the corpus before tuning semantic ranking. A reranker cannot recover text for which no passage or vector exists.

## Threshold question: CDF, DDF, and *Universi Dominici Gregis*

### CDF and DDF

CDF means Congregation for the Doctrine of the Faith. DDF means Dicastery for the Doctrine of the Faith. These are the pre-2022 and post-2022 names of the same continuing Roman Curia institution, not separate bodies. Francis reorganized the Congregation into doctrinal and disciplinary sections in *Fidem servare*. *Praedicate Evangelium*, effective 5 June 2022, adopted the DDF name while retaining those sections.

The office helps the Pope and bishops promote and safeguard Catholic teaching on faith and morals. Its doctrinal section studies doctrinal questions and examines writings or opinions; its disciplinary section handles reserved delicts and related canonical proceedings. The office publishes many different genres: declarations, instructions, notes, responsa, letters, notifications, decrees, procedural norms, rescripts, press releases, presentations, and commentary. These do not all have the same teaching authority or purpose.

A curated CDF/DDF doctrinal collection belongs in TheoCorpus if the product is meant to answer Catholic doctrinal, moral, and bioethical questions. *Donum vitae*, *Dignitas personae*, and *Dominus Iesus* are clear examples. The whole DDF website should not be flattened into one authority tier. Each document needs issuer, genre, date, papal approval language where present, Acta Apostolicae Sedis citation, authority or source role, and amendment or supersession metadata. Pontifical Biblical Commission and International Theological Commission documents need their own institutional authorship rather than an inherited DDF label.

Primary sources: [DDF historical profile](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_pro_14071997_en.html), [*Fidem servare*](https://www.vatican.va/content/francesco/en/motu_proprio/documents/20220211-motu-proprio-fidem-servare.html), [*Praedicate Evangelium*, articles 69 to 78](https://www.vatican.va/content/francesco/en/apost_constitutions/documents/20220319-costituzione-ap-praedicate-evangelium.html#Dicastery_for_the_Doctrine_of_the_Faith), [official DDF document index](https://www.vatican.va/roman_curia/congregations/cfaith/doc_doc_index.htm), and [*Donum veritatis*, 15 to 18 and 23 to 24](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_19900524_theologian-vocation_en.html).

### *Universi Dominici Gregis*

*Universi Dominici Gregis* is John Paul II's 1996 apostolic constitution on a vacancy of the Apostolic See and the election of the Roman Pontiff. It is universal papal legislation, not primarily a doctrinal treatise. It governs the College of Cardinals during a vacancy, the conclave, voting, secrecy, acceptance, and proclamation.

It belongs if TheoCorpus covers canon law, papal governance, or common questions about conclaves. The searchable default should be the Vatican's consolidated text current from 22 February 2013. The 1996 original and Benedict XVI's 2007 and 2013 amendments should remain linked historical versions. The 2025 dispensation concerning more than 120 electors was an application in a concrete vacancy, not a silent textual amendment. Present-tense retrieval should prefer the current consolidated provision.

Primary sources: [consolidated *Universi Dominici Gregis*](https://www.vatican.va/content/john-paul-ii/en/apost_constitutions/documents/hf_jp-ii_apc_22021996_universi-dominici-gregis.html), [2007 amendment](https://www.vatican.va/content/benedict-xvi/la/motu_proprio/documents/hf_ben-xvi_motu-proprio_20070611_de-electione.html), [2013 *Normas nonnullas*](https://www.vatican.va/content/benedict-xvi/en/motu_proprio/documents/hf_ben-xvi_motu-proprio_20130222_normas-nonnullas.html), and the [2025 cardinal declaration](https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2025/04/30/250430a.html).

## Audit method

The audit was read-only against live services. It did not publish, delete, repair, or rewrite corpus data.

1. Counted passages by collection in Supabase and Qdrant.
2. Compared passage IDs in both systems for missing and orphan points.
3. Compared Qdrant content and structural payloads with Supabase.
4. Re-embedded live passage text in audit mode and compared it with stored vectors to detect stale-vector drift.
5. Built all collections locally with the current adapters and compared deterministic passage IDs, content, and structure with live Supabase.
6. Parsed every vendored Vatican II HTML file independently to measure numbered body sections, unnumbered continuation paragraphs, footnote leakage, and duplicate section numbers.
7. Audited database structure, blank and very short passages, duplicates, outline counts, metadata coverage, annotations, and source manifests.
8. Reviewed Git history to place ingestion changes against question dates and live publication dates.
9. Ran the datapipeline test suite with network access allowed for the tokenizer cache: 777 tests passed.

Passing tests show that the implemented behavior is internally stable. They do not establish source completeness. The Vatican II tests encode the current faulty parsing assumption and therefore did not catch the omitted text.

## Live storage and vector parity

| Collection | Supabase passages | Qdrant points | Missing points | Orphan points |
|---|---:|---:|---:|---:|
| Apostolic exhortations | 3,024 | 3,024 | 0 | 0 |
| Bible | 3,262 | 3,262 | 0 | 0 |
| Canon law | 1,747 | 1,747 | 0 | 0 |
| Catechism | 800 | 800 | 0 | 0 |
| Church Fathers | 9,783 | 9,783 | 0 | 0 |
| Councils | 2,173 | 2,173 | 0 | 0 |
| Encyclicals | 6,110 | 6,110 | 0 | 0 |
| Medieval | 434 | 434 | 0 | 0 |
| Papal documents | 485 | 485 | 0 | 0 |
| Summa | 26,750 | 26,750 | 0 | 0 |
| **Total** | **54,568** | **54,568** | **0** | **0** |

For every live row, content and structural payloads match between stores. The vector-drift check found no stale vector for any nonblank passage. The only anomaly is 21 blank Summa rows. Qdrant contains points for them, but a blank database source cannot be usefully re-embedded or retrieved as a theological answer.

This establishes synchronization, not completeness. Text omitted during source parsing never became a Supabase row and therefore has no Qdrant point to compare.

## The *Nostra Aetate* failure and its systemic scope

The failure is deterministic:

1. The vendored HTML contains the full official section 4 in seven paragraph elements.
2. The first paragraph begins with `4.`; the six continuations do not repeat the section number.
3. The current Vatican II adapter accepts only paragraph elements matching a leading number and period.
4. It therefore stores the first 155 characters and discards the rest, including the rejection of collective Jewish guilt for Christ's Passion.
5. After reaching the notes, it also mistakes numbered footnotes for new body sections.

The same construction appears throughout Vatican II. The audit found:

| Document | Numbered body sections | Sections with dropped continuations | Approx. omitted characters | Spurious footnote passages |
|---|---:|---:|---:|---:|
| *Dei Verbum* | 26 | 10 | 7,229 | 0 |
| *Lumen Gentium* | 69 | 50 | 81,798 | 0 |
| *Sacrosanctum Concilium* | 129 | 65 | 24,426 | 0 |
| *Gaudium et Spes* | 93 | 85 | 138,621 | 0 |
| *Ad Gentes* | 42 | 39 | 62,046 | 0 |
| *Presbyterorum Ordinis* | 22 | 22 | 42,666 | 39 |
| *Apostolicam Actuositatem* | 33 | 27 | 44,579 | 0 |
| *Optatam Totius* | 21 | 19 | 13,507 | 0 |
| *Perfectae Caritatis* | 25 | 18 | 16,369 | 0 |
| *Christus Dominus* | 44 | 37 | 30,695 | 0 |
| *Unitatis Redintegratio* | 24 | 20 | 25,860 | 3 |
| *Orientalium Ecclesiarum* | 30 | 5 | 3,539 | 0 |
| *Inter Mirifica* | 24 | 10 | 6,412 | 0 |
| *Gravissimum Educationis* | 12 | 12 | 21,015 | 24 |
| *Nostra Aetate* | 5 | 5 | 7,334 | 2 |
| *Dignitatis Humanae* | 15 | 12 | 16,464 | 8 |
| **Total** | **614** | **436** | **542,560** | **76** |

The omission estimate groups unnumbered body paragraphs with the preceding numbered section and stops at the notes. It measures the parser's likely loss, not a diplomatic comparison with every official edition.

This defect directly explains at least three reviewed misses:

- "Who killed Jesus?" could not retrieve the crucial part of *Nostra Aetate* 4 because that text does not exist in the corpus.
- "Can I read Scripture without a teacher?" did retrieve *Dei Verbum* 12, but the passage itself is truncated. Sections 10, 11, 12, 18, 20, and 25 are among those affected.
- The Baptist conversion question needed *Unitatis Redintegratio* 3 to 4 and 19 to 23. Most of those sections have dropped continuations, so even a title hit may deliver an incomplete teaching.

This is more serious than a ranking problem. It also means a user can open an apparently authoritative council passage and read an incomplete section without any warning.

## Other completeness and quality findings

### Live publication is behind current adapters

The last substantive passage-construction change was commit `3c92ccb` on 22 August 2026 at 21:27 EDT, "split display passages at readable boundaries." Earlier that day, `ea7bca9` fixed a generic splitter that could discard all pieces after the first when overlap was zero. The previous day, `d6a0d5d` fixed comma-less Summa dialectical markers.

Most live rows were inserted between 22 and 25 June. Current adapters and vendored sources produce the following differences from live:

| Collection | Current build | Live | Missing from live by current ID | Extra in live | Content differences | Net additional characters in current build |
|---|---:|---:|---:|---:|---:|---:|
| Apostolic exhortations | 3,053 | 3,024 | 51 | 22 | 364 | 3,439 |
| Bible | 3,295 | 3,262 | 64 | 31 | 479 | 2,456 |
| Canon law | 1,747 | 1,747 | 0 | 0 | 0 | 0 |
| Catechism | 809 | 800 | 22 | 13 | 98 | 1,837 |
| Church Fathers | 9,783 | 9,783 | 0 | 0 | 0 | 0 |
| Councils | 2,202 | 2,173 | 58 | 29 | 107 | 3,491 |
| Encyclicals | 6,154 | 6,110 | 81 | 37 | 363 | 3,295 |
| Medieval | 449 | 434 | 20 | 5 | 212 | 2,132 |
| Papal documents | 494 | 485 | 14 | 5 | 89 | 754 |
| Summa | 26,792 | 26,750 | 63 | 21 | 727 | 1,343 |
| **Total** | **54,778** | **54,568** | **373** | **163** | **2,439** | **18,747** |

"Missing" and "extra" use deterministic passage IDs, so boundary changes can turn one logical replacement into both a missing and an extra row. This is not a count of wholly absent doctrines. It proves that the live publication does not match current methodology. Republishing needs the existing identity-churn review because saved retrievals and bookmarks can refer to passage IDs.

The 22 August repairs do not solve the Vatican II problem. The current councils adapter still reproduces the continuation loss. The historical misses from 8 July, 11 August, and 15 August predate the splitter repair. The addiction and Baptist misses on 23 and 24 September postdate it, but the live corpus remained on the older publication and the council-specific bug remained in current code.

### Blank, tiny, and noisy passages

- Twenty-one Summa rows are blank, mostly objections. These should fail publication rather than receive points.
- Very short passages include legitimate brief canons and Bible verses, but also clear debris: `Islam`, page numbers such as `146` and `170`, a lone quotation mark, `PAUL VI`, `VI`, `8.21).`, dating lines, and footnote fragments.
- Conservative counts under 20 characters include 10 apostolic-exhortation passages, 2 Bible passages, 1 council passage, 17 encyclical passages, 1 medieval passage, 1 papal passage, and 3 nonblank Summa passages. There are also the 21 blank Summa rows.
- Four within-document duplicate text groups of at least 100 characters were found. Two council duplicates are misparsed *Presbyterorum Ordinis* footnotes. One of the two Summa groups may be a legitimate repeated quotation; the other duplicates an objection inside one article.

A global minimum-length rule would delete real content. Health rules should be adapter-aware and should reject empty text, known footer or note regions, and pure page-number or punctuation debris while permitting legitimate short verses and canons.

### Structural database health

The live database has 421 documents and 54,568 passages. All live passages have anchors, chapter keys, chapter labels, and FTS vectors. Positions are contiguous, anchors are unique within their documents, and every precomputed document outline count agrees with the actual passage count. These are strong results.

The weak point is semantic enrichment: all 54,568 passages have empty annotations. The production pipeline therefore depends on raw passage vocabulary, HyDE, embeddings, and reranking. Exact concepts not named in the passage, precise paragraph references, and modern-language paraphrases receive no help from the designed enrichment layer.

### Source inventory and provenance

Three vendored files are absent from their manifests and therefore never enter a normal publication:

- `apostolic-exhortations/amoris-laetitia.html`
- `apostolic-exhortations/a-new-hope-for-lebanon.html`
- `papal-documents/ubicumque-et-semper.html`

The live collection does contain *Laudate Deum*. It is not a missing source. *Evangelii Nuntiandi* and *Evangelii Gaudium* are currently classified under encyclicals even though they are apostolic exhortations, which can confuse collection-scoped retrieval and evaluation.

Source verification succeeded for the hashed Church Fathers, medieval, and canon-law inputs. It could not verify the 131 encyclicals, 30 apostolic exhortations, 14 papal documents, or the HTML council sources because their manifests carry no recorded hash. The files may be correct, but the publication is not reproducible from a cryptographically recorded source inventory.

### Metadata is insufficient for theological discrimination

Only 16 of 421 documents have a `document_type`, all Vatican II documents. No consistent field records authority level, issuing body, express papal approval, current or superseded status, legal effect, or relationship to an amended text. This makes it impossible for retrieval to distinguish, for example, a dogmatic constitution, a disciplinary norm, a papal encyclical, a dicastery responsum, and accompanying commentary by policy rather than by whatever wording the title happens to contain.

## Catechism segmentation

The Catechism is already segmented at the smallest natural heading-defined unit available in the source. It is not simply cut into arbitrary large windows. CCC 2408 to 2414 and CCC 2351 to 2356 are coherent source sections. Treating that as a failed ingestion would be wrong.

There is still a search-index design issue. A query for "gambling" needs CCC 2413 and a query for "prostitution" needs CCC 2355, but the vector represents the whole natural section. The best solution is to preserve natural sections as reader passages while creating paragraph-level secondary retrieval units, or paragraph-level annotations and generated questions, that resolve back to the natural passage. This avoids degrading reading context while improving exact recall.

## Previously reviewed questions: what the audit changes

The prior review identified ranking misses such as Summa I, questions 63 to 64 for the devil; CCC 1735 for addiction; CCC 597 to 598 and *Nostra Aetate* 4 for responsibility for Jesus' death; and *Unitatis Redintegratio* for conversion and ecumenism.

This audit divides them into three classes:

1. **Impossible retrieval.** The needed text was omitted during parsing. *Nostra Aetate* 4 is the clearest case. No ranker can return absent text.
2. **Present but hard to target.** Exact Catechism paragraphs sit inside natural sections; Summa loci and other numbered units exist but need exact-reference and title-aware retrieval; annotations are absent.
3. **Present and retrievable but poorly prioritized.** The system sometimes chooses semantically similar older or indirect sources over a direct council, Catechism, or modern synthesis. This needs authority, source-role, and query-mode signals.

The saved pre-change results support this distinction. The devil query returned Summa passages on deliverance from the devil and temptation, but not the direct angelic-fall treatise in I, questions 63 to 64. The Scripture-teacher searches included *Dei Verbum* 12 or 23 only at ranks 7 to 11 and delivered truncated sections. The "Who killed Jesus?" search included CCC 597 near the top and CCC 598 around rank 10, but could not return the missing part of *Nostra Aetate* 4.

## Controlled rerun status

The rerun plan preserves each original question, selected collections, quota, and the current production pipeline. It covers eight representative searches: devil, two Scripture-teacher quotas, responsibility for Jesus' death, addiction, Baptist conversion, frozen embryos, and cardinal election.

The reruns have not been executed. They would transmit previously stored theological and medical query text to the configured external embedding and model providers. The runtime approval gate rejected that egress without explicit informed authorization. No query text left the machine during this audit. Once authorized, the reruns can distinguish improvements caused by today's ranking pipeline from failures that remain because the live corpus was never republished. Until then, no claim of before-and-after retrieval improvement is warranted.

## Retrieval and publication improvements

### Priority 0: restore source integrity

1. Rewrite the Vatican II adapter to group every continuation paragraph with its numbered section and to stop before notes and footers.
2. Add source-completeness tests that compare captured visible body text or canonical section sentinels, not merely the adapter's own output shape.
3. Repair the 21 blank Summa passages and reject empty content at publication time.
4. Add the three unmanifested source files deliberately or remove them from the vendored tree with a documented reason.
5. Record source hashes for every manifest entry.
6. Review and publish current adapters collection by collection with an identity-churn report. Do not bulk-replace IDs without mapping effects on saved retrievals and bookmarks.

### Priority 1: make corpus state observable

Persist source checksum, adapter version or commit, publication revision, content hash, and publication timestamp on each document or release. CI should build current sources and compare passage count, character count, IDs, blank count, and terminal sentinels with the last approved baseline. Any unexplained contraction should block publication.

Keep the successful Supabase-to-Qdrant parity and payload checks as a scheduled health audit. Add a semantic reachability check that verifies vectors against current nonblank passage text. Report "existing-row parity" separately from "source completeness" so a perfect parity score cannot mask parser loss.

### Priority 2: improve retrieval precision

1. Add paragraph-level secondary units for the Catechism and similar numbered texts while keeping natural sections as the displayed reader passages.
2. Parse exact references such as `CCC 2413`, `Dei Verbum 12`, `ST I q.63`, canon numbers, and Bible citations. Boost exact document, title, chapter, article, and paragraph matches before semantic ranking.
3. Publish high-quality annotations, facets, and generated questions for passages, then evaluate their contribution. The current all-empty annotation state leaves a useful retrieval channel dormant.
4. Give the ranker document-level inputs for authority, genre, issuer, date, approval status, currentness, and source role. A direct governing or doctrinal source should usually outrank an indirect thematic resemblance, but user-selected filters must still be honored.
5. Add an exhaustive or enumerative query mode for requests such as "all papal bulls" or "what councils say." Semantic top-k is the wrong primitive for inventory questions.
6. Diversify broad answers by source role and authority, not only by document or chapter caps. An introductory Eucharist answer should not spend every slot on one historical source family when Scripture, the Catechism, a council, and later synthesis are selected.
7. Expose filter limitations. When the best governing source is outside the selected collections, preserve the user's scope but say what kind of source is excluded and offer a wider search.

### Priority 3: expand cautiously

Add a curated CDF/DDF doctrinal collection because it would materially improve bioethics and contemporary doctrinal questions. Add *Universi Dominici Gregis* if governance and conclave questions remain in scope. Neither should be added until authority and version metadata exist. Otherwise the corpus will gain coverage while making theological weighting less reliable.

## Recommended order of work

1. Fix and test the Vatican II parser.
2. Repair blanks, note leakage, source manifests, and hashes.
3. Add release metadata and run a reviewed republish of affected collections.
4. Run the eight controlled before-and-after searches after explicit provider-egress approval.
5. Evaluate exact-reference routing, paragraph-level secondary units, and authority-aware reranking against the same fixed question set.
6. Only then add curated CDF/DDF material and versioned *Universi Dominici Gregis*.

## Bottom line

TheoCorpus's two storage systems are synchronized and structurally healthy. The central risk lies earlier in the chain: incomplete parsing, stale publication, weak provenance, and insufficient theological metadata. The *Nostra Aetate* miss was not an isolated bad document and was not a vector-store outage. It was one visible result of a Vatican II-wide adapter failure. Repairing source construction will improve answers more than another round of ranking-weight changes. After that repair, exact-reference handling, secondary paragraph units, annotations, and authority-aware ranking are the most promising retrieval improvements.

The official-source threshold memo with fuller CDF/DDF and *Universi Dominici Gregis* discussion is [CDF, DDF, and *Universi Dominici Gregis*](2026-09-28-cdf-ddf-udg-source-memo.md).
