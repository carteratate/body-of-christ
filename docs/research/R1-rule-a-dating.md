# R1. Rule A dating and Church-act check

Research for corpus-cleanup item R1 (`docs/corpus-cleanup/P0-checks-identity-research.md`, GitHub issue #144), which blocks 3.1, 3.2 (for the Refutation of All Heresies), 5.6a and 5.6b. Done 4 to 5 October 2026. No production store was queried. The corpus figures come from a master build of the `church-fathers`, `medieval` and `summa` adapters against the vendored sources (135 documents); the other seven collections are Scripture or magisterial texts, which rule A does not cover.

Outcomes the plan already decided are recorded here, not re-argued. Anything that would change a Decision log outcome, and every chronology choice Carter must approve, is under "For Carter" at the end.

## Result in brief

- **Plan's rule A rows reproduced exactly.** Origen 932, Tertullian 192, Novatian 79 + 16, Tatian 44, Arnobius 392 and Alexander of Lycopolis 27 passages, 1,682 in all, match the master build. Tertullian's To His Wife and On the Apparel of Women pass on the named chronology.
- **Three findings would remove more, and are left for Carter.** Hippolytus (the Refutation, 377 passages, plus 115 undatable passages in "Extant Works"), Gregory Thaumaturgus's Panegyric to Origen (37) and Lactantius's Phoenix (4). The Catena Aurea's quotations from Origen and from the Opus imperfectum ("Pseudo-Chrys.") also go to Carter.
- **The six open Index questions are answered.** The Pensées were never on the Index; only Voltaire's annotated edition was (1789). The Provincial Letters were prohibited by Holy Office decree of 6 September 1657. Theologia Germanica's Latin translation by Castellio was prohibited in 1621, and the entry is gone from the 1900 Index. Tyrrell was deprived of the sacraments with his case reserved to the Holy See, 22 October 1907. The Tridentine Index prohibited the Praise of Folly and four other Erasmus titles. No reconciliation of Ockham is documented.
- **No new Church act was found against any corpus author or any candidate the plan keeps.**

## Keying of `datapipeline/registry/rule_a_R1.json`

2.1's `work_id` does not exist yet. On 4 Oct 2026 Carter decided that the file is keyed as follows.

- **Corpus works** by the frozen document ID a master build emits (`document_id`). This part is Carter's choice.
- **Container sub-works (proposed by R1, pending Carter: For Carter item 10).** Container documents whose works get different outcomes also have one sub-entry per ThML work div, keyed by `document_id` plus that `div_id` (Treatises Attributed to Cyprian, Hippolytus's Extant Works, Gregory Thaumaturgus's Acknowledged Writings, Fragments of Lactantius). Every div in those four containers, editorial ones included, has an entry with its passage count; the counts sum to each document's total.
- **Planned candidate works** by `{"author", "title"}` (Carter's choice).

Each entry holds exactly 2.1's `rule_a` object. How the keys are carried into `works.json` is left to the item that merges the file (3.1, or 2.1 if R1 finishes first); this file does not prescribe it.

The file has 216 entries: 135 corpus documents, 39 container sub-works and 42 candidate works. `decision` is `include` for 148, `exclude` for 36 and `null` for 32. A null is one of two things: one of the five container documents, which carry no document-level decision because every work in them has its own sub-entry (Treatises Attributed to Cyprian, Hippolytus's Extant Works, Acknowledged Writings, Fragments of Lactantius, plus the Refutation, a single work held for Carter); or a named "For Carter" item (22 Hippolytus works, the Panegyric, the Phoenix, Theologia Germanica, the Catena's Pseudo-Chrysostom and Theophylact quotations). Editorial divs inside containers (elucidations, a translator's introduction, a general note) are marked `include` for rule A with a basis saying rule G removes them. A null `communion_start` on an `applies: false` entry means the author is presumed in communion.

Two notes on the shape:

- `church_acts[].date` must be ISO, so acts known only to the year use January 1 (Novatian's synod, `0251-01-01`). The `act` text says the day is unknown.
- `communion_start`, `communion_end` and `work_date` are free text where the sources give only a range ("about 207-213"), because 2.1 does not fix their format. 2.1's validator checks ISO dates only for acts.

## Method and sources

**Chronologies.**
- Patristic authors: J. Quasten, *Patrology*, vol. II, *The Ante-Nicene Literature after Irenaeus* (Newman Press, 1953). It is the only standard patrology reachable. It was read through the Internet Archive's search-inside service on item [`patrology0000joha_r2b2`](https://archive.org/details/patrology0000joha_r2b2), whose metadata misdates it 1853. Printed page = scan leaf minus 16, checked against the table of contents (leaf 13) and section heads.
- Modern converts: the conversion or reception date from a biography or the Holy See, and the first-edition date of each work.

**Church acts.** These were searched for every author:
1. *Index librorum prohibitorum* of Pius IX, Rome 1877, which lists all books proscribed up to 1876 ([archive.org](https://archive.org/details/index-librorum-prohibitorum-catholic), OCR text).
2. The Leonine Index, Rome 1900, in its 1901 printing, the base of every later edition to 1948 ([archive.org](https://archive.org/details/indexlibrorumpro0000unse), OCR text).
3. Spot checks in the 1664 Index of Alexander VII ([archive.org](https://archive.org/details/index_librorum_prohibitorum_1664-alexandri_vii)) and the 1841 Index of Gregory XVI ([archive.org](https://archive.org/details/bub_gb_7MPk71j1YEIC)).
4. The DDF's index of doctrinal documents and notifications ([vatican.va](https://www.vatican.va/roman_curia/congregations/cfaith/doc_doc_index.htm), read 5 Oct 2026). Its notifications concern authors after 1966, Faustina Kowalska (1978) and Rosmini (2001). None names another author in this file.

Every author's name, and the Latin or vernacular forms of it, was searched in the OCR texts of items 1 and 2, and each hit was read in context.

**Not reached.**
- The 1948 Index. The archive.org copies of 1938, 1940 and 1948 are lending-only, and their text files return 401 or 500.
- De Bujanda's *Index des livres interdits*, which is not online.
- Statements about the 1948 Index rest on the Leonine Index plus the fact that later editions only added to it. They are marked as such.

## 1. Author list and classification

The classes are: `born` (born in communion), `presumed` (anonymous, pseudonymous or no biography checked; rule A's presumption), `convert-no-pre` (convert-no-pre-baptism-writing), `convert-pre` (convert-with-possible-pre-baptism-writing), `later-break` and `break-return` (break-and-return). One citation is given per classification.

### 1a. Corpus authors (church-fathers, medieval, summa)

| Author (corpus label) | Class | Citation |
|---|---|---|
| Clement of Rome | born / presumed | No evidence of conversion; rule A presumption |
| Mathetes (Diognetus) | presumed | Anonymous (plan, "Labels") |
| Polycarp; Martyrdom of Polycarp | born / presumed | Irenaeus, *Against Heresies* 3.3.4 ([New Advent](https://www.newadvent.org/fathers/0103303.htm)) |
| Ignatius (genuine letters) | presumed | Rule B/C labels are 3.2's job; rule A presumption |
| Barnabas (Pseudo-) | presumed | Pseudonymous (plan, "Labels") |
| Papias | presumed | Rule A presumption |
| Justin Martyr | convert-no-pre | Converted about 130 (*Dialogue* 2-8); earliest extant work the First Apology, about 150-155 |
| Irenaeus | born | Hearer of Polycarp (*Against Heresies* 3.3.4); Doctor 2022 |
| Augustine | convert-pre | Baptized at Easter 387 (*Confessions* 9.6). The corpus holds no Cassiciacum work. City of God, On Christian Doctrine, the Confessions and the NPNF I/3 doctrinal and moral treatises (On the Trinity, Enchiridion, On Catechising, Faith and the Creed, Faith of Things Not Seen, On Continence, Good of Marriage, Holy Virginity, Widowhood, On Lying, Against Lying, Work of Monks, Patience, Care for the Dead) all date from 393 to 427. Checked by listing every chapter label in the two treatise documents. |
| Athanasius | born | Rule A presumption |
| Hermas | presumed | Rule A presumption |
| Tatian | later-break | Irenaeus, *Against Heresies* 1.28.1. Decided: out |
| Theophilus | convert-no-pre | *To Autolycus* 1.14 |
| Athenagoras | convert-no-pre | Quasten I (not opened); Plea about 177. Rule A outcome unaffected: no pre-conversion work exists |
| Clement of Alexandria | convert-no-pre | Quasten II p. 5 (leaf 21): pagan-born; all extant works are Christian. Decided: stays |
| Hippolytus | break-return | Quasten II p. 163 (leaf 179): first antipope, martyred 235; p. 165 (leaf 181): urged his followers to reconcile. **For Carter** |
| Cyprian | convert-no-pre | Baptized about 246 (Pontius, *Life* 2-3; Quasten II, Cyprian section, page not recorded) |
| Caius | presumed | Rule A presumption |
| Novatian | later-break (condemned by name) | Eusebius, *Church History* 6.43. Decided: out |
| "Appendix" (Against Novatian; On Re-baptism) | presumed | Anonymous |
| Gregory Thaumaturgus | convert-pre | Quasten II pp. 123-124 (leaf 139): pagan-born, converted at Caesarea 233-238, given the name Gregory at baptism (date unknown). **For Carter** (Panegyric) |
| Dionysius of Alexandria | born / presumed | Conversion tradition not verified; no outcome turns on it |
| Julius Africanus; Anatolius; Alexander of Cappadocia; Theognostus; Pierius; Theonas; Phileas; Pamphilus; Malchion | presumed | Rule A presumption |
| Archelaus (Hegemonius) | presumed | Plan, "Labels" |
| Alexander of Lycopolis | non-Christian | van Oort 2012. Decided: out |
| Peter of Alexandria; Alexander of Alexandria; Methodius | born / presumed | Rule A presumption |
| Arnobius | convert-pre | Quasten II p. 384 (leaf 400): wrote Against the Pagans to convince the bishop, before reception (Jerome, *Chronicle*). Decided: out |
| Tertullian | later-break (also a convert, with no pre-conversion work extant) | Benedict XVI, [audience of 30 May 2007](https://www.vatican.va/content/benedict-xvi/en/audiences/2007/documents/hf_ben-xvi_aud_20070530.html). Per work, section 2 |
| Minucius Felix | convert-no-pre | *Octavius* 1; Quasten II p. 155 (leaf 171) |
| Commodian | convert-no-pre | His *Instructions*, preface (conversion from paganism). Decided: stays |
| Origen | born; condemned by name | Constantinople II, anathema 11. Decided: out |
| Lactantius | convert-pre | Quasten II pp. 392-395 (leaves 408-411): his first work, the lost *Symposium*, predates his conversion; earliest extant work 303-304. Phoenix **for Carter** |
| Asterius Urbanus | presumed | Anonymous anti-Montanist |
| Victorinus of Pettau | born / presumed | Rule A presumption. Decided: stays |
| Didache; Apostolic Constitutions | presumed | Anonymous; rule B handles the Constitutions |
| Anselm; Bernard; Thomas à Kempis; Thomas Aquinas | born | Rule A presumption (no conversion; all religious from youth) |
| Boethius | born | Rule A presumption. Decided: moves to the Fathers |

Corpus totals: 4 converts with possible pre-baptism writing (Augustine, Gregory Thaumaturgus, Arnobius, Lactantius); 7 converts with no pre-baptism work (Justin, Theophilus, Athenagoras, Clement, Cyprian, Minucius, Commodian; Tertullian, also a convert, is counted under later-break); 3 later-break (Tatian, Novatian, Tertullian); Origen is born in communion and condemned by name; 1 break-and-return (Hippolytus); 1 non-Christian (Alexander of Lycopolis). The rest are born in communion or presumed.

### 1b. Candidate authors (candidates memo, plan's collection table, Catena Aurea sources)

| Author | Class | Citation |
|---|---|---|
| John Henry Newman | convert-pre (also Doctor, 2025) | Received 9 Oct 1845 (*Apologia*, ch. 5, [Gutenberg 22088](https://www.gutenberg.org/ebooks/22088)). Parochial and Plain Sermons out (decided); Apologia 1864, Grammar of Assent 1870, Idea of a University 1852-73, Gerontius 1865 in; Development in its 1878 edition (decided) |
| G. K. Chesterton | convert-pre | Received 30 July 1922 ([Seton Hall Chesterton Institute](https://wsou.shu.edu/chesterton/biographical-note.html)). Orthodoxy (1908) out (decided); Everlasting Man 1925, St Francis 1923, Catholic Church and Conversion 1926, The Thing 1929 in |
| Ronald Knox | convert-pre | Received 1917 ([knoxbible.com](https://knoxbible.com/about_ronald_knox.html); the day was not verified). Belief of Catholics (1927) in |
| F. W. Faber | convert-pre | Received at Northampton, November 1845 ([CE, "Frederick William Faber"](https://www.newadvent.org/cathen/05740c.htm)). All for Jesus 1853, Growth in Holiness 1854 in |
| Edith Stein | convert-pre | Baptized 1 Jan 1922 ([Vatican biography](https://www.vatican.va/news_services/liturgy/saints/ns_lit_doc_19981011_edith_stein_en.html)). Works before then out (decided) |
| Jacques Maritain | convert-pre | Baptized 11 June 1906 ([Notre Dame Maritain Center](https://maritain.nd.edu/about/about-jacques-maritain/)). Candidate titles are 1920s, in |
| Dietrich von Hildebrand | convert-pre | Received Holy Saturday, 11 April 1914 ([Alice von Hildebrand, EWTN](https://www.ewtn.com/catholicism/library/on-the-legacy-of-he-beloved-husband-5539)). Candidates later, in (rights: List B) |
| Augustine Baker (*Holy Wisdom* / *Sancta Sophia*, compiled by Serenus Cressy) | convert-no-pre | Received at Oxford before joining the Benedictines at Padua in 1605; wrote his ascetical treatises at Cambrai from 1624 ([CE, "David Augustine Baker"](https://www.catholic.com/encyclopedia/david-augustine-baker)) |
| Ambrose, Basil, Gregory Nazianzen, John Chrysostom (5.6a) | convert-no-pre, except that Basil's and Gregory Nazianzen's earliest letters need dating if letters are chosen | Baptized as adults, from Christian families (catechumens until then). **Unverified here**; 5.6a must date any letter collection per work from Quasten vol. III |
| Cyril of Jerusalem, Leo, Gregory the Great, Bede, Isidore, John Damascene; Pseudo-Dionysius (5.6a) | born / presumed | Rule A presumption |
| Gregory of Narek | Armenian Church, passes as Doctor (limit 2) | [Apostolic letter, 12 April 2015](https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco_lettera-ap_2015412_gregorius-narecensis-doctor-ecclesiae.html) |
| Teresa of Avila, John of the Cross, Francis de Sales, Catherine of Siena, Thérèse, Alphonsus, Bonaventure, Albert, Anthony, Peter Damian, Hildegard, John of Avila, Canisius, Bellarmine, Lawrence of Brindisi, Bernard, Anselm | born (Doctors; limit 2 applies anyway) | Doctors table in the candidates memo, §2.1 |
| Ignatius of Loyola, Francis of Assisi, Clare, Gertrude, Bridget, Catherine of Genoa, Thomas More, John Fisher, John Vianney, Elizabeth of the Trinity, Louis de Montfort, Faustina | born (saints) | Candidates memo §2.1 (CE and vatican.va links) |
| Julian of Norwich, Hilton, Rolle, *Cloud* author, Ruusbroec, Tauler, Suso, Mechthild, William of St Thierry, Hugh and Richard of St Victor, Aelred, Peter Lombard, Duns Scotus, Guigo, Gerson, Luis of Granada, Scupoli, Caussade, Brother Lawrence, Lallemant, Alphonsus Rodriguez, Challoner, Marmion, Tanquerey, Scheeben, Nieremberg, Möhler, Pohle, Arthur Preuss, Koch, Karl Adam, Gilson, Sheen, Vonier, Garrigou-Lagrange, Guardini, Escrivá, Ratzinger, Balthasar, de Lubac | presumed | Rule A presumption; no biography checked for conversion. Challoner (a convert as a boy) and Arthur Preuss (son of a convert) are **unverified**; their candidate works are adult works, so no outcome turns on it |
| *Little Flowers*, *Mirror of Perfection*, *Theologia Germanica*, Pseudo-Bonaventure, Pseudo-Albert (*On Cleaving to God*) | presumed (anonymous); rule B/C labels by 3.2 | Rule A presumption |
| Pascal | born | Decided: Pensées in, Provincial Letters out (section 3) |
| Eckhart, Abelard, Fénelon, Guyon, Molinos, Jansen, Quesnel, Teilhard, Rosmini, Erasmus, Joachim of Fiore | born (outcome set by the Church acts in section 3) | Candidates memo §4 (CE, papal and DDF sources) |
| Lamennais | later-break (refused reconciliation; buried without rites) | Candidates memo §4 ([1911 Britannica](https://en.wikisource.org/wiki/1911_Encyclop%C3%A6dia_Britannica/Lamennais,_Hugues_F%C3%A9licit%C3%A9_Robert_de)); acts in section 3 |
| Loisy | later-break (excommunicated 1908) | Section 3; limit 1 excludes every work |
| Tyrrell | convert (received 1879) and later-break (1907) | Section 3; limit 1 excludes every work |
| William of Ockham | later-break (excommunicated 1328, no reconciliation documented) | Section 3 |
| Thomas Merton (convert, baptized 1938), C. S. Lewis, Dante | not candidates | Plan and memo: out of scope or decided out |
| Henry Edward Manning; Orestes Brownson | not candidates | Manning appears only as author of a preface (rule G removes it); Brownson is not on the list |
| Catena Aurea sources (5.6b), Matthew and Mark | see "For Carter" | Label counts in section 5 |

The classes the dating method covers (convert-pre, later-break, break-return) hold 19 authors across the corpus and the candidates, 21 if 5.6a takes Basil's and Gregory Nazianzen's early letters: corpus, Augustine, Gregory Thaumaturgus, Arnobius, Lactantius, Tatian, Novatian, Tertullian and Hippolytus (8); candidates, Newman, Chesterton, Knox, Faber, Stein, Maritain, von Hildebrand, Lamennais, Loisy, Tyrrell and Ockham (11). For the last four, Church acts decide the outcome before any dating. That matches the Decision log's estimate of about 20.

## 2. Dated authors: chronology, communion dates and per-work results

### Tertullian (later-break)

- **Chronology:** Quasten II, pp. 290-319, cross-checked against Barnes, *Tertullian* (1971; 2nd ed. 1985). Barnes could not be opened (see "Could not verify"), so the cross-check uses the disagreement Quasten himself reports.
- **Communion:** convert before about 197; all extant works are Christian. **Break:** Quasten puts the "definite break" before about 213 (p. 318, leaf 334: Concerning Ecstasy was written after it, about 213). He calls the period from about 207 "semi-Montanistic". The break date is itself disputed (about 207 to about 213), so any work in that window falls on a disputed side.

| Work (passages) | Date (Quasten) | Result |
|---|---|---|
| To His Wife (22) | 200-206, written as a Catholic (p. 302) | **include** |
| On the Apparel of Women (28) | after De oratione (198-200); Quasten says Montanist ideas are completely absent (pp. 294-295) | **include** |
| On Exhortation to Chastity (21) | 204-212; he finds no evidence that Tertullian had yet left the Church (p. 305) | exclude: other chronologies class it Montanist, so sources disagree |
| On the Veiling of Virgins (26) | before the formal break at Carthage, but with Montanist appeals (pp. 306-307) | exclude: as above |
| De Fuga in Persecutione (17) | 212, Montanist point of view (p. 310) | exclude |
| On Monogamy (29) | about 217, after he joined the Montanists (p. 305) | exclude |
| On Fasting (29) | Montanist, against the "psychici" (p. 312) | exclude |
| On Modesty (55) | Montanist; against a bishop's edict, often taken as Callistus's (pp. 312-314) | exclude |
| On the Pallium (15) | no date recovered from Quasten; dates proposed in the literature range widely | exclude: not datable (the Decision log names it) |

Total excluded: 192, as the plan says. Quasten alone would also admit Exhortation to Chastity and Veiling of Virgins, and perhaps De Fuga, because he places the break later than the others do. Rule A's "standard sources don't disagree" condition keeps them out (see "For Carter", item 4).

### Hippolytus (break-return): see "For Carter", item 1

- **Chronology:** Quasten II, pp. 163-207.
- **Communion:** born in communion. In schism from the election of Callistus (217) to his deportation with Pontian in 235. Reconciled before death: the Liberian Catalogue and Damasus's epigram, via Quasten p. 165 and the rule-1 memo §7(f).

| Work (passages) | Date | Rule A as written |
|---|---|---|
| Refutation of All Heresies (377) | after 222, since it narrates Callistus's episcopate of 217-222 (Quasten pp. 166-169); "220s" (Litwa, via [BMCR 2016.12.05](https://bmcr.brynmawr.edu/2016/2016.12.05/)) | exclude |
| Christ and Antichrist (26) | about 200 (p. 170) | include |
| On Daniel, fragments (29) | about 204 (p. 171) | include |
| Against Plato, on the Universe (3) | before 225 (p. 196) | exclude (straddles 217) |
| Against Noetus (17) | Quasten reports that it may be the end of the early Syntagma, of Zephyrinus's time (199-217), but hedges ("perhaps"; p. 180) | exclude (not shown before 217) |
| Other exegetical fragments, doubtful Pentateuch fragments, Against the Jews, Against Beron and Helix, Theophany, homily and other fragments (95) | undated, or doubtful attribution | exclude (undatable) |
| Elucidation (1) | editor's text | rule G, not rule A |
| Appendix of dubious and spurious pieces (57) | not Hippolytus's | rule A presumption (anonymous); rules B and C by 3.2 |

### Gregory Thaumaturgus (convert-pre): see "For Carter", item 2

- **Chronology:** Quasten II, pp. 123-128.
- **Communion:** converted at Caesarea during 233-238; baptism undated. The CE ([Leclercq](https://www.newadvent.org/cathen/07015a.htm)) gives 231-238/239 and also gives no baptism date.
- The Panegyric to Origen (Argument I-XIX, 37 passages) was delivered on leaving Caesarea in 238. Rule A as written: exclude, because no source places it after baptism.
- The Declaration of Faith, the Metaphrase of Ecclesiastes and the Canonical Epistle (32 passages) are episcopal works from after about 240: include.
- The plan's corrections section counts the Argument passages as 38; the master build has 37, with 3 Elucidations alongside.

### Lactantius (convert-pre)

- **Chronology:** Quasten II, pp. 392-410.
- **Communion:** converted at Nicomedia about 300; baptism undated. The plan settles that he wrote his prose works as a baptized Christian.
- On the Workmanship of God (303-304, his earliest extant work), the Divine Institutes, On the Anger of God (313-314) and On the Deaths of the Persecutors: **include**.
- The Phoenix (4): **For Carter**, item 3. Quasten (pp. 403-404) discusses its Christian symbolism but gives no date, and the studies he lists question the attribution.
- The Poem on the Passion (2): a doubtful attribution, include. If it is not his, it is an anonymous Christian poem.

### Augustine (convert-pre)

No pre-baptism work is in the corpus (section 1a). All include.

### Arnobius, Tatian, Novatian (decided)

- **Arnobius:** written before his reception (Jerome, *Chronicle*; Quasten p. 384). Exclude 392.
- **Tatian:** break after Justin's death, about 172; the Address's date is disputed. Exclude 44.
- **Novatian:** condemned by name in 251, so every work is excluded, including the two treatises inside "Treatises Attributed to Cyprian" (I, On the Public Shows, `div iv.vii.ii`, 8; III, On Chastity, `iv.vii.iv`, 8). Exclude 79 + 16.

### Modern converts

- **Newman:** received 9 Oct 1845. Apologia 1864, Grammar of Assent 1870, Idea of a University 1852-73 and Gerontius 1865 are after his reception: include. Development is taken in the 1878 revision (decided). Parochial and Plain Sermons (1834-43): exclude (decided).
- **Chesterton:** received 30 July 1922. Orthodoxy (1908): exclude (decided). St Francis 1923, Everlasting Man 1925, Catholic Church and Conversion 1926 and The Thing 1929 (UK edition): include.
- **Knox** (1917; Belief of Catholics 1927), **Faber** (Nov 1845; 1853, 1854), **Maritain** (1906; 1920s titles) and **von Hildebrand** (1914; later works): all candidate works are later than their reception. Include.
- **Stein:** baptized 1 Jan 1922. Exclude earlier works (decided).

## 3. Church-act search, per author

Sources searched for every author are listed under "Method". "None found" means no entry for the author or the work in the 1877 or 1900 Index and no DDF notification. The 1948 Index and De Bujanda were not reached.

### Acts found

| Author / work | Act | Effect | Citation |
|---|---|---|---|
| Origen | Constantinople II, anathema 11 (553) | condemn | [NPNF2 14](https://www.newadvent.org/fathers/3812.htm) |
| Novatian | Roman synod under Cornelius (251) | condemn | [Eusebius, *HE* 6.43](https://www.newadvent.org/fathers/250106.htm) |
| Pascal, *Les Provinciales* | Holy Office, Thursday 6 Sept 1657 (Leonine Index, s.v. "Montalte, Louis de"; also "Lettre … écrite à un provincial"). The Italian version with Nicole's notes: Holy Office, 3 March 1762 | prohibit | [Leonine Index](https://archive.org/details/indexlibrorumpro0000unse); [1877 Index](https://archive.org/details/index-librorum-prohibitorum-catholic) |
| Pascal, *Pensées* | Only "Pensées de Pascal, avec les notes de M. de Voltaire" (Geneva 1778): decree of 18 Sept 1789. The Pensées themselves were never listed | prohibit (that edition only) | same, s.v. "Pascal, Blaise" and "Pensées de Pascal" |
| *Theologia Germanica* | The Latin translation "ex germanico translatus studio Ioannis Theophili" (Sebastian Castellio; Antwerp, Plantin 1558), and the variant "Theologia mystica" by the same translator: decree of 16 March 1621. The 1664 Index also cites an earlier Roman decree, illegible in the OCR. Still in the 1841 and 1877 Indexes; **absent from the Leonine Index of 1900**, whose "Theologey (teutsche) in 100 Capiteln" (decrees of 1612 and 1616) is a different book, Berthold of Chiemsee's *Tewtsche Theologey*. The original German text was never listed by that name | prohibit (one Latin translation) | [1841 Index](https://archive.org/details/bub_gb_7MPk71j1YEIC), s.v. "Theologia germanica"; [1664 Index](https://archive.org/details/index_librorum_prohibitorum_1664-alexandri_vii); [Leonine Index](https://archive.org/details/indexlibrorumpro0000unse) |
| George Tyrrell | 22 Oct 1907. Bishop Amigo of Southwark wrote that Tyrrell's case had been laid before Pius X, and the answer was privation of the sacraments with the case reserved to the Holy See. Amigo then told the press it was not an excommunication but a prohibition from the sacraments. Tyrrell himself called it an excommunication, universal and not diocesan. The *Concise Oxford Dictionary of World Religions* calls it "minor excommunication". Refused Catholic burial, 1909 | condemn (papal; communicated by the local bishop) | M. D. Petre, *Autobiography and Life of George Tyrrell*, vol. 2 (1912), pp. 341-343, [archive.org](https://archive.org/details/a611438902tyrruoft); NCE via [Encyclopedia.com](https://www.encyclopedia.com/environment/encyclopedias-almanacs-transcripts-and-maps/tyrrell-george) |
| Alfred Loisy | Holy Office, 7 March 1908, excommunication *vitandus* | condemn | NCE via [Encyclopedia.com](https://www.encyclopedia.com/humanities/encyclopedias-almanacs-transcripts-and-maps/loisy-alfred-1857-1940) |
| Teilhard de Chardin | Holy Office monitum, 30 June 1962 (AAS 54 [1962] 526); communiqué of July 1981 | warn | EWTN text of the monitum and the 1981 statement, [archived copy](http://web.archive.org/web/20250917144035/https://www.ewtn.com/catholicism/library/monitum-on-the-writings-of-fr-teilhard-de-chardin-sj-2144) (the live page now returns 404); official text in [AAS 54 (1962)](https://www.vatican.va/archive/aas/documents/AAS-54-1962-ocr.pdf), p. 526, not opened |
| Rosmini | Holy Office, *Post obitum* (14 Dec 1887); CDF note of 1 July 2001 | condemn, then lift | [vatican.va](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_20010701_rosmini_en.html) |
| Faustina Kowalska | Holy Office notification (1959); S. C. Doctrine of the Faith, 15 April 1978 | prohibit, then lift | [vatican.va](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_19780415_kowalska_en.html) |
| Fénelon, *Explication des maximes des saints* | Brief of Innocent XII, 12 March 1699 | condemn | Leonine Index, s.v. "Fénélon" |
| Molinos, *Opera omnia* | Holy Office, 28 Aug 1687; bull of Innocent XI, 20 Nov 1687 (*Caelestis Pastor*) | prohibit, condemn | Leonine Index, s.v. "Molinos" |
| Guyon, *Moyen court* | Holy Office, 3 May 1689 (year read from damaged OCR) | prohibit | Leonine Index, s.v. "Moyen court" |
| Jansen, *Augustinus* | Holy Office, 1 Aug 1641; bull of Urban VIII, 6 March 1642 (*In eminenti*) | prohibit, condemn | Leonine Index, s.v. "Iansenius, Cornelius" |
| Quesnel, *Réflexions morales* | Brief of Clement XI, 13 July 1708; bull *Unigenitus*, 8 Sept 1713 | condemn | Leonine Index, s.v. "Quesnel" |
| Lamennais, *Paroles d'un croyant* | Gregory XVI, *Singulari nos*, 25 June 1834 | condemn | Leonine Index; [text](https://www.papalencyclicals.net/greg16/g16singu.htm) |
| Erasmus | The Tridentine Index (1564), as carried in the 1877 Index: Colloquia, Moriae encomium (Praise of Folly), Lingua, Christiani matrimonii institutio and De interdicto esu carnium prohibited; the Adagia unless in Manutius's edition; the Italian paraphrase of Matthew; works on religion "donec expurgentur". The 1559 Pauline Index's first-class listing of all his works is reported widely but was not checked. **No Erasmus entry in the Leonine Index.** That omission does not lift the prohibition: Leo XIII's *Officiorum ac munerum* (1897), General Decrees art. 1, printed in the Leonine Index's front matter, keeps every book condemned by popes or ecumenical councils before 1600 condemned even when the new Index does not list it | prohibit | [1877 Index](https://archive.org/details/index-librorum-prohibitorum-catholic), s.v. "Erasmus Desider." |
| William of Ockham | Excommunicated 6 June 1328 for leaving Avignon without leave (John XXII). **No reconciliation documented.** Wadding read Clement VI's letter *Petitio pro parte tua* (8 June 1349), absolving a "Guilelmus de Anglia", as Ockham's reconciliation. G. Gál's article ("William of Ockham Died 'Impenitent' in April 1347", *Franciscan Studies* 42, 1982, 90-95; record at [PhilPapers](https://philpapers.org/rec/GLWOO)) is reported to show that the letter concerns another friar and that Ockham died in April 1347. This rests on the article's title and on summaries of it; R1 did not read the article | condemn, never lifted | [SEP, "William of Ockham"](https://plato.stanford.edu/entries/ockham/) (rev. 2024) |
| Meister Eckhart | John XXII, *In agro dominico*, 27 March 1329: 28 articles, the bull naming him | condemn | [CE](https://www.newadvent.org/cathen/05274a.htm); not in the Index lists |
| Peter Abelard | Innocent II's rescript after Sens (1140 or 1141) imposed silence on him by name | condemn | [CE](https://www.newadvent.org/cathen/01036b.htm) |
| Joachim of Fiore | Lateran IV (1215), canon 2 | condemn (one treatise) | [CE](https://www.newadvent.org/cathen/08406c.htm) |

### Index entries that do not touch a candidate work

- **Thomas à Kempis:** only Castellio's Latin version *De imitando Christo* is listed (Leonine Index, s.v. "Thomas Kempisius"; decree date OCR-damaged, read as 1723). The corpus uses the Bruce English edition, so it is not affected.
- **Tauler:** the hit is an Italian novena citing him (Holy Office, 5 Feb 1688), not his work.
- **Gerson:** the hit is Le Noble's *L'Esprit de Gerson* (1704), not his work.
- **Nieremberg:** the hit is his *Vida de s. Ignacio* (donec corrigatur, 1642), not the work Scheeben adapted.
- **Others:** the hits on Bellarmine, Möhler, Liguori and Rosmini are books about them or against them.

### None found

No act or Index entry was found for:

- every other corpus author in section 1a, including Clement of Alexandria, Lactantius, Commodian, Victorinus, Cyprian, Hippolytus and Gregory Thaumaturgus (rule-1 memo §8 agrees);
- every other candidate in section 1b, including Newman, Chesterton, Knox, Faber, Stein, Maritain, von Hildebrand, Marmion, Tanquerey, Scheeben, Möhler, Garrigou-Lagrange, Caussade, Scupoli, Lallemant, Luis of Granada, Brother Lawrence, Montfort, Suso, Ruusbroec and Julian;
- the Opus imperfectum in Matthaeum. Benedict XIV's *Sollicita ac provida* (1753), printed at the front of the Leonine Index, quotes it approvingly.

## 4. Passage counts against the plan's table

| Plan row | Plan | Master build | Note |
|---|---|---|---|
| Origen, 3 works | 932 | 932 (De Principiis 262, Letter to Gregory 4, Against Celsus 666) | match |
| Tertullian, 7 of 9 | 192 | 192 | match; To His Wife (22) and Apparel (28) confirmed in |
| Novatian, 2 works + Treatises I and III | 79 + 16 | 79 + 16 | match |
| Tatian | 44 | 44 | match |
| Arnobius | 392 | 392 | match |
| Alexander of Lycopolis | 27 | 27 | match |
| **Rule A total** | 1,682 | 1,682 | |
| *Not in the plan: For Carter* | | Refutation 377; other Hippolytus 115; Panegyric 37; Phoenix 4 | 533 more if Carter applies rule A as written |

## 5. For Carter

Each item has a recommendation. No change was made to the plan.

1. **Hippolytus.** He was in schism from 217 until about 235, is not a Doctor and was never condemned. Rule A as written removes the Refutation (377) and 115 undated passages of "Extant Works", 492 in all, and keeps Christ and Antichrist (26) and On Daniel (29). The Refutation's authorship is also disputed; if it is not his, its author led a Roman schismatic group (Litwa), so the outcome is the same.
   - **Recommendation:** apply the rule as written, which keeps the method's single standard. 3.2 then labels the Refutation only if Carter keeps it.
   - The alternative is to treat a schismatic later reconciled and venerated as a saint like a Doctor. That would be a new limit to rule A.
2. **Gregory Thaumaturgus, Panegyric to Origen (37).** Delivered in 238 after his conversion, but no source dates his baptism.
   - **Recommendation:** exclude, as the method directs ("errors fall toward exclusion"). Keep the 32 episcopal-period passages.
3. **Lactantius, The Phoenix (4).** Its date relative to his conversion is not established, and the attribution is questioned.
   - **Recommendation:** exclude. The Decision log's "Lactantius stays" concerns the author; the dating method still applies per work.
4. **Chronology choices.**
   - **Tertullian:** Quasten (1953) puts the break about 212-213, Barnes and others about 207. **Recommendation:** name Quasten as the registry chronology, the only one read, and keep the "sources disagree" exclusions (Exhortation to Chastity, Veiling of Virgins, De Fuga), giving 192.
   - **Hippolytus, Gregory Thaumaturgus and Lactantius:** **recommendation:** Quasten vol. II.
   - **Modern converts:** **recommendation:** the date of reception plus the first edition, as recorded.
5. **Catena Aurea, Pseudo-Chrysostom quotations** (5.6b). The Oxford translation that the candidates memo lists (CCEL `catena1` and `catena2`) already labels them "Pseudo-Chrys.": 439 quotations in Matthew and 109 in Mark by paragraph-label count. Luke and John were not counted (scans only). The source is the Opus imperfectum in Matthaeum, by an Arian bishop or priest of the second or third quarter of the fifth century, from the Latin-Greek border region (J. van Banning, CCSL 87B, *Praefatio*, 1988, [Brepols](https://www.brepols.net/products/IS-9782503008752-1)). No Church act names it.
   - **Rule B:** R1 found no statement that the work's own text names Chrysostom; the attribution is the manuscripts' and the Catena's. Not checked against the CCSL text. So B probably does not remove it.
   - **Rule A:** the author was outside communion, an Arian, and the presumption for unknown authors does not cover a known Arian.
   - **Recommendation:** exclude these quotations. If Carter keeps them, label them "Pseudo-Chrysostom (Opus imperfectum, an Arian commentary)".
6. **Catena Aurea, Origen quotations** (new). The Catena quotes Origen 308 times in Matthew, 11 in Mark (label count), plus 18 "Pseudo-Origen". Each quotation is attributed to the Father quoted (Decision log), and limit 1 excludes every work of Origen's.
   - **Recommendation:** exclude the Origen quotations under limit 1. "Pseudo-Origen" quotations need an authorship check in 5.6b.
7. **Catena Aurea, other sources** (new, for 5.6b):
   - **Theophylact of Ohrid** (365 in Mark), a Byzantine archbishop writing after 1054. No act names him. The plan's Gregory of Narek limit implies that churches not in communion fail rule A. **Recommendation:** treat Theophylact as not in communion and exclude, unless Carter reads the presumption to cover him.
   - **Josephus** (1 in Matthew), non-Christian: exclude.
   - **"Euseb."** (4), Eusebius of Caesarea: no act condemning him by name was checked. 5.6b should check Nicaea II's treatment of him before ingesting.
8. **Theologia Germanica.** Only Castellio's Latin translation was prohibited (1621), and the entry is absent from the 1900 Index. An English translation from the German (for example Winkworth, 1854) is not the prohibited text. **Recommendation:** rule A does not bar it. It stays out today only because nobody has proposed it (memo: "exclude unless researched").
9. **Authors named in a condemnation of their propositions** (Eckhart, Abelard). Limit 1 excludes "every work" when an act condemned the author by name. John XXII's bull names Eckhart while condemning his articles; Innocent II's rescript names Abelard and imposes silence on him.
   - **Recommendation:** read these as condemnations of named authors, which excludes all their works. That matches the memo's recommendations, and neither is a live candidate.
   - **Joachim of Fiore is different.** Lateran IV, canon 2, condemned one treatise of his, not the author, and he had submitted all his writings to the Holy See in 1200 ([CE](https://www.newadvent.org/cathen/08406c.htm)). Limit 1 by name is doubtful for him. His exclusion stands on the candidates memo's grounds (no usable English) and on the condemned treatise itself.
   - Fénelon (whose brief condemns one book and who submitted) stays limited to that book, as decided.
10. **Rule A key format.** The container sub-entries (`document_id` plus `div_id`) go one step beyond Carter's 4 Oct choice, because Novatian's treatises, Hippolytus and the Panegyric sit inside container documents. **Recommendation:** accept them.

## Could not verify

- **The 1948 Index** (lending-only on archive.org) and **De Bujanda's Index volumes**. Statements on the 1948 Index rest on the Leonine Index (1900).
- **Barnes, *Tertullian*** (1971/1985), and the ODCC, CPG and Altaner. Barnes is on archive.org (`tertullianhistor0000barn`, `tertullianhistor0000timo`) but lending-only, and its search-inside service returned 403 on 5 Oct 2026. So the exclusions of Exhortation to Chastity and Veiling of Virgins rest on Quasten's own report of a Montanist-leaning period and of other views, not on a second chronology R1 read.
- **Exact days:**
  - Knox's reception (year only).
  - Abelard's rescript (1140 or 1141).
  - The Kempis-Castellio decree year (OCR).
  - The Faustina 1959 notification (cited from the 1978 document).
- **Quasten page numbers** are derived from scan leaves (offset 16, checked at three section heads), not from page images.
- **Conversion facts:** Challoner, Arthur Preuss, Dionysius of Alexandria, and the baptism dates of Basil and Gregory Nazianzen. 5.6a must date any early letters.
- **Catena counts** are paragraph-label counts in the CCEL ThML files (Matthew and Mark only). Luke and John exist only as scans.

## Files

- `datapipeline/registry/rule_a_R1.json`: 216 entries, as described above.
- Build used: master adapters at `9f3e19e`, vendored sources from the main checkout (not committed).
