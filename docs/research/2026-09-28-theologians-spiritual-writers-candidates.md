# Theologians and spiritual writers, candidate works and how to get them legally

Research date: 28 September 2026

This memo lists candidate works for the collection now called "Theologians and spiritual writers" (formerly `medieval`). It sorts them by how we could legally get an English text, checks each author against the content rules, and records the signals that should decide priority.

The Church Fathers collection covers writers up to about 750 and the Summa is its own collection, so both are out of scope here except where a boundary call is needed (section 5).

## How this was checked

- **CCEL.** For every CCEL work named below I downloaded the ThML file (`https://ccel.org/ccel/<letter>/<author>/<work>.xml`) and read its header (`DC.Rights`, `published`, `comments`) and its title page. Word counts are counts of the body text of that file. A ThML entry here means I fetched the file and it contains real text, not page images.
- **Project Gutenberg.** Edition details come from the Gutenberg catalogue record and the title page of the plain-text file. Gutenberg only posts texts it has cleared as US public domain, but I still read the title page for the year.
- **Internet Archive.** Edition details come from the item's metadata (title, date, publisher, page count). Items marked "scan" are page images with OCR text. I checked that the items listed are open to download, not lending-only. I did not read the OCR quality of each scan; treat OCR as unknown unless noted.
- **CCC citations.** Counted from the footnotes of the Catechism already vendored at `datapipeline/sources/catechism/ccc.json` (3,728 footnotes, Libreria Editrice Vaticana text). A count is the number of footnotes that name the author. It misses quotations whose footnote cites only the Liturgy of the Hours, so treat each figure as a floor.
- **US public domain.** Cornell's copyright chart, current as of 1 January 2026, says works published before 1931 are public domain in the US, whether published here or abroad. Works published 1931-1963 are public domain only if the US copyright was not renewed. Foreign works published 1931-1977 had their US copyright restored by the URAA if they were still protected at home on 1 January 1996, and then run 95 years from publication. [Cornell University Library, "Copyright Term and the Public Domain in the United States"](https://guides.library.cornell.edu/copyright/publicdomain). In practice the rule this memo applies is simple. A translation first published in 1930 or earlier is safe. Anything later needs a renewal search (US) or is probably restored (UK and Europe).
- **Life dates and saint status** come from the CCEL, Gutenberg and Catholic Encyclopedia catalogue records cited in each row, and from the Vatican documents in the Doctors table.

Nothing here was published or ingested. The only repository change is this file.

---

## 1. Summary

### Counts

| List | What it holds | Count |
|---|---|---|
| A1 | Available now, CCEL ThML (our existing ingest format) | 27 works |
| A2 | Available now, Gutenberg text or Internet Archive scan | 58 works |
| B | Needs payment or permission (or a renewal search before use) | 37 authors or author groups |
| C | Flagged or excluded (17 persons, 10 authorship items, 5 scope calls, 12 rights flags) | 44 items |

Five problems turned up in files we already ingest or were about to ingest. They are in section 4 (rights flags) and in the open questions.

- The vendored Boethius is the W. V. Cooper translation (Dent, 1902), not H. R. James. The file's title page says so.
- The vendored *Imitation of Christ* is the Bruce 1940 edition. It is public domain only because nobody renewed it. CCEL's header records a renewal search that found no renewal.
- The vendored *On Loving God* names no translator. It came via Paul Halsall's etext. The translation should be identified before we display a credit.
- CCEL's *Ascent of Mount Carmel*, *Dark Night* and *Way of Perfection* are E. Allison Peers's translations (Image Books reprints of the 1950s-60s). CCEL calls them public domain, but Peers's UK translations were very likely restored under the URAA. Use the David Lewis translations instead.
- CCEL's Chesterton *St. Thomas Aquinas* is marked public domain but was published in 1933. It stays under US copyright until 1 January 2029.

### Top 15 recommendations

Every item below is public domain in the US on the evidence in List A.

| # | Work | Why |
|---|---|---|
| 1 | Teresa of Avila, *Interior Castle* (Stanbrook, 1921) | Doctor; the standard map of prayer; CCEL ThML ready |
| 2 | Teresa of Avila, *Life* (Lewis, 1904) | Doctor; cited in the CCC on prayer; CCEL ThML ready |
| 3 | John of the Cross, *Ascent*, *Dark Night*, *Spiritual Canticle*, *Living Flame* (Lewis) | Doctor; five CCC citations; Canticle is CCEL ThML, the rest are in an 1864 scan |
| 4 | Francis de Sales, *Introduction to the Devout Life* | Doctor; the lay spirituality classic; CCEL ThML ready |
| 5 | Francis de Sales, *Treatise on the Love of God* (Mackey, 1884) | Doctor; cited by the CCC; CCEL ThML ready |
| 6 | Catherine of Siena, *Dialogue* (Thorold) | Doctor; three CCC citations; CCEL ThML ready |
| 7 | Julian of Norwich, *Revelations of Divine Love* (Warrack, 1901) | CCC 313; suffering and providence; CCEL ThML ready |
| 8 | Thérèse of Lisieux, *Story of a Soul* (Taylor, 1912) | Doctor; six CCC citations, the most of any modern writer here; CCEL ThML ready |
| 9 | Ignatius of Loyola, *Spiritual Exercises* (Mullan, 1914) and *Autobiography* | Two CCC citations; the discernment text; CCEL ThML ready |
| 10 | Alphonsus Liguori, *Glories of Mary*, *Visits to the Blessed Sacrament*, *Preparation for Death*, *Uniformity with God's Will* | Doctor; Mary, the Eucharist, death, God's will; Gutenberg text plus Centenary Edition scans |
| 11 | Louis de Montfort, *True Devotion to the Blessed Virgin* (Faber, 1863) | Named by John Paul II in *Redemptoris Mater* and *Rosarium Virginis Mariae*; Marian consecration |
| 12 | Newman, *Parochial and Plain Sermons*, *Apologia*, *Grammar of Assent*, *Development of Christian Doctrine* | Doctor since 2025; four CCC citations; apologetics and conscience |
| 13 | Bernard, *Sermons on the Song of Songs*, *On Consideration*, *On Grace and Free Choice* | Doctor; *Doctor Mellifluus*; fills out an author we already hold |
| 14 | Three short practical classics (Scupoli's *Spiritual Combat*, 1846; Caussade's *Abandonment*, 1887; Brother Lawrence's *Practice of the Presence of God*, Revell) | Answer everyday questions about temptation, providence and prayer; all short |
| 15 | Chesterton, *Orthodoxy* (1908) and *The Everlasting Man* (1925) | Apologetics, which the corpus lacks; CCEL ThML ready. Not a saint, so label as lay apologetics |

The next tier is the English mystics on CCEL (*Cloud of Unknowing*, Hilton's *Scale of Perfection*, Rolle, Ruusbroec, Tauler, Suso), Francis of Assisi's writings with Bonaventure's *Life of St Francis*, Teresa's *Foundations* and *Letters*, and Marmion's *Christ the Life of the Soul*. Aquinas's *Summa contra Gentiles* and *Catena Aurea* are high value but belong to a boundary decision (section 5).

---

## 2. List A: available now, free and legal

This section opens with the priority signals per author, because they are shared by every work below, then lists the works in two tiers (A1 and A2).

### 2.1 Priority signals by author

#### The Doctors of the Church (38)

The request said 37. Pope Leo XIV proclaimed John Henry Newman the 38th Doctor on 1 November 2025 and named him co-patron of Catholic education. [Vatican News, 1 November 2025](https://www.vaticannews.va/en/pope/news/2025-11/pope-leo-newman-doctor-church-light-new-generations.html). Irenaeus was the 37th, by decree of 21 January 2022. [Holy See Press Office](https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2022/01/21/220121b.html)

Fathers era (to about 750), 18, belonging to the Church Fathers collection: Ambrose, Jerome, Augustine, Gregory the Great, Athanasius, Basil, Gregory Nazianzen, John Chrysostom, Cyril of Alexandria, Cyril of Jerusalem, Hilary of Poitiers, Leo the Great, Peter Chrysologus, Isidore of Seville, Ephrem, Bede (d. 735), John Damascene (d. about 749), Irenaeus. [Catholic Encyclopedia, "Doctors of the Church"](https://www.newadvent.org/cathen/05075a.htm) lists all but Ephrem (1920) and Irenaeus.

After the Fathers, 20, all in scope for this collection:

| Doctor | Died | Declared | Source |
|---|---|---|---|
| Peter Damian | 1072 | 1828 | [CE, Doctors](https://www.newadvent.org/cathen/05075a.htm) |
| Anselm | 1109 | 1720 | same |
| Bernard of Clairvaux | 1153 | 1830 | same; [*Doctor Mellifluus* (1953)](https://www.vatican.va/content/pius-xii/en/encyclicals/documents/hf_p-xii_enc_24051953_doctor-mellifluus.html) |
| Anthony of Padua | 1231 | 1946 | [CE, Anthony](https://www.newadvent.org/cathen/01556a.htm) predates it; year from the 1946 proclamation |
| Albert the Great | 1280 | 1931 | [CE, Albertus Magnus](https://www.newadvent.org/cathen/01264a.htm) predates it |
| Bonaventure | 1274 | 1588 | [CE, Doctors](https://www.newadvent.org/cathen/05075a.htm) |
| Thomas Aquinas | 1274 | 1567 | same |
| Catherine of Siena | 1380 | 1970 | [*Spes aedificandi* (1999)](https://www.vatican.va/content/john-paul-ii/en/motu_proprio/documents/hf_jp-ii_motu-proprio_01101999_co-patronesses-europe.html) |
| Teresa of Avila | 1582 | 1970 | [Benedict XVI, audience of 2 February 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110202.html) |
| John of Avila | 1569 | 2012 | [Apostolic letter, 7 October 2012](https://www.vatican.va/content/benedict-xvi/en/apost_letters/documents/hf_ben-xvi_apl_20121007_giovanni-avila.html) |
| John of the Cross | 1591 | 1926 | [Benedict XVI, audience of 16 February 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110216.html) |
| Peter Canisius | 1597 | 1925 | [audience of 9 February 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110209.html) |
| Robert Bellarmine | 1621 | 1931 | [audience of 23 February 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110223.html) |
| Lawrence of Brindisi | 1619 | 1959 | [audience of 23 March 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110323.html) |
| Francis de Sales | 1622 | 1877 | [CE, Doctors](https://www.newadvent.org/cathen/05075a.htm) |
| Alphonsus Liguori | 1787 | 1871 | same |
| Thérèse of Lisieux | 1897 | 1997 | [*Divini amoris scientia*](https://www.vatican.va/content/john-paul-ii/en/apost_letters/1997/documents/hf_jp-ii_apl_19101997_divini-amoris.html) |
| Hildegard of Bingen | 1179 | 2012 | [Apostolic letter, 7 October 2012](https://www.vatican.va/content/benedict-xvi/en/apost_letters/documents/hf_ben-xvi_apl_20121007_ildegarda-bingen.html) |
| Gregory of Narek | about 1003 | 2015 | [Apostolic letter, 12 April 2015](https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco_lettera-ap_2015412_gregorius-narecensis-doctor-ecclesiae.html) |
| John Henry Newman | 1890 | 2025 | [Vatican News](https://www.vaticannews.va/en/pope/news/2025-11/pope-leo-newman-doctor-church-light-new-generations.html) |

Gregory of Narek is an Armenian monk of the tenth and eleventh centuries. He is after 750, so he belongs here, not with the Fathers.

#### Signals per author

"CCC" is the footnote count from our vendored Catechism (method above). "BXVI" means Benedict XVI gave a general audience catechesis on the author in his 2009-2011 series on medieval and early modern teachers. That is not a doctrinal act, but it is a strong papal commendation of the author as a model, and a useful tiebreaker. Audience dates link to vatican.va.

| Author | Status | Doctor | CCC | Commendation | Search usefulness |
|---|---|---|---|---|---|
| Thomas Aquinas | Saint | 1567 | 56 (45 Summa, 11 other works) | [*Aeterni Patris*](https://www.vatican.va/content/leo-xiii/en/encyclicals/documents/hf_l-xiii_enc_04081879_aeterni-patris.html); [*Studiorum Ducem*](https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_19230629_studiorum-ducem.html); BXVI [2](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100602.html), [16](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100616.html), [23 June 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100623.html) | Very high (apologetics, the Creed, the Our Father, the Commandments) |
| Thérèse of Lisieux | Saint | 1997 | 6 | *Divini amoris scientia*; BXVI [6 Apr 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110406.html) | Very high (prayer, suffering, the little way) |
| Teresa of Avila | Saint | 1970 | 5 | BXVI 2 Feb 2011 | Very high (prayer) |
| John of the Cross | Saint | 1926 | 5 | BXVI 16 Feb 2011 | High (dryness, darkness, detachment) |
| Newman | Saint | 2025 | 4 | Doctor and co-patron of Catholic education (2025) | High (conscience, faith and reason, development of doctrine, conversion) |
| Catherine of Siena | Saint | 1970 | 3 | Co-patroness of Europe, *Spes aedificandi*; BXVI [24 Nov 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20101124.html) | High (providence, the Church, prayer) |
| Francis of Assisi | Saint | no | 3 | BXVI [27 Jan 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100127.html) | Medium (creation, poverty, peace) |
| Bonaventure | Saint | 1588 | 2 | Named beside Aquinas in *Aeterni Patris*; BXVI 3, 10, 17 Mar 2010 | Medium to high |
| Bernard of Clairvaux | Saint | 1830 | 2 | *Doctor Mellifluus*; BXVI [21 Oct 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20091021.html) | High (love of God, Mary, humility) |
| Ignatius of Loyola | Saint | no | 2 | [CE](https://www.newadvent.org/cathen/07639c.htm) | Very high (discernment, examen, retreat) |
| John Vianney | Saint | no | 2 | Benedict XVI's [letter opening the Year for Priests](https://www.vatican.va/content/benedict-xvi/en/letters/2009/documents/hf_ben-xvi_let_20090616_anno-sacerdotale.html) | High (confession, the priesthood, the Eucharist) |
| Anselm | Saint | 1720 | 1 | BXVI [23 Sep 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20090923.html) | Already held |
| Francis de Sales | Saint | 1877 | 1 | [*Rerum omnium perturbationem*](https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_26011923_rerum-omnium-perturbationem.html) (patron of writers, holds up the *Devout Life*); BXVI [2 Mar 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110302.html) | Very high (holiness in ordinary life) |
| Alphonsus Liguori | Saint | 1871 | 1 | BXVI [30 Mar 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110330.html) | Very high (Mary, the Eucharist, death, prayer, confession) |
| Julian of Norwich | Not canonized | no | 1 | BXVI [1 Dec 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20101201.html) | High (suffering, sin, providence) |
| Thomas More | Saint | no | 1 | [Patron of statesmen and politicians](https://www.vatican.va/content/john-paul-ii/en/motu_proprio/documents/hf_jp-ii_motu-proprio_20001031_thomas-more.html) (2000) | Medium (tribulation, conscience) |
| Elizabeth of the Trinity | Saint (2016) | no | 1 | | Medium (the indwelling Trinity) |
| Thomas à Kempis (*Imitation*) | Not canonized | no | 1 | [CE](https://www.newadvent.org/cathen/14661a.htm) | Already held |
| Guigo the Carthusian | | no | 1 | | Low (short *Ladder of Monks*) |
| Louis de Montfort | Saint | no | 0 | Cited in [*Redemptoris Mater* 48](https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031987_redemptoris-mater.html) and [*Rosarium Virginis Mariae* 15](https://www.vatican.va/content/john-paul-ii/en/apost_letters/2002/documents/hf_jp-ii_apl_20021016_rosarium-virginis-mariae.html) | High (Mary, consecration, rosary) |
| Hildegard of Bingen | Saint | 2012 | 0 | BXVI 1 and 8 Sep 2010 | Low for our purposes (no public domain English) |
| Albert the Great | Saint | 1931 | 0 | BXVI [24 Mar 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100324.html) | Low (no suitable English) |
| Anthony of Padua | Saint | 1946 | 0 | BXVI [10 Feb 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100210.html) | Low to medium |
| Peter Canisius, Robert Bellarmine, Lawrence of Brindisi | Saints | yes | 0 each | BXVI 2011 audiences above | Bellarmine medium, others low (little English) |
| John of Avila | Saint | 2012 | 0 | Apostolic letter 2012 | Medium (letters of direction) |
| Hugh and Richard of St Victor | Not canonized | no | 0 | BXVI [25 Nov 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20091125.html) | Medium |
| William of St Thierry | Not canonized | no | 0 | BXVI [2 Dec 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20091202.html) | Medium |
| Peter Lombard | Not canonized | no | 0 | BXVI [30 Dec 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20091230.html) | Low (reference text) |
| Duns Scotus | Blessed | no | 0 | BXVI [7 Jul 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100707.html) | Low |
| Gertrude the Great | Saint | no | 0 | BXVI [6 Oct 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20101006.html) | Medium (Sacred Heart) |
| Mechthild of Magdeburg | Not canonized | no | 0 | [CE](https://www.newadvent.org/cathen/10106a.htm) | Low |
| Bridget of Sweden | Saint | no | 0 | Co-patroness of Europe; BXVI [27 Oct 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20101027.html) | Medium (the Passion) |
| Clare of Assisi | Saint | no | 0 | BXVI [15 Sep 2010](https://www.vatican.va/content/benedict-xvi/en/audiences/2010/documents/hf_ben-xvi_aud_20100915.html) | Low (few writings) |
| Catherine of Genoa | Saint | no | 0 | BXVI [12 Jan 2011](https://www.vatican.va/content/benedict-xvi/en/audiences/2011/documents/hf_ben-xvi_aud_20110112.html) | High for one question (purgatory) |
| Ruusbroec, Suso | Blessed | no | 0 | [CE Ruysbroeck](https://www.newadvent.org/cathen/13280c.htm), [CE Suso](https://www.newadvent.org/cathen/07238c.htm) | Medium |
| Tauler, Hilton, Rolle, *Cloud* author | Not canonized | no | 0 | [CE Tauler](https://www.newadvent.org/cathen/14465c.htm), [Hilton](https://www.newadvent.org/cathen/07355a.htm), [Rolle](https://www.newadvent.org/cathen/13119a.htm) | Medium (contemplative prayer) |
| Columba Marmion | Blessed (2000) | no | 0 | | High (grace, baptism, the Mass) |
| Chesterton | Not beatified | no | 0 | | High (apologetics) |

The CCC also cites Joan of Arc (3), Rose of Lima, Nicholas of Flüe and Dominic. None left writings that fit this collection.

---

### 2.2 Why these are public domain

Unless a note says otherwise, every row is public domain in the US because the English translation was first published in 1930 or earlier (Cornell chart above). For the author's own English (More, Fisher, Newman, Chesterton) the publication year of the work decides.

"Strip" names editorial matter to remove at ingest. Sizes are body words for CCEL and Gutenberg, printed pages for scans.

### 2.3 A1. CCEL ThML (drop-in for `datapipeline/ingest/thml_doc.py`)

| # | Work | Author | English edition | Source (ThML) | Size | Notes |
|---|---|---|---|---|---|---|
| 1 | *The Interior Castle* | Teresa of Avila (1515-1582) | Stanbrook Benedictines, revised by B. Zimmerman, 3rd ed., Thomas Baker, London 1921 | [ccel.org/ccel/teresa/castle2](https://ccel.org/ccel/teresa/castle2) | 89k words | Strip Zimmerman's introduction and notes |
| 2 | *The Life of St. Teresa of Jesus* | Teresa of Avila | David Lewis, 3rd ed., Baker / Benziger 1904; also [Gutenberg 8120](https://www.gutenberg.org/ebooks/8120) | [ccel.org/ccel/teresa/life](https://ccel.org/ccel/teresa/life) | 209k | Strip Zimmerman introduction, Lewis preface, "Annals" |
| 3 | *A Spiritual Canticle of the Soul* | John of the Cross (1542-1591) | David Lewis, corrected with introduction by Zimmerman, 1909 | [ccel.org/ccel/john_cross/canticle](https://ccel.org/ccel/john_cross/canticle) | 75k | Plantinga's 1995 edition modernized some English; strip introduction |
| 4 | *Introduction to the Devout Life* | Francis de Sales (1567-1622) | "Library of Spiritual Works for English Catholics" edition (Rivingtons series). CCEL gives no date | [ccel.org/ccel/desales/devout_life](https://ccel.org/ccel/desales/devout_life) | 86k | Check the title page year; the series is 19th century. Editor footnotes inline |
| 5 | *Treatise on the Love of God* | Francis de Sales | H. B. Mackey, originally Burns & Oates about 1884 (TAN reprint) | [ccel.org/ccel/desales/love](https://ccel.org/ccel/desales/love) | 250k | TAN front matter to strip |
| 6 | *The Dialogue* | Catherine of Siena (1347-1380) | Algar Thorold (Kegan Paul, 1896; abridged edition 1907) | [ccel.org/ccel/catherine/dialog](https://ccel.org/ccel/catherine/dialog) | 91k | CCEL does not say which Thorold edition; the full 1896 edition is on [IA](https://archive.org/details/seraphicvirginca00cathuoft) (380 pp.) if this one is the abridgement |
| 7 | *Revelations of Divine Love* | Julian of Norwich (b. 1343) | Grace Warrack, Methuen 1901; also [Gutenberg 52958](https://www.gutenberg.org/ebooks/52958) | [ccel.org/ccel/julian/revelations](https://ccel.org/ccel/julian/revelations) | 61k | Warrack's glosses are inline, as in the source |
| 8 | *The Story of a Soul* | Thérèse of Lisieux (1873-1897) | T. N. Taylor, *Soeur Thérèse of Lisieux*, Burns Oates & Washbourne 1912 (8th ed. 1922) | [ccel.org/ccel/therese/autobio](https://ccel.org/ccel/therese/autobio) | 107k | Includes letters, counsels and poems. Strip Cardinal Bourne's preface, prologue, epilogue. Taylor translates the edited *Histoire d'une âme*, not the critical manuscripts |
| 9 | *Spiritual Exercises* | Ignatius of Loyola (1491-1556) | Elder Mullan, P. J. Kenedy 1914 | [ccel.org/ccel/ignatius/exercises](https://ccel.org/ccel/ignatius/exercises) | 33k | Numbered paragraphs, good for anchors |
| 10 | *Autobiography of St. Ignatius* | Ignatius of Loyola | J. F. X. O'Conor, Benziger 1900; also [Gutenberg 24534](https://www.gutenberg.org/ebooks/24534) | [ccel.org/ccel/ignatius/autobiography](https://ccel.org/ccel/ignatius/autobiography) | 23k | Strip editor's preface |
| 11 | *The Cloud of Unknowing* | Anonymous English, 14th century | Evelyn Underhill, John M. Watkins 1912 (2nd ed. 1922) | [ccel.org/ccel/anonymous2/cloud](https://ccel.org/ccel/anonymous2/cloud) | 44k | Long Underhill introduction to strip |
| 12 | *The Scale (or Ladder) of Perfection* | Walter Hilton (d. 1396) | Dalgairns edition; CCEL's companion file names Art and Book Co. / Benziger 1901 as the print source | [ccel.org/ccel/hilton/ladder](https://ccel.org/ccel/hilton/ladder) | 113k | Strip Dalgairns's essay |
| 13 | *Treatise Written to a Devout Man* (on the mixed life) | Walter Hilton | same 1901 edition | [ccel.org/ccel/hilton/treatise](https://ccel.org/ccel/hilton/treatise) | 13k | |
| 14 | *The Cell of Self-Knowledge* (seven treatises, including Richard of St Victor's *Benjamin Minor* in English, Hilton's *Song of Angels*, extracts from Catherine of Siena) | ed. Edmund Gardner, 1910 | Gardner 1910 (Pepwell's 1521 texts); also [Gutenberg 4544](https://www.gutenberg.org/ebooks/4544) | [ccel.org/ccel/gardner/cell](https://ccel.org/ccel/gardner/cell) | about 30k | The only public domain Richard of St Victor found. Also contains Margery Kempe extracts, who is not in scope; drop them or label |
| 15 | *The Fire of Love* and *The Mending of Life* | Richard Rolle (d. 1349) | Richard Misyn's 1435 Middle English, modernized by Frances Comper, Methuen 1914 (2nd ed. 1920) | [ccel.org/ccel/rolle/fire](https://ccel.org/ccel/rolle/fire) | 84k | Strip Underhill introduction |
| 16 | *The Adornment of the Spiritual Marriage*, *The Sparkling Stone*, *The Book of Supreme Truth* | John Ruusbroec (1293-1381) | C. A. Wynschenk Dom, ed. Underhill, 1916 | [ccel.org/ccel/ruysbroeck/adornment](https://ccel.org/ccel/ruysbroeck/adornment) | 79k | Strip introduction |
| 17 | *The Inner Way* (36 festal sermons) | John Tauler (d. 1361) | A. W. Hutton, Methuen 1901 (2nd ed. 1909) | [ccel.org/ccel/tauler/inner_way](https://ccel.org/ccel/tauler/inner_way) | 97k | Sermons are authentic Tauler; see List C for the spurious Tauler items |
| 18 | *A Little Book of Eternal Wisdom* | Henry Suso (d. 1366) | Burns Oates & Washbourne, imprimatur 1910 | [ccel.org/ccel/suso/wisdom](https://ccel.org/ccel/suso/wisdom) | 45k | Also contains Hilton's *Parable of the Pilgrim* |
| 19 | *The Life of Blessed Henry Suso by Himself* | Henry Suso | T. F. Knox, Burns, Lambert & Oates 1865 | [ccel.org/ccel/suso/susolife](https://ccel.org/ccel/suso/susolife) | 71k | Hagiographic; medium priority |
| 20 | *Letters of St. Bernard* | Bernard of Clairvaux (1090-1153) | S. J. Eales, John Hodges 1904 | [ccel.org/ccel/bernard/letters](https://ccel.org/ccel/bernard/letters) | 97k | Mabillon notes inline |
| 21 | *Catena Aurea*, Matthew and Mark | Thomas Aquinas (1225-1274) | Oxford translation ed. J. H. Newman, Parker / Rivington 1841-42 | [catena1](https://ccel.org/ccel/aquinas/catena1), [catena2](https://ccel.org/ccel/aquinas/catena2) | 405k + 139k | CCEL's "tr. William Whiston" is a metadata error. Luke and John are only on IA (A2). Boundary item |
| 22 | *Of God and His Creatures* (abridged *Summa contra Gentiles*) | Thomas Aquinas | Joseph Rickaby, Burns & Oates 1905 | [ccel.org/ccel/aquinas/gentiles](https://ccel.org/ccel/aquinas/gentiles) | 299k | Abridged and annotated. Prefer the complete 1923-29 Dominican translation (A2) if we take SCG at all |
| 23 | *Works of Dionysius the Areopagite* (Divine Names, Mystical Theology, Letters) | Pseudo-Dionysius (about 500) | John Parker, James Parker & Co. 1897 | [ccel.org/ccel/dionysius/works](https://ccel.org/ccel/dionysius/works) | 95k | Keep with a pseudonymity label (section 4). Parker believed the works apostolic; strip his prefaces |
| 24 | *Orthodoxy* | G. K. Chesterton (1874-1936) | Dodd, Mead 1908 | [ccel.org/ccel/chesterton/orthodoxy](https://ccel.org/ccel/chesterton/orthodoxy) | 64k | Written as an Anglican (he converted in 1922) |
| 25 | *The Everlasting Man* | G. K. Chesterton | 1925; also [Gutenberg 65688](https://www.gutenberg.org/ebooks/65688) | [ccel.org/ccel/chesterton/everlasting](https://ccel.org/ccel/chesterton/everlasting) | 106k | |
| 26 | *Devotions of Saint Anselm* (Proslogion, Meditations, Prayers) and *Book of Meditations and Prayers* | Anselm (1033-1109) | C. C. J. Webb, Methuen 1903; "M. R.", Burns & Oates 1872 | [anselm/devotions](https://ccel.org/ccel/anselm/devotions), [anselm/meditations](https://ccel.org/ccel/anselm/meditations) | 44k + 69k | The 1872 volume includes pieces now judged not Anselm's (see C) |
| 27 | *The Dream of Gerontius* | John Henry Newman (1801-1890) | 1865 poem | [ccel.org/ccel/newman/gerontius](https://ccel.org/ccel/newman/gerontius) | 6k | Poetry; low priority but short and about death and purgatory |

Also on CCEL as ThML but lower value: Thomas à Kempis, *Founders of the New Devotion* (J. P. Arthur, 1905, 83k), Bernard, *Life of St Malachy* (Lawlor, 1920, 88k), Thérèse's *Poems* (S. L. Emery, 1907, 31k), Augustine Baker, *Holy Wisdom* (Sweeney edition, Burns & Oates, undated in the header, 251k; check the title page date), and Gerson, *Snares of the Devil* (1883, 11k).

### 2.4 A2. Gutenberg text or Internet Archive scan

| # | Work | Author | English edition | Source, format | Size | Notes |
|---|---|---|---|---|---|---|
| 1 | *Ascent of Mount Carmel*, *Dark Night*, *Living Flame*, *Spiritual Canticle*, poems | John of the Cross | *Complete Works*, tr. David Lewis, Longman 1864, 2 vols | [IA vol 1](https://archive.org/details/completeworksofs01johnuoft), [vol 2](https://archive.org/details/completeworksofs02johnuoft), scan | 524 + 514 pp. | Use this instead of CCEL's Peers files. Cardinal Wiseman's introduction to strip |
| 2 | *The Book of the Foundations* | Teresa of Avila | David Lewis, 1871 | [IA](https://archive.org/details/bookfoundations00teregoog), scan (Google, Oxford copy) | 425 pp. | |
| 3 | *Letters of St Teresa* | Teresa of Avila | Stanbrook Benedictines, Thomas Baker, from 1919, several vols | [IA vol 1](https://archive.org/details/letterst01tere), [vol 2](https://archive.org/details/letterst02tere), scan | about 340 pp. per vol | Only vols 1-2 found; find the rest and confirm every volume is dated 1930 or earlier |
| 4 | *The Way of Perfection* | Teresa of Avila | John Dalton, 1852 | [IA](https://archive.org/details/wayperfectionan00teregoog), scan | 305 pp. | Use instead of CCEL's Peers. Dalton is dated but public domain |
| 5 | *The Glories of Mary* | Alphonsus Liguori (1696-1787) | Dunigan, New York 1852 ("second American edition") | [Gutenberg 72411](https://www.gutenberg.org/ebooks/72411), text | 213k words | Highest Marian value in the list |
| 6 | *Complete Ascetical Works* (Centenary Edition) | Alphonsus Liguori | ed. Eugene Grimm, Benziger 1886-1897, 22 vols | IA, e.g. [vol 2](https://archive.org/details/thecompleteascet02liguuoft), [vol 4](https://archive.org/details/thecompleteascet04liguuoft), [vol 5](https://archive.org/details/PassionDeathOfJesusChristV5), scan | about 500 pp. per vol | Contains *Preparation for Death*, *Uniformity with God's Will*, *The Great Means of Prayer* (CCC-cited), *The Holy Eucharist* with the *Visits*. Map volumes to titles before ingesting |
| 7 | *Visits to the Most Holy Sacrament and the Blessed Virgin* | Alphonsus Liguori | Kenedy, New York 1855 | [IA](https://archive.org/details/visitstomostholy0000ligu), scan | 260 pp. | Stand-alone alternative to the Centenary volume |
| 8 | *Preparation for Death* | Alphonsus Liguori | Boston 1854 | [IA](https://archive.org/details/preparationforde00ligu), scan | 410 pp. | |
| 9 | *A Treatise on the True Devotion to the Blessed Virgin* | Louis de Montfort (1673-1716) | F. W. Faber, Burns & Lambert 1863 | [IA](https://archive.org/details/TreatiseTrueDevotionBlessedVirgin), scan | 238 pp. | Strip Faber's preface |
| 10 | *Abandonment, or Absolute Surrender to Divine Providence* | Jean-Pierre de Caussade (d. 1751) | Ella McMahon from the 8th French ed. (ed. H. Ramière), Benziger 1887 | [Gutenberg 52057](https://www.gutenberg.org/ebooks/52057), text | 38k words | Ramière edited the text heavily; label as his edition |
| 11 | *The Practice of the Presence of God* | Brother Lawrence (1611-1691) | Fleming H. Revell, undated | [Gutenberg 13871](https://www.gutenberg.org/ebooks/13871), text | 14k | Do not use Gutenberg 5657: its text is a "2002 edition, Copyright (C) 2002 by Lightheart" |
| 12 | *The Spiritual Combat* with *Peace of the Soul* | Lorenzo Scupoli (d. 1610) | J. Burns, London 1846 | [IA](https://archive.org/details/TheSpiritualCombat1846), scan | 284 pp. | |
| 13 | *Apologia pro Vita Sua* | Newman | 1864 text | [Gutenberg 19690](https://www.gutenberg.org/ebooks/19690) or [22088](https://www.gutenberg.org/ebooks/22088), text | 141k | CCEL's copy is page images only |
| 14 | *An Essay on the Development of Christian Doctrine* | Newman | 6th ed. | [Gutenberg 35110](https://www.gutenberg.org/ebooks/35110), text | 140k | |
| 15 | *The Idea of a University* | Newman | | [Gutenberg 24526](https://www.gutenberg.org/ebooks/24526), text | 162k | Medium priority (education, faith and reason) |
| 16 | *An Essay in Aid of a Grammar of Assent* | Newman | Burns, Oates 1870 | [IA](https://archive.org/details/anessayinaidofag00newmuoft), scan | 508 pp. | |
| 17 | *Parochial and Plain Sermons*, 8 vols | Newman | Rivingtons 1868 | IA, e.g. [vol 4](https://archive.org/details/parochialplainse04newmuoft), [vol 7](https://archive.org/details/parochialandp07newmuoft), scan | about 400 pp. per vol | Anglican-period sermons (1834-43), republished by Newman as a Catholic. [Newman Reader](https://www.newmanreader.org/) has clean HTML of all Newman, but the site says "Copyright 2007 by The National Institute for Newman Studies. All rights reserved"; ask before scraping it |
| 18 | *Cantica Canticorum: Eighty-Six Sermons on the Song of Solomon* | Bernard | S. J. Eales, Hodges 1895 (vol 4 of *Life and Works*) | [IA](https://archive.org/details/LifeAndWorksOfSaintBernardV4), scan | 577 pp. | Also a Mount Melleray translation, Browne & Nolan 1920, [IA vol 1](https://archive.org/details/stbernardssermon01bern), [vol 2](https://archive.org/details/stbernardssermon02bern) |
| 19 | *On Consideration* | Bernard | George Lewis, Clarendon Press 1908 | [IA](https://archive.org/details/bernarddeclirvau00bernuoft), scan | 184 pp. | |
| 20 | *Concerning Grace and Free Will* | Bernard | W. Watkin Williams, SPCK 1920 | [IA](https://archive.org/details/treatiseofstber00bern), scan | 150 pp. | |
| 21 | *The Golden Epistle* | William of St Thierry (d. 1148) | Sheed & Ward 1930, ed. Justin McCann | [IA](https://archive.org/details/goldenepistleofa0000domj), scan | 186 pp. | Public domain in the US since 1 January 2026 (1930 publication). Confirm year on the title page |
| 22 | *The Writings of Saint Francis of Assisi* | Francis of Assisi (1182-1226) | Paschal Robinson, Dolphin Press 1906 | [IA](https://archive.org/details/writingsofsaintf00fran_0), scan | 260 pp. | Includes the Rules, Admonitions, Canticle, letters |
| 23 | *The Little Flowers of Saint Francis* | Anonymous Franciscan, 14th century | Upton translation revised by Thomas Okey, Kegan Paul 1899 | [IA](https://archive.org/details/littleflowersofs00unse), scan | 277 pp. | Not by Francis; label as legend. Includes *Life of Brother Juniper* and *Brother Giles* |
| 24 | *The Life of Saint Francis* (*Legenda maior*) | Bonaventure (1221-1274) | E. Gurney Salter, Dent 1904 | [IA](https://archive.org/details/TheLifeOfSaintFrancis), scan | 239 pp. | The one public domain Bonaventure found |
| 25 | *Letters of Catherine Benincasa* (selected) | Catherine of Siena | Vida Scudder, 1905 | [Gutenberg 7403](https://www.gutenberg.org/ebooks/7403), text | 115k | Scudder's linking commentary to strip |
| 26 | *The Life and Revelations of Saint Gertrude* | Gertrude the Great (1256-1302) | Burns & Oates / Benziger, about 1870 | [IA](https://archive.org/details/thelifeandrevela00gertuoft), scan | 638 pp. | The *Herald* "comprises five books containing the life" of Gertrude as well as her revelations ([CE](https://www.newadvent.org/cathen/06534a.htm)), so not all of it is in her voice. Label accordingly |
| 27 | *The Exercises of Saint Gertrude* | Gertrude | from Guéranger's French, 1863 | [IA](https://archive.org/details/exercisessaintg00gertgoog), scan | 261 pp. | |
| 28 | *Revelations of St. Bridget on the Life and Passion of Our Lord* | Bridget of Sweden (1303-1373) | Sadlier, New York 1862 | [IA](https://archive.org/details/RevelationsOfStBridget), scan | 166 pp. | A small selection |
| 29 | *The Revelations of Saint Birgitta* (Middle English version) | Bridget of Sweden | ed. W. P. Cumming, EETS 1929 | [IA](https://archive.org/details/30081000926059), scan | 196 pp. | Middle English; hard for users. Low priority |
| 30 | *Matelda and the Cloister of Hellfde* (extracts) | Mechthild of Magdeburg (about 1207-1282) | Frances Bevan, 1896 | [Gutenberg 35811](https://www.gutenberg.org/ebooks/35811), text | 37k | Selective; see C |
| 31 | *Utopia* with *A Dialogue of Comfort* | Thomas More (1478-1535) | Everyman, Dent 1910 / 1913 | [IA](https://archive.org/details/utopiawiththedia00moreuoft), scan | 418 pp. | Take the *Dialogue of Comfort* only. Use this, not the 1951 Stevens modernization on CCEL (see C) |
| 32 | *English Works of John Fisher* | John Fisher (1469-1535) | ed. J. E. B. Mayor, EETS 1876 | [IA](https://archive.org/details/englishworksjoh00mayogoog), scan | 485 pp. | Includes the sermons on the seven penitential psalms. Early Tudor spelling |
| 33 | *The Art of Dying Well* | Robert Bellarmine (1542-1621) | Richardson, London 1847 | [IA](https://archive.org/details/theartofdyingwel00belluoft), scan | | |
| 34 | *The Eternal Happiness of the Saints* | Robert Bellarmine | Richardson, London, 19th century | [IA](https://archive.org/details/theeternalhappin00belluoft), scan | 284 pp. | |
| 35 | *The Ascent of the Mind to God* | Robert Bellarmine | 1928 | [IA](https://archive.org/details/ascentofmindtogo0000unse), scan | 354 pp. | Publisher not in IA metadata; confirm title page |
| 36 | *Letters of Blessed John of Avila* | John of Avila (1499-1569) | Stanbrook Benedictines, Burns & Oates 1904 | [IA](https://archive.org/details/lettersofblessed00johnuoft), scan | 190 pp. | Only public domain English of a 2012 Doctor |
| 37 | *The Moral Concordances of Saint Anthony of Padua* | Anthony of Padua (1195-1231) | J. M. Neale, Hayes 1856 / 1867 | [IA](https://archive.org/details/moralconcordance00neal), scan | | A preacher's aid, not the sermons. Low priority |
| 38 | *The Spirit of the Curé of Ars* | John Vianney (1786-1859), as recorded by Alfred Monnin | ed. J. E. Bowden, Burns, Lambert & Oates 1865 | [IA](https://archive.org/details/TheSpiritOfTheCureOfArs), scan | 298 pp. | Reported sayings and catechisms, not Vianney's own manuscripts. Label as such |
| 39 | *Thoughts of the Curé of Ars* | Vianney | Flynn & Mahony, Boston 1896 | [IA](https://archive.org/details/thoughtsofcurofa00vian), scan | 46 pp. | |
| 40 | *The Praise of Glory* | Elizabeth of the Trinity (1880-1906) | Washbourne 1913 / 1914 | [IA](https://archive.org/details/thepraiseofglory00elizuoft), scan | 372 pp. | Mostly her prioress's memoir with her letters and retreats. Take her own writings |
| 41 | *Summa contra Gentiles*, complete | Thomas Aquinas | English Dominican Fathers, Burns Oates & Washbourne 1923-1929 | IA, e.g. [book 1](https://archive.org/details/summacontragenti01thomuoft), scan | 4 books in 5 vols | Boundary item |
| 42 | *Catena Aurea*, Luke and John | Thomas Aquinas | Oxford 1841-45 | IA, e.g. [this volume](https://archive.org/details/catenaaureacomme04thom), scan | | Completes the CCEL Matthew and Mark |
| 43 | *The Lord's Prayer* | Thomas Aquinas | H. A. Rawes, Burns & Oates 1879 | [IA](https://archive.org/details/LordsPrayerTrByFatherRawes), scan | 183 pp. | CCC cites Aquinas's catechetical sermons |
| 44 | *On the Two Commandments of Charity and the Ten Commandments* | Thomas Aquinas | H. A. Rawes, 1880 | [IA](https://archive.org/details/AquinasOnTheCommandments), scan | 275 pp. | CCC cites *De decem praeceptis* |
| 45 | *The Celestial and Ecclesiastical Hierarchy* | Pseudo-Dionysius | John Parker, Skeffington 1894 | [IA](https://archive.org/details/celestialandecc00parkgoog), scan | | Pair with A1 #23 |
| 46 | *The Treatise on Purgatory* | Catherine of Genoa (1447-1510) | Burns & Lambert 1858, preface by H. E. Manning | [IA](https://archive.org/details/TreatiseOnPurgatory), scan | | Short; answers a common question well |
| 47 | *Christ the Life of the Soul* | Columba Marmion (1858-1923) | Sands 1922 | [IA](https://archive.org/details/christlifeofsoul0000marm), scan | 456 pp. | Beatified 2000 |
| 48 | *Christ in His Mysteries* | Columba Marmion | 1923 (1924 per some records) | [IA](https://archive.org/details/christinhismyste0000righ), scan | | Confirm year |
| 49 | *The Spiritual Life: A Treatise on Ascetical and Mystical Theology* | Adolphe Tanquerey (1854-1932) | Desclée, Tournai 1930 | [IA](https://archive.org/details/spirituallife0000atan), scan | 830 pp. | Public domain in the US since 1 January 2026. A manual, well indexed by topic |
| 50 | *The Glories of Divine Grace* | M. J. Scheeben (1835-1888), after J. E. Nieremberg (1595-1658) | Benziger 1886 | [IA](https://archive.org/details/gloriesofdivineg00sche_1), scan | 470 pp. | Scheeben calls it "a free rendering" of Nieremberg. Credit both |
| 51 | *Symbolism* | J. A. Möhler (1796-1838) | J. B. Robertson, Dolman 1843, 2 vols | [IA vol 1](https://archive.org/details/a593164201mohluoft), scan | 530 pp. | Catholic and Protestant doctrine compared; apologetics |
| 52 | *The Belief of Catholics* | Ronald Knox (1888-1957) | Benn / Harper 1927 | [IA](https://archive.org/details/beliefofcatholic0000knox_h2r4), scan | 264 pp. | The only Knox book found that is safely public domain and on topic |
| 53 | *The Catholic Church and Conversion* | Chesterton | Macmillan 1926 | [IA](https://archive.org/details/catholicchurchco0000ches), scan | | |
| 54 | *The Thing: Why I Am a Catholic* | Chesterton | Dodd, Mead 1930 (UK 1929) | [IA](https://archive.org/details/thingwhyiamcatho00ches_0), scan | | |
| 55 | *St. Francis of Assisi* | Chesterton | 1923 | [Gutenberg 63084](https://www.gutenberg.org/ebooks/63084), text | 47k | |
| 56 | *The Sinner's Guide* | Luis of Granada (1504-1588) | 1883 / Noonan 1886 | [IA](https://archive.org/details/sinnersguide00luis), scan | | Dominican; a classic of conversion |
| 57 | *The Spiritual Doctrine of Father Louis Lallemant* | Louis Lallemant (1588-1635) | ed. F. W. Faber, Burns 1855 | [IA](https://archive.org/details/SpiritualDoctrineOfFrLouisLallemant), scan | | Docility to the Holy Spirit |
| 58 | *All for Jesus* (1853) and *Growth in Holiness* (1855) | F. W. Faber (1814-1863) | Faber's own English | [IA](https://archive.org/details/allforjesusoreas00fabeuoft), [IA](https://archive.org/details/GrowthInHoliness1855), scan | | Oratorian; no cause. Popular Victorian devotional |

Further public domain items found but lower priority: Alphonsus Rodriguez, *Practice of Christian and Religious Perfection* (1861, [IA](https://archive.org/details/PracticeOfChristianAndReligiousPerfectionV1)), Challoner, *Meditations for Every Day* (1815, [IA](https://archive.org/details/ConsiderationsUponChristianV1)), Francis de Sales, *Spiritual Conferences* (1862, [IA](https://archive.org/details/ConferencesOfStFrancisOfSales)) and *Letters to Persons in the World* (Mackey, [IA](https://archive.org/details/letterstopersons00franuoft)), *Maxims and Counsels of St Francis de Sales* (1884, [Gutenberg 73661](https://www.gutenberg.org/ebooks/73661)), Karl Adam, *The Spirit of Catholicism* (tr. McCann, Sheed & Ward 1929, [IA](https://archive.org/details/spiritofcatholic0000adam)), Gilson, *The Philosophy of St Thomas Aquinas* (Heffer 1924, [IA](https://archive.org/details/philosophyofstth00gils_0); secondary scholarship), Sheen, *God and Intelligence* (1925) and *Religion Without God* (1928, [IA](https://archive.org/details/religionwithoutg00shee_0); academic, low search value), *The Life and Legend of the Lady Saint Clare* (Balfour, 1910, [IA](https://archive.org/details/lifelegendoflady0000char); a life, not Clare's writings).

---

## 3. List B: needs payment, permission, or a renewal search

These have no acceptable public domain English, or the only one is abridged, a paraphrase, or in Middle English. Rights holders are the current publishers as far as I know from the editions; I did not contact any, and none of these rights claims was checked against a copyright record. Treat each as "confirm before asking."

| Author | Work | Best modern translation (publisher) | Why no PD alternative | Route |
|---|---|---|---|---|
| Bonaventure | *Breviloquium*, *Itinerarium* (*Soul's Journey into God*), *Tree of Life* | Monti, Franciscan Institute Publications (Works of St Bonaventure); Cousins, Paulist (Classics of Western Spirituality) | No pre-1931 English of these found. CCEL's *Mind's Road to God* is George Boas's 1953 translation (the preface cites the 1938 Quaracchi text); CCEL says public domain, which holds only if not renewed | Renewal search on Boas (Liberal Arts Press, 1953) first. Otherwise Franciscan Institute, St Bonaventure University |
| Hugh of St Victor | *On the Sacraments*; *Didascalicon* | Deferrari, Medieval Academy of America 1951; Taylor, Columbia UP 1961 | Nothing pre-1931 found | Renewal search on Deferrari (1951) could make it free |
| Richard of St Victor | *Twelve Patriarchs*, *Mystical Ark*, *Book Three of the Trinity* | Zinn, Paulist 1979 | Only the Middle English *Benjamin Minor* in A1 #14 | Paulist Press |
| Peter Lombard | *Sentences* | Silano, Pontifical Institute of Mediaeval Studies 2007-2010, 4 vols | No other English | PIMS, Toronto. Low priority (reference work) |
| Albert the Great | Any authentic work | e.g. Tugwell, *Albert and Thomas: Selected Writings*, Paulist 1988 | The only free "Albert" (CCEL *On Cleaving to God*) is not his (C) | Paulist Press |
| Thomas Aquinas | Scripture commentaries, *Compendium theologiae*, catechetical sermons complete | Aquinas Institute (Emmaus Academic) Latin-English Opera Omnia; Vollert, *Compendium* (Herder 1947); Collins, *Catechetical Instructions* (Wagner 1939) | Rawes (1879-80) covers the Our Father and Commandments only. Vollert and Collins may be unrenewed | Renewal search on Collins and Vollert; Aquinas Institute for a licence. isidore.co hosts the Hanover House SCG (1955-57), which is not public domain |
| Duns Scotus | Selections | Wolter, CUA Press | No PD English | Low priority |
| Hildegard of Bingen | *Scivias* | Hart and Bishop, Paulist 1990 | No PD English found on Gutenberg or IA | Paulist Press. A Doctor with nothing free |
| Mechthild of Magdeburg | *The Flowing Light of the Godhead*, complete | Tobin, Paulist 1998 | Bevan 1896 is extracts only | Paulist Press |
| Gertrude | *The Herald*, critical | Barratt, Cistercian Publications | The 1870 translation is serviceable; buy only if it proves poor | Cistercian Publications / Liturgical Press |
| Bridget of Sweden | *Revelations*, complete | Searby and Morris, Oxford UP, 4 vols | PD options are a small selection or Middle English | OUP. Medium priority |
| Catherine of Siena | *Dialogue*, *Letters*, complete | Noffke, Paulist 1980; Noffke *Letters* (ACMRS) | Thorold is good; buy only if coverage is short | Only if Thorold fails |
| Aelred of Rievaulx | *Spiritual Friendship*, *Mirror of Charity* | Laker, Cistercian 1974; Braceland, Liturgical Press 2010 | Talbot's *Christian Friendship* (1942) exists; renewal unknown | Renewal search on Talbot first |
| William of St Thierry | *Nature and Dignity of Love*, *Contemplation of God* | Cistercian Fathers series | Only the *Golden Epistle* is free | Cistercian Publications |
| Anthony of Padua | *Sermons* | Spilsbury, Edizioni Messaggero Padova | Only the *Concordances* are free | Messaggero |
| Peter Damian | *Letters* | Blum, CUA Press (Fathers of the Church, Mediaeval Continuation) | No PD English | CUA Press. A Doctor with nothing free |
| Peter Canisius, Lawrence of Brindisi | Catechisms; *Mariale* | none found in English for Lawrence | No PD English found | Low priority |
| John of Avila | *Audi, filia* | Gormley, Paulist 2006 | Only the letters are free | Paulist Press |
| Gregory of Narek | *Book of Lamentations* | Samuelian, Vem Press 2001 | No PD English | Out of the Latin mainstream; low priority |
| Teresa of Avila, John of the Cross | Critical translations | Kavanaugh and Rodriguez, ICS Publications (the CCC cites these); Peers (Burns & Oates / Sheed & Ward) | PD Lewis and Stanbrook texts exist. Buy only for quality | ICS Publications, Washington DC |
| Thérèse of Lisieux | *Story of a Soul*, critical | Clarke, ICS 1975 (CCC cites); Knox 1958 (CCC cites) | Taylor 1912 is free but follows the edited text | ICS Publications |
| Elizabeth of the Trinity | *Complete Works* | ICS Publications | 1913 volume has only part of her writing | ICS Publications |
| Faustina Kowalska | *Diary* (*Divine Mercy in My Soul*) | Marian Press | No other English | Marians of the Immaculate Conception, Stockbridge MA. See C for the 1959-1978 history |
| Louis de Montfort | *Secret of the Rosary*, *Secret of Mary* | Montfort Publications | No pre-1931 English found | Montfort Publications, Bay Shore NY |
| Scheeben | *The Mysteries of Christianity* | Vollert, Herder 1946 | Renewal unknown | Renewal search |
| Garrigou-Lagrange | *Three Ages of the Interior Life*, *Our Saviour*, etc. | Herder 1930s-50s; TAN reprints | French originals are protected; English 1930s-50s need per-title renewal checks | Renewal search, then TAN / Herder |
| Anscar Vonier | *A Key to the Doctrine of the Eucharist* | Burns Oates, commonly dated 1925 | Only a lending-restricted 1931 printing on IA | If the 1925 date is confirmed it is PD; find a scan |
| Chesterton | *St. Thomas Aquinas* (1933) | Sheed & Ward | Published 1933; restored UK work | Wait until it enters the US public domain on 1 January 2029 |
| Ronald Knox | Later works (*Enthusiasm*, retreat books) | Burns & Oates / Sheed & Ward | Post-1930 | Knox estate via publishers |
| Fulton Sheen | Works after 1930 | Various | Post-1930; many possibly unrenewed | Per-title renewal search |
| Edith Stein | *Collected Works* | ICS Publications | Post-1930 | ICS Publications |
| Josemaría Escrivá | *The Way*, *Furrow*, *The Forge* | Scepter | Post-1930 | Scepter / the Prelature's rights office |
| Romano Guardini | *The Lord*, *The Spirit of the Liturgy* | Regnery; Ignatius | Post-1930 | Publishers |
| Joseph Ratzinger | *Introduction to Christianity*, *Spirit of the Liturgy*, *Jesus of Nazareth* | Ignatius Press; Doubleday | Post-1930 | Ignatius Press; Libreria Editrice Vaticana for papal-era material |
| Balthasar, de Lubac | Major works | Ignatius Press | Post-1930 | Ignatius Press |
| Dietrich von Hildebrand | *Transformation in Christ*, etc. | Hildebrand Project / Sophia | Post-1930 | Hildebrand Project |
| Maritain, Gilson | Later works | various | Post-1930 (their 1924-1930 English titles are in A2 or PD) | Publishers |

---

## 4. List C: flagged or excluded, with the facts

### Rule A (persons)

| Person | Facts | Church's final word | Recommendation |
|---|---|---|---|
| Meister Eckhart (about 1260-1328) | John XXII's bull of 27 March 1329 (*In agro dominico*) condemned 17 of his propositions as heretical and 11 as suspect. Before his death he publicly retracted any error his words could bear and submitted to the Holy See, which the bull records. [CE](https://www.newadvent.org/cathen/05274a.htm) | Died in communion; propositions condemned | Exclude by default. CCEL has Claud Field's *Sermons* (1909?) and a German text only |
| Peter Abelard (1079-1142) | Council of Sens 1141 condemned propositions; Innocent II confirmed. Peter the Venerable reconciled him with Bernard and received him at Cluny. [CE](https://www.newadvent.org/cathen/01036b.htm); BXVI set him beside Bernard in the [audience of 4 November 2009](https://www.vatican.va/content/benedict-xvi/en/audiences/2009/documents/hf_ben-xvi_aud_20091104.html) | Reconciled; died in communion | Keep-with-label possible, but the only free text (*Historia Calamitatum*, Bellows tr., CCEL) is autobiography with little search value. Exclude for now |
| François Fénelon (1651-1715) | Innocent XII condemned 23 propositions from the *Maximes des saints* in 1699; Fénelon announced his acceptance from the pulpit. [CE](https://www.newadvent.org/cathen/06035a.htm) | Submitted; died in communion | Exclude *Maxims of the Saints* (CCEL). Other works (CCEL *Existence of God*, *Spiritual Progress*) could be kept with a label; *Spiritual Progress* is mixed with Guyon, so exclude that one |
| Madame Guyon (1648-1717) | Her *Moyen court* was placed on the Index in 1688; she submitted to the condemnation. [CE](https://www.newadvent.org/cathen/07092b.htm) | Work condemned | Exclude (CCEL has several) |
| Miguel de Molinos (1628-1696) | Innocent XI condemned 68 propositions from the *Spiritual Guide* in 1687. [CE, Quietism](https://www.newadvent.org/cathen/12608c.htm) | Work condemned | Exclude (CCEL `molinos/guide`) |
| Blaise Pascal (1623-1662) | Wrote the *Provincial Letters* (1656-57) for the Jansenist side. Died after receiving the sacraments. [IEP](https://iep.utm.edu/pascal-b/). The request says the *Letters* were put on the Index; I did not confirm the decree from a primary source | Died in communion | Exclude the *Provincial Letters*. *Pensées* (Trotter, CCEL ThML, 99k) is a keep-with-label option for apologetics; Carter to decide |
| Antonio Rosmini (1797-1855) | Holy Office decree *Post obitum* (1887) condemned 40 propositions. The CDF said in 2001 that the reasons for it "can now be considered superseded." [CDF note, 1 July 2001](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_20010701_rosmini_en.html). Beatified 18 November 2007. [Benedict XVI, Angelus](https://www.vatican.va/content/benedict-xvi/en/angelus/2007/documents/hf_ben-xvi_ang_20071118.html) | Blessed; condemnation superseded | Passes rule A. No free English of note found; not a candidate now |
| Pierre Teilhard de Chardin (1881-1955) | Holy Office *monitum* of 30 June 1962 warned that his works contain "ambiguities and indeed even serious errors"; a 1981 Holy See communiqué said the warning still stands. [EWTN reprint of the monitum](https://www.ewtn.com/catholicism/library/monitum-on-the-writings-of-fr-teilhard-de-chardin-sj-2144) | Died a Jesuit in communion; works under warning | Exclude. Works are also in copyright |
| Cornelius Jansen (1585-1638) | *Augustinus* condemned by Urban VIII and five propositions by Innocent X (1653). He had submitted the book to the Holy See before death. [CE](https://www.newadvent.org/cathen/08285a.htm) | Died in communion; work condemned | Exclude |
| Pasquier Quesnel (1634-1719) | 101 propositions from his *Réflexions morales* condemned in *Unigenitus* (1713); he kept appealing against it and died at Amsterdam. [CE](https://www.newadvent.org/cathen/12601c.htm) | Did not submit | Exclude |
| Félicité de Lamennais (1782-1854) | *Paroles d'un croyant* condemned by Gregory XVI in [*Singulari nos*](https://www.papalencyclicals.net/greg16/g16singu.htm) (1834). He refused reconciliation and was buried without rites. [1911 Britannica](https://en.wikisource.org/wiki/1911_Encyclop%C3%A6dia_Britannica/Lamennais,_Hugues_F%C3%A9licit%C3%A9_Robert_de) | Died outside communion | Exclude |
| Alfred Loisy (1857-1940) | Excommunicated *vitandus* by the Holy Office, 7 March 1908. [Encyclopedia.com (New Catholic Encyclopedia text)](https://www.encyclopedia.com/humanities/encyclopedias-almanacs-transcripts-and-maps/loisy-alfred-1857-1940) | Died outside communion | Exclude |
| George Tyrrell (1861-1909) | Excommunicated 1907; denied Catholic burial because he had not retracted. [Britannica](https://www.britannica.com/biography/George-Tyrrell) | Died under excommunication | Exclude |
| Erasmus (about 1466-1536) | Died without the last sacraments, for reasons that "cannot now be settled." [CE](https://www.newadvent.org/cathen/05510b.htm). His works were on the Index; I did not check the Index entries themselves | Never condemned as a heretic; not a theologian of this kind | Exclude (CCEL has *Praise of Folly*, satire) |
| William of Ockham (about 1287-1347) | Excommunicated 6 June 1328 for leaving Avignon without permission. [SEP](https://plato.stanford.edu/entries/ockham/). No reconciliation is documented in the sources I read | Uncertain whether reconciled | Exclude |
| Joachim of Fiore (about 1135-1202) | Lateran IV (1215) condemned his teaching on the Trinity. In 1200 he submitted all his writings to Innocent III. [CE](https://www.newadvent.org/cathen/08406c.htm) | Died in communion; one doctrine condemned | Exclude (no useful English anyway) |
| Jean Gerson (1363-1429) | Chancellor of Paris. The 1883 CCEL edition's title page calls him "the Most Christian Doctor." No condemnation found. [CCEL, *Snares of the Devil*](https://ccel.org/ccel/gerson/snares) | No censure found | Passes; low priority |

### Rules B and C (authorship)

| Item | Problem | Recommendation |
|---|---|---|
| Pseudo-Dionysius | Pseudonymous (about 500) but not a heretic's forgery. The writings were accepted as genuine and used against the Monothelites at the Lateran Council of 649. [CE](https://www.newadvent.org/cathen/05013a.htm). Aquinas and Bonaventure cite him constantly | Keep with label "Pseudo-Dionysius (about 500), writing under the name of Dionysius the Areopagite" |
| *On Cleaving to God* (CCEL `albert/cleaving`) | CCEL's own translator's introduction says "almost all modern scholars are agreed that the work could not have been written by him." Also a modern translation of uncertain date | Exclude, or keep as anonymous with no Albert attribution |
| Tauler, *The Following of Christ* (CCEL) and *Meditations on the Life and Passion* (CCEL, 1875) | The CCEL front matter itself says the first may not "proceed from Tauler himself." I did not verify the *Meditations* attribution | Exclude the first; hold the second until its authorship is checked. Keep *The Inner Way* |
| *The History and Life of the Reverend Doctor John Tauler* (Winkworth 1857, IA) | IA credits the narrative to the "Gottesfreund im Oberland" and Rulman Merswin, not to Tauler. Its reliability was not researched | Exclude the narrative; the 25 sermons could stay after an authorship check |
| Pseudo-Bonaventure, *Meditations on the Life of Christ* | Printed under Bonaventure's name; not sourced here, but modern editions do not treat it as his | Do not ingest under his name without checking |
| *Little Flowers of St Francis*, *Mirror of Perfection* | Not by Francis; later Franciscan compilations | Keep, credited to "Anonymous Franciscan, 14th century" |
| Anselm, *Book of Meditations and Prayers* (M. R., 1872) | Older collections printed under Anselm's name may include pieces by others. Not researched here | Check each piece's authenticity against a modern edition before ingesting; prefer Webb's 1903 *Devotions* until then |
| *Theologia Germanica* | Anonymous 14th-century German treatise, first printed by Luther. Its Church standing was not researched | Exclude unless researched |
| Mechthild of Magdeburg (Bevan 1896) | Extracts chosen by the translator, not the whole book; Mechthild is not canonized ([CE](https://www.newadvent.org/cathen/10106a.htm)) | Low priority; acceptable, but label as selections |
| Faustina, *Diary* | A 1959 Holy Office notification forbade spreading the devotion "in the forms proposed by" her; the CDF declared it no longer binding on 15 April 1978. [CDF notification](https://www.vatican.va/roman_curia/congregations/cfaith/documents/rc_con_cfaith_doc_19780415_kowalska_en.html). Canonized 2000 | Passes the content rules. Rights issue only (List B) |

### Out of scope or Carter's call

| Item | Facts | Recommendation |
|---|---|---|
| C. S. Lewis | Anglican, not Catholic | Out of scope unless Carter decides otherwise |
| Dante, *Divine Comedy* | Poet, not a theologian by trade. Strong papal commendation in Benedict XV's [*In praeclara summorum*](https://www.vatican.va/content/benedict-xv/en/encyclicals/documents/hf_ben-xv_enc_30041921_in-praeclara-summorum.html) (1921) and Francis's [*Candor lucis aeternae*](https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco-lettera-ap_20210325_centenario-dante.html) (2021). Longfellow translation (1867) is CCEL ThML, 113k | Carter's call. Poetry retrieves badly for doctrinal questions |
| Thomas Merton | Not censured. Works are in copyright (Merton Legacy Trust and publishers) | Not a candidate now |
| Chesterton | Lay apologist, not beatified | Include with "lay apologetics" label, as recommended above |
| Karl Adam, Gilson, Sheen (early), Tanquerey | Scholarly or manual writing, not spiritual classics | Include only if the collection's brief extends to modern theology |

### Rights flags on texts that look free

| Text | Problem | Use instead |
|---|---|---|
| CCEL *Ascent of Mount Carmel*, *Dark Night* (Peers, 3rd rev. ed. 1953, Image 1959) and *Way of Perfection* (Peers, Image 1964) | The Dark Night file says it was scanned from an "uncopyrighted 1959 Image Books third edition." Peers's translation first appeared in the UK in the 1930s; a UK work still protected there in 1996 had its US copyright restored under the URAA regardless of US notice. Peers died in 1952, so it was protected in the UK in 1996 | Lewis (A2 #1) and Dalton (A2 #4) |
| CCEL Chesterton *St. Thomas Aquinas* | Published 1933; restored UK work; US public domain on 1 January 2029 | Wait |
| CCEL More *Dialogue of Comfort* | Monica Stevens's modernization, Sheed & Ward 1951 (from Gutenberg). Gutenberg's clearance was probably a non-renewal finding, but Sheed & Ward published in London and New York, so restoration is possible | Everyman 1910 text (A2 #31) |
| CCEL Bonaventure *Mind's Road to God* | Boas, 1953 | List B, renewal search |
| CCEL Alphonsus *Uniformity with God's Will* | Tobin translation, TAN, undated; its preface cites a 1933 Italian edition, so the translation is after 1933 | Centenary Edition (A2 #6) |
| CCEL Brother Lawrence *Practice* | Epworth Press "Authentic Edition", no date in file | Gutenberg 13871 (A2 #11) |
| Gutenberg 5657 (Brother Lawrence) | "Copyright (C) 2002 by Lightheart" in the text | Gutenberg 13871 |
| CCEL *Little Flowers* (`ugolino/flowers`) | Heritage Press edition with Livingston introduction, 1930s | IA 1899 Okey revision (A2 #23) |
| CCEL *Nature and Grace* (Fairweather, Westminster Press 1954) | Summa selections; 1954 and a duplicate of our Summa | Skip |
| CCEL *Celestial Hierarchy* (`dionysius/celestial`) | No edition named in the file | Parker 1894 (A2 #45) |
| Newman Reader | Newman's text is PD; the site claims copyright on its edition | Gutenberg and IA; or ask NINS |
| isidore.co *Contra Gentiles* | Hanover House 1955-57 translation, now University of Notre Dame Press | English Dominican 1923-29 (A2 #41) |

---

## 5. Boundary notes

**Fathers versus this collection.** The line at about 750 puts these with the Church Fathers, not here: Gregory the Great (d. 604), Isidore of Seville (d. 636), Bede (d. 735, Doctor 1899) and John Damascene (d. about 749, Doctor 1890). CCEL has Bede's *Ecclesiastical History* (Sellar, Bell 1907, 123k words) and Gregory's *Life of St Benedict* with the Rule (1898, 39k); both are CCEL ThML and public domain but belong to the Fathers. Boethius (d. 524) is already in `medieval` and is a Fathers-era writer by date; either move him to the Fathers collection or record why he stays. Pseudo-Dionysius (about 500) is also Fathers-era by date. He could sit in either; Fathers is the more consistent home.

**Aquinas outside the Summa.** The CCC has 11 footnotes to Aquinas works outside the Summa. They cite the *Summa contra Gentiles* (twice), the Creed and Commandments sermons, a Psalms commentary, Hebrews, the *Sentences* commentary, *De malo*, the Corpus Christi office and *Adoro te*. Three options:

1. Rename `summa` to "Thomas Aquinas" and put everything of his there. Cleanest for users, who search for Aquinas as one author.
2. Keep `summa` pure and put the other works here. Simple, but Aquinas then appears in two collections under one name.
3. Put the *Catena Aurea* with scripture commentary if such a collection is ever added, since it is almost entirely quotations from the Fathers.

Option 1 is the recommendation. It also solves a problem with the *Catena*. Most of its text is quotations from the Fathers, so filed here it would pull Fathers passages into this collection's results.

**Newman.** He is now a Doctor and his Catholic and Anglican writings are all public domain. The *Parochial and Plain Sermons* are from his Anglican years. He republished them as a Catholic, so they pass the rules, but label the date.

---

## 6. Open questions for Carter

1. Should the Summa collection become an Aquinas collection (section 5, option 1)?
2. Which translation of *On Loving God* did we ingest? The vendored file names no translator.
3. The vendored Boethius is Cooper (1902), not H. R. James. Fine to keep, or switch to James (Gutenberg 14328)? And should Boethius move to the Fathers?
4. Do we accept "public domain by non-renewal" (the 1940 Bruce *Imitation*, possibly the 1930s-1950s Herder books) on the strength of a renewal search, or do we require a pre-1931 edition?
5. Are lay and non-canonized writers in scope (Chesterton, Knox, Julian, the *Cloud* author, Tauler, Hilton)? The rules allow them; the collection name suggests yes.
6. Is Dante in or out? Pascal's *Pensées*?
7. Does the collection extend to modern manuals and theology (Tanquerey 1930, Marmion, Scheeben, Möhler), or stop at spiritual classics?
8. Should we spend on licences? Hildegard, Peter Damian and Bonaventure's systematic works are Doctors with no free English. Paulist Press and Cistercian Publications cover most of the gap.
9. Scanned items need OCR clean-up, which ThML does not. Is there budget for an OCR clean-up pass, or should phase one be CCEL ThML plus Gutenberg text only (A1 plus A2 rows marked "text")?
10. CCEL asks for permission to republish its editions even where the base text is public domain ([CCEL copyright policy](https://www.ccel.org/about/copyright.html), as noted in `corpus-expansion-candidates.md`). We already ingest CCEL ThML for four works. Has that permission been sought?
