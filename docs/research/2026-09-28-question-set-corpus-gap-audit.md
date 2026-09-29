# Corpus gaps revealed by the September 2026 user question set

Checked 28 September 2026 against the 56 retrieval sets reviewed in this thread, the current vendored manifests, and official Holy See or episcopal-conference sources. This note separates three problems that can look alike in the product:

1. TheoCorpus owns the right text but does not retrieve it.
2. TheoCorpus lacks the right text.
3. The question requires a source type that should not be presented as universal Catholic teaching.

The short answer is that retrieval caused more weak answers than corpus coverage did, but collection filters explain several apparent misses. Of the 21 sets previously rated 3 or below, eight had a high-confidence omission of a decisive passage from a collection the user had selected. Six other sets lacked an ideal source because the user had excluded its collection: the Bible-only grace search, Summa-only war search, Bible-and-Fathers Church-authority search, Fathers-only Eucharist search, Bible-and-Fathers fear-of-Hell search, and the reconciliation search that excluded apostolic exhortations and councils. Two performance-enhancing-drug searches were mixed cases. The corpus had general moral principles, but not the best sport-specific document. Two questions exposed clear content gaps, two needed a different exhaustive or document-type retrieval mode, and two should have triggered clarification or an out-of-scope response.

The local source inventory and manifests support the corpus-status judgments below. See [`datapipeline/SOURCES.md`](../../datapipeline/SOURCES.md) and the earlier [corpus expansion survey](corpus-expansion-candidates.md).

## Decisive texts already present but not retrieved

These are retrieval or ranking failures where the decisive source belonged to a collection selected for that search. Adding more documents will not fix them.

| Question type | Text already in TheoCorpus | Why its absence mattered |
|---|---|---|
| Reading Scripture without a teacher | *Dei Verbum* 10 to 12 | Both searches selected the councils collection, but the first five results leaned on indirect biblical and patristic material rather than Vatican II's direct rules for interpretation. CCC 80 to 95 and 109 to 119 and *Verbum Domini* 29 to 30 are also ideal sources when those collections are enabled. [*Dei Verbum*](https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651118_dei-verbum_en.html), [CCC 109 to 119](https://www.vatican.va/content/catechism/en/part_one/section_one/chapter_two/article_3/iii_the_holy_spirit%2C_interpreter_of_scripture.html), [CCC 80 to 95](https://www.vatican.va/content/catechism/en/part_one/section_one/chapter_two/artcile_2/iii_the_interpretation_of_the_heritage_of_faith.html) |
| "How to convert Baptists" | *Unitatis Redintegratio* 3 to 4 and 19 to 23, *Ad Gentes* 11 to 13, *Ut Unum Sint*, *Redemptoris Missio*, and *Evangelii Nuntiandi* | TheoCorpus retrieved catechumenal rules aimed largely at the unbaptized. The corpus already has the needed teaching on the baptismal bond, respectful dialogue, witness, freedom, and the call to full communion. [*Unitatis Redintegratio*](https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19641121_unitatis-redintegratio_en.html), [*Evangelii Nuntiandi*](https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html) |
| Who killed Jesus? | CCC 597 to 598 and *Nostra Aetate* 4 | CCC 597 appeared, but the safeguard was incomplete. CCC 598 assigns responsibility to sinners, especially Christians who persist in sin. *Nostra Aetate* rejects charging Christ's Passion to all Jews then alive or to Jews today. Both should outrank an older passage open to an anti-Jewish reading. [CCC 597 to 598](https://www.vatican.va/content/catechism/en/part_one/section_two/chapter_two/article_4/paragraph_2_jesus_died_crucified.html), [*Nostra Aetate* 4](https://press.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html) |
| Is gambling a sin? | CCC 2413 | This paragraph answers the question almost word for word. It distinguishes games of chance in themselves from loss of necessities, enslavement, unfair wagers, and cheating. Its absence is an exact-paragraph recall failure. [CCC 2413](https://www.vatican.va/content/catechism/en/part_three/section_two/chapter_two/article_7/ii_respect_for_persons_and_their_goods.html) |
| Prostitution | CCC 2355 | This paragraph directly covers the dignity of the person, the grave wrong committed by the buyer, social harm, and diminished culpability under destitution, blackmail, or social pressure. Metaphorical passages from Ezekiel should not have displaced it. [CCC 2355](https://www.vatican.va/content/catechism/en/part_three/section_two/chapter_two/article_6/ii_the_vocation_to_chastity.html) |
| Addiction, mortal sin, and Communion | CCC 1735, together with CCC 1857 to 1861 and Eucharistic discipline | CCC 1735 names habit and disordered attachments among factors that can diminish or even remove imputability. The retrieved set covered grave matter and Communion but omitted the paragraph needed to discuss addiction without collapsing objective gravity into subjective mortal guilt. [CCC 1735](https://www.vatican.va/content/catechism/en/part_three/section_one/chapter_one/article_3/i_freedom_and_responsibility.html) |
| Is there a devil? | *Summa Theologiae* I, questions 63 to 64 | The user selected only the Summa. The library contained Aquinas's direct treatment of the fall and punishment of demons, but retrieval returned indirect articles on temptation and Christ's Passion instead. |

There is a pattern here. Exact Catechism paragraphs lost to thematically related passages. Vatican II and modern papal syntheses lost to older sources. Broad questions returned five passages from one source family. Authority, recency, and source-role diversity need to influence ranking, not just semantic resemblance.

Several other theologically incomplete sets were correct within the selected filters. The Fathers-only Eucharist search, for example, returned strong patristic witnesses; it could not return the Catechism or modern papal synthesis. TheoCorpus should preserve the user's filter while making the resulting coverage limit visible and offering to widen the search.

## Ingestion and metadata defects

*Nostra Aetate* is listed in the corpus, but its crucial section 4 is incomplete in the live database. The stored section is only 155 characters and stops after its opening sentence, omitting the council's rejection of collective Jewish responsibility for Christ's Passion. The vendored source file contains the missing text. The Vatican II adapter ingests only the first numbered paragraph of each section and drops its unnumbered continuation paragraphs. This made the document impossible to retrieve usefully for the question about who killed Jesus. Repairing the adapter and republishing Vatican II is more urgent than tuning its rank.

The live Catechism deliberately follows the smallest natural heading-defined sections rather than forcing every numbered paragraph into a separate reader passage. CCC 2413 on gambling therefore sits in the coherent section CCC 2408 to 2414, and CCC 2355 on prostitution sits in CCC 2351 to 2356. That segmentation is not an ingestion defect. It is still a retrieval-granularity tradeoff: paragraph-level secondary retrieval units, or annotations attached to the natural reader passages, would make exact paragraph answers easier to recall without degrading the reader structure.

Document-type metadata is inconsistent. *Evangelii Nuntiandi* and *Evangelii Gaudium* are apostolic exhortations stored in the `encyclicals` collection, while many papal records have no normalized `document_type`. A request for "papal bulls only" therefore cannot be enforced reliably as a hard filter.

## Clear corpus gaps

### 1. CDF and DDF doctrinal documents

This is the most important missing document family. The present collections are rich in papal and conciliar texts but omit many Congregation for the Doctrine of the Faith and Dicastery for the Doctrine of the Faith instructions, declarations, responses, and doctrinal notes.

The frozen-embryo question shows the cost. *Dignitas Personae* 18 to 19 directly discusses cryopreserved embryos and proposed prenatal adoption. The current corpus could retrieve principles about embryonic dignity and artificial procreation, but not the document that actually considers the proposal. The instruction describes the situation as an injustice that cannot be resolved in a morally licit way. It is universal doctrinal guidance from the CDF, approved by Benedict XVI and ordered published. It should rank above commentary or local guidance on this question. [*Dignitas Personae*](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_20081208_dignitas-personae_en.html)

A first CDF or DDF ingestion set should include:

- *Dignitas Personae* and *Donum Vitae* for reproductive technology and embryonic life.
- *Iura et Bona* and *Samaritanus Bonus* for end-of-life questions.
- *Persona Humana* for sexual ethics.
- *Dominus Iesus* for Christ, the Church, and other religions.
- The *Doctrinal Note on Some Aspects of Evangelization* for conversion, witness, conscience, and religious freedom. It would sharpen the Baptist questions even though the current corpus already contains enough material for a good answer. [CDF doctrinal document index](https://www.vatican.va/roman_curia/congregations/cfaith/doc_dottrinali_index.htm), [Doctrinal Note on Evangelization](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_20071203_nota-evangelizzazione_en.html)

Store the issuing body, document type, date, approval note, section number, and authority class. "Vatican document" is too coarse a label.

### 2. Applied Catholic health-care ethics

Ectopic pregnancy exposed a narrower problem. The universal texts in the corpus establish the prohibition of direct abortion and the permissibility of genuinely therapeutic acts whose unintended side effect may be fetal death. They do not give enough case-specific medical analysis for a safe short answer.

The USCCB's *Ethical and Religious Directives for Catholic Health Care Services*, especially directives 47 and 48, are a useful addition for United States users. They distinguish treatment of a proportionately serious pathological condition from an intervention that constitutes direct abortion, then address extrauterine pregnancy. The USCCB approved the sixth edition in plenary assembly and recommends diocesan implementation. That makes it authoritative particular guidance for Catholic health care in the United States. It is not universal Magisterium, and it does not settle every disputed procedure. [USCCB Ethical and Religious Directives, sixth edition](https://www.usccb.org/resources/ethical-religious-directives-catholic-health-service-sixth-edition-2016-06_2.pdf), [USCCB Committee on Doctrine statement on direct abortion and legitimate medical procedures](https://www.usccb.org/resources/direct-abortion-statement2010-06-23)

This material belongs in an authority-labeled health-care guidance collection. It should never appear as though it has the same scope as the Catechism or a universal CDF instruction. Medical queries should also carry a product warning that retrieved moral principles do not replace clinical evaluation.

### 3. Universal governance and disciplinary law outside the Code

Canon 349 correctly surfaced for the question about cardinals electing the pope, but it only states the cardinals' role. *Universi Dominici Gregis* explains the historical and ecclesial rationale and supplies the governing procedure. The current Holy See page incorporates Benedict XVI's amendments through 2013. This is universal disciplinary law in an apostolic constitution, not a doctrine of faith. [*Universi Dominici Gregis*](https://www.vatican.va/content/john-paul-ii/en/apost_constitutions/documents/hf_jp-ii_apc_22021996_universi-dominici-gregis.html)

The gap suggests a document family for apostolic constitutions, motu proprios, and other universal laws that do not sit inside the Code of Canon Law. Authority and effective-date metadata matter because these texts can be amended or superseded.

### 4. Curial studies and technical guidance

The performance-enhancing-drug question needed material on health, fairness, deception, and the rules of sport. CCC 2288 to 2291, already present, covers health and drugs. The Dicastery for Laity, Family and Life's 2018 document *Giving the Best of Yourself* directly discusses doping as contrary to health, fair play, loyalty, and the constitutive rules of sport. This is a useful Holy See study and pastoral document, not an act of universal Magisterium. [*Giving the Best of Yourself*](https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2018/06/01/180601b.html)

The same lower authority tier could hold Pontifical Biblical Commission studies. *The Interpretation of the Bible in the Church* and *The Jewish People and Their Sacred Scriptures in the Christian Bible* would deepen difficult biblical and Jewish-Christian questions. They are expert commission documents, not acts of the Magisterium. TheoCorpus should label them as such and place them below conciliar, catechetical, and papal teaching when answering doctrinal questions. [Pontifical Biblical Commission document index](https://www.vatican.va/roman_curia/congregations/cfaith/pcb_doc_index.htm), [*The Jewish People and Their Sacred Scriptures in the Christian Bible*](https://www.vatican.va/roman_curia/congregations/cfaith/pcb_documents/rc_con_cfaith_doc_20020212_popolo-ebraico_en.html)

## Questions that do not justify a corpus expansion

Two failures call for product behavior rather than new Catholic texts.

- "Do Catholics believe about Mart" needed clarification. Adding more Mary, marriage, or martyrdom documents would make the ambiguity worse.
- "Does the pope have a popemobile?" is a current factual question. A theology corpus should give a scope notice or use a separately identified factual source. It should not fill the answer with canon law about papal authority.

The exhaustive requests also need a different retrieval mode. "All magisterial mentions" and "papal bulls only" require enumeration and hard document-type filters. Five semantic neighbors cannot meet either request, even if the corpus grows.

## Recommended order of work

1. Fix exact-paragraph recall and authority-aware ranking for the Catechism and Vatican II. Start with CCC 2413, 2355, 1735, 1453, 597 to 598, 109 to 119; *Nostra Aetate* 4; *Dei Verbum* 10 to 12; and *Unitatis Redintegratio* 3 to 4 and 19 to 23.
2. Add source-role diversification for broad questions. A Eucharist introduction should not spend all five slots on patristic witnesses when the corpus has Scripture, the Catechism, and current magisterial syntheses.
3. Add a CDF or DDF doctrinal collection, beginning with *Dignitas Personae*. This is the corpus addition most directly supported by the observed questions.
4. Add *Universi Dominici Gregis* and build version-aware metadata for universal disciplinary documents.
5. Add clearly separated particular and technical guidance. Begin with the USCCB health-care directives and the dicastery sport document. Never blend their authority with councils, the Catechism, or universal doctrinal instructions.
6. Add hard filters for issuing body, document type, author, date, and authority level before promising exhaustive or type-constrained research.

The main conclusion is blunt. TheoCorpus found related theology, but too often missed the text that actually answered the question. Corpus expansion matters for modern applied questions. For the sampled failures, however, better retrieval over the library already owned would produce the larger immediate gain.
