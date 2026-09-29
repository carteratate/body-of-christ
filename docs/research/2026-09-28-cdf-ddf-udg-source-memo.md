# CDF, DDF, and *Universi Dominici Gregis*

Research date: 28 September 2026

This memo uses Holy See sources only. It answers the threshold question: what are these sources, and what would TheoCorpus be adding if it included them?

## CDF and DDF

### What the names mean

**CDF** means the Congregation for the Doctrine of the Faith. **DDF** means the Dicastery for the Doctrine of the Faith. They name the same continuing institution of the Roman Curia on opposite sides of the 2022 Curial reform, not two unrelated bodies.

Its institutional predecessors include the Roman Inquisition, founded in 1542, and the Sacred Congregation of the Holy Office, the name adopted in 1908. Paul VI renamed it the Sacred Congregation for the Doctrine of the Faith in 1965. [Official historical profile](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_pro_14071997_en.html)

The transition happened in two steps:

1. Francis's *Fidem servare*, dated 11 February 2022 and effective 14 February, reorganized the then-Congregation into a Doctrinal Section and a Disciplinary Section. It still used the name "Congregation for the Doctrine of the Faith." [Official text of *Fidem servare*](https://www.vatican.va/content/francesco/en/motu_proprio/documents/20220211-motu-proprio-fidem-servare.html)
2. Francis's apostolic constitution *Praedicate Evangelium*, dated 19 March 2022 and effective 5 June, replaced *Pastor Bonus* as the law governing the Roman Curia. Articles 69 through 78 call the office the "Dicastery for the Doctrine of the Faith" and retain the two-section structure. [Official text of *Praedicate Evangelium*](https://www.vatican.va/content/francesco/en/apost_constitutions/documents/20220319-costituzione-ap-praedicate-evangelium.html)

For corpus metadata, `CDF` and `DDF` should therefore be aliases under one institutional identity. Each document should still retain the issuer name printed at publication.

### What the office does

Article 69 of *Praedicate Evangelium* assigns the DDF the task of helping the Pope and bishops promote and safeguard Catholic teaching on faith and morals, drawing on the deposit of faith and addressing new questions. The Doctrinal Section studies faith, morals, and theology, examines problematic writings and opinions, and reviews other Curial documents that concern faith and morals. The Disciplinary Section handles delicts reserved to the DDF and the canonical proceedings attached to them. [*Praedicate Evangelium*, arts. 69-76](https://www.vatican.va/content/francesco/en/apost_constitutions/documents/20220319-costituzione-ap-praedicate-evangelium.html#Dicastery_for_the_Doctrine_of_the_Faith)

The Pontifical Biblical Commission and International Theological Commission are established within the DDF, but article 77 says each operates under its own approved norms. Their publications therefore need their own authorship and authority metadata. They should not silently inherit a DDF document label. [*Praedicate Evangelium*, art. 77](https://www.vatican.va/content/francesco/en/apost_constitutions/documents/20220319-costituzione-ap-praedicate-evangelium.html#Dicastery_for_the_Doctrine_of_the_Faith)

### What kinds of documents it publishes

The DDF's official complete list includes declarations, instructions, doctrinal notes, notes, responsa to dubia, letters, notifications, decrees, norms, rescripts, vademecums, statements, press releases, presentations, and commentary. These are different acts with different purposes. The index itself distinguishes formal documents from presentations, press conferences, and other accompanying material, and gives Acta Apostolicae Sedis citations when available. [Official DDF document index](https://www.vatican.va/roman_curia/congregations/cfaith/doc_doc_index.htm)

Document type alone does not settle the authority of every proposition in a text. *Donum veritatis* says that one must consider the proper character of each exercise of the Magisterium and the extent to which its authority is engaged. It distinguishes infallibly proposed teaching, definitive teaching, non-definitive authentic teaching, disciplinary decisions, and prudential interventions. It also states that CDF documents expressly approved by the Pope participate in the Pope's ordinary magisterium. [*Donum veritatis*, 15-18 and 23-24](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_19900524_theologian-vocation_en.html)

The DDF's doctrinal commentary on the *Professio fidei* gives the corresponding distinctions in assent: theological faith for divinely revealed doctrine, firm and definitive assent for doctrine definitively proposed, and religious submission of will and intellect for non-definitive authentic teaching. [Doctrinal commentary on the *Professio fidei*, 5-10](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_1998_professio-fidei_en.html)

### Does this material belong in TheoCorpus?

Selected DDF and CDF texts belong if TheoCorpus intends to answer Catholic doctrinal and moral questions from authoritative sources. The office's remit directly covers those subjects. For example, the 1987 instruction [*Donum vitae*](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_19870222_respect-for-human-life_en.html) addresses respect for nascent human life and the dignity of procreation. The 2008 instruction [*Dignitas personae*](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_20081208_dignitas-personae_en.html) states that *Donum vitae* remains valid and addresses later bioethical questions, including cryopreservation and proposals for prenatal adoption. *Dignitas personae* also records Benedict XVI's express approval and order that it be published. These texts answer some modern bioethical questions more specifically than the Catechism or an encyclical can.

Ingesting the entire official index into one flat doctrinal collection would be a mistake. The index also contains disciplinary procedure, case-specific decisions, apparition judgments, administrative acts, press releases, and remarks by the Prefect. A defensible first scope is:

- formal doctrinal declarations, instructions, notes, responsa, and broadly addressed doctrinal letters;
- current canonical or disciplinary norms only if TheoCorpus intends to cover Church law and governance;
- case-specific and administrative material only when there is a demonstrated search need;
- press releases, presentations, interviews, and Prefect speeches as commentary, never as equivalent to the underlying document;
- Pontifical Biblical Commission and International Theological Commission texts under their actual institutional authors, with a lower or separately described source role unless the text itself establishes something more.

Every record should capture the issuing body and name at publication, document genre, date, official language or translation, papal approval wording when the source supplies it, Acta Apostolicae Sedis citation, amendment or supersession relationships, and a source-role or authority field. "Published on the DDF page" is not an adequate authority classification.

## *Universi Dominici Gregis*

### What it is

*Universi Dominici Gregis* is John Paul II's apostolic constitution of 22 February 1996 "On the Vacancy of the Apostolic See and the Election of the Roman Pontiff." It is universal papal legislation for a sede vacante and conclave, not a general doctrinal treatise. It governs the limited powers of the College of Cardinals during the vacancy, preparatory congregations, offices that continue or cease, funeral arrangements, electors, conclave secrecy and logistics, voting, acceptance, and proclamation of the elected Pope. [Official consolidated English text](https://www.vatican.va/content/john-paul-ii/en/apost_constitutions/documents/hf_jp-ii_apc_22021996_universi-dominici-gregis.html)

The genre matters. An apostolic constitution is a solemn papal legislative instrument, and this constitution expressly prescribes the norms to be followed during the vacancy and election. Its provisions answer questions about papal elections and sede vacante governance directly. They should not be ranked as if they were doctrinal definitions about faith or morals.

### Amendments and current text

The official Vatican page presents a consolidated version current from 22 February 2013 and links the original 1996 version and both amendments:

- Benedict XVI's 11 June 2007 motu proprio *De aliquibus mutationibus in normis de electione Romani Pontificis* replaced number 75 so that a two-thirds majority remains necessary even after prolonged inconclusive balloting. [Official Latin text](https://www.vatican.va/content/benedict-xvi/la/motu_proprio/documents/hf_ben-xvi_motu-proprio_20070611_de-electione.html)
- Benedict XVI's 22 February 2013 motu proprio *Normas nonnullas* replaced several provisions and incorporated the 2007 rule. The Vatican's consolidated page identifies numbers 35, 37, 43, 46 section 1, 47, 48, 49, 50, 51 section 2, 55 section 3, 62, 64, 70 section 2, 75, and 87 as modified. [Official text of *Normas nonnullas*](https://www.vatican.va/content/benedict-xvi/en/motu_proprio/documents/hf_ben-xvi_motu-proprio_20130222_normas-nonnullas.html)

The Holy See used and linked *Universi Dominici Gregis* for the 2025 vacancy and conclave. During that vacancy, the General Congregation of Cardinals stated that Francis had dispensed from the 120-elector limit in number 33 by creating more than 120 cardinal electors. That was a reported dispensation in the concrete 2025 situation, not a textual amendment to the constitution. [Holy See 2025 sede vacante page](https://www.vatican.va/content/vatican/en/special/sede-vacante/sede-vacante-2025.html) and [Declaration of the Congregation of Cardinals, 30 April 2025](https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2025/04/30/250430a.html)

### Does it belong in TheoCorpus?

Yes, if TheoCorpus covers canon law, papal governance, or common questions about how a pope is elected. It is the controlling primary source for those questions and is more useful than trying to infer conclave procedure from the 1983 Code alone.

The corpus should ingest the current 2013 consolidated text as the searchable default. It should retain the 1996 original and the 2007 and 2013 amending acts as linked historical versions, not mingle obsolete and current provisions without labels. The 2025 declaration should be related application material, clearly marked as a situational dispensation rather than silently rewriting number 33. Retrieval should prefer the consolidated current provision for present-tense questions and expose prior wording only when the query is historical or asks how the law changed.

## Bottom line

- CDF and DDF are one continuing doctrinal institution under pre-2022 and post-2022 names.
- A curated doctrinal subset belongs in TheoCorpus. The whole DDF web index should not receive one authority level.
- *Universi Dominici Gregis* belongs if papal elections and Church governance are in scope. It is legislative material and needs version-aware ingestion.
- Both additions require document-level authority and legal-status metadata. Provenance at the domain or collection level is too coarse.
