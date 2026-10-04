# R4. Are the Refutation's book contents authorial?

4 October 2026. Spec: R4 in `docs/corpus-cleanup/P0-checks-identity-research.md`. Consumer: 1.8a in `docs/corpus-cleanup/P1b-adapters-catechism-summa-fathers.md`.

**Answer: yes.** The short tables of contents at the head of Books I and V to X are in the Greek manuscripts, and the modern translator credits them to the author. Rule G does not apply to them. 1.8a keeps the seven `Contents.` divs and removes only the ANF heading lines inside them, plus the translator credit at the top of Book I.

## 1. What the Greek manuscript tradition has at the head of each book

The work survives in two manuscript groups.

- **Book I** circulated on its own as the *Philosophumena*. Legge counts four early copies (Medicean, Turin, Ottobonian, Barberine). Litwa counts five, all ascribing the work to Origen (Litwa xxvii).
- **Books IV to X** survive in one fourteenth-century manuscript found on Mount Athos in 1841 and deposited in Paris in 1842, Parisinus Supplément grec 464 ("P", Litwa xxviii). Books II and III and the opening of Book IV are lost. Miller's 1851 preface describes the codex: 137 cotton-paper leaves, copied by one Michael.

**Both groups carry the table.** Each surviving book opens with the formula τάδε ἔνεστιν ἐν τῇ … τοῦ κατὰ πασῶν αἱρέσεων ἐλέγχου ("these are the contents of the … [book] of the Refutation of all Heresies"), followed by a short list of what the book covers.

- Legge prints the Book I formula in his note and says "This formula is repeated at the head of Books V-X with the alteration of the number only" (Legge vol. 1, p. 31 n. 2). So it stands in the Book I manuscripts and in P.
- At the head of Book IV, Legge explains that the first pages of P are torn away, so the reader is "deprived of the small Table of Contents which the author has prefixed to the other seven" (Legge vol. 1, p. 66). That is why the corpus has no Book IV contents.
- Litwa (2016) uses the tables as the manuscript evidence for the work's title. The manuscripts give no title for the whole treatise, but "the brief tables of contents at the head of each book" consistently call it the Refutation of All Heresies (Litwa xxviii).
- On authorship, Litwa writes in his "Organization" section: "Apparently, our author himself adds the tables of contents that begin each book" (Litwa xliv).

**Marcovich (PTS 25, 1986) was not reachable.** No preview, library copy or open text could be fetched. Litwa's Greek text is a revision of Marcovich's, keeping some of his emendations and discarding others (Litwa's introduction; Poirier 2018; Cosentino 2018), and Legge worked from Cruice's Greek, so the two sources above are the critical-edition tradition at one remove. Nothing found disputes the tables.

**Two things not to confuse with the tables:**
- The **summary in the body of Book X** (the "Epitome of all Philosophers" and "Epitome of all Heresies", chapters following `iii.iii.viii.i`) is a separate question. Legge notes that some critics gave it to another hand, but concludes it is "by Hippolytus' own hand" (Legge vol. 1, pp. 19–20). It is ordinary chapter text and out of scope here.
- The **chapter titles** in ANF (the `title` attributes on the `type="Chapter"` divs) are the editor's. 1.8a leaves them out of scope already.

## 2. What the ANF translator and editor say

Vendored file: `datapipeline/sources/church-fathers/third-century-2.xml` (ANF volume 5). The Refutation is `div2 iii.iii`. The translator is J. H. MacMahon. The American editor is A. Cleveland Coxe, whose own notes are the bracketed ones.

- **Neither says the tables are editorial.** MacMahon translates each table as running text with the lead-in sentence "The following are the contents of the … book of the Refutation of all Heresies". His notes on the tables treat them as manuscript Greek, giving variant readings like those he gives for any author text:
  - `iii.iii.i.i-p8` (note 20, Book I): the four Book I manuscripts' inscriptions, one of which reads "Of Origen's Philosophumena…these are the contents".
  - `iii.iii.iii.i-p8.1` (Book V): "The ms. employs the form Sithians".
  - `iii.iii.v.i-p7.1`, `-p17.1`, `-p19.1` (Book VII): Miller's readings "Satronilus" and "Sacerdon"; μόνος "occurs in Miller's text" and "crept into the ms."
- **The translator's Introductory Notice** (quoted by Coxe in `div2 iii.ii`, from `iii.ii-p22` on) describes the plan of the ten books in MacMahon's own words. It does not mention the tables.
- **Coxe's Elucidations and General Note** (`div3 iii.iii.ix` and `iii.iii.x`) do not mention the tables either. 1.8a already removes both under rule G.

So the edition marks the tables as translated text. The only editorial material around them is ANF's typesetting (title line, translator credit, rules, the "Book N." and "Contents." headings) and the endnotes.

## 3. Verdict for each live passage

The adapter (`ingest/church_fathers.py` → `ingest/common.py:iter_chapters`) emits one passage per `Contents.` div. Book I's div is long enough to split into two passages, so there are 8 passages for 7 divs. Book IV has no contents div. A local adapter run (no production query) gives 2,621 + 887 + 1,278 + 811 + 2,450 + 1,203 + 872 + 243 = 10,365 characters. This matches the spec.

Every stored passage is **mixed**: the table is authorial, but the passage also contains ANF heading lines and inlined endnotes.

| Passage anchor | Div id | Authorial (keep) | Editorial (remove) |
|---|---|---|---|
| `the-refutation-of-all-heresies/book-i/contents/p1` | `iii.iii.i.i` | `-p7`, `-p9`, `-p10` | `-p1` title line, `-p2` translator credit, `-p3`, `-p5` rules, `-p4` "Book I.", `-p6` "Contents."; notes 20 and 21 (`-p7.2`, `-p10.1`) |
| `the-refutation-of-all-heresies/book-i/contents/p2` | `iii.iii.i.i` | `-p12`, `-p13` | note 22 (`-p13.1`) |
| `the-refutation-of-all-heresies/book-v/contents` | `iii.iii.iii.i` | `-p4`, `-p6`, `-p7`, `-p8`, `-p11` | `-p1` "Book V.", `-p2` rule, `-p3` "Contents."; notes `-p4.1` (Coxe, bracketed), `-p8.1`, `-p9.2` |
| `the-refutation-of-all-heresies/book-vi/contents` | `iii.iii.iv.i` | `-p4` to `-p8` | `-p1` "Book VI.", `-p2` rule, `-p3` "Contents." |
| `the-refutation-of-all-heresies/book-vii/contents` | `iii.iii.v.i` | `-p4`, `-p5`, `-p7`, `-p9` to `-p12`, `-p14`, `-p15`, `-p17`, `-p19`, `-p21` | `-p1` "Book VII.", `-p2` rule, `-p3` "Contents."; notes `-p5.1` (Coxe), `-p7.1`, `-p12.1`, `-p15.1`, `-p17.1`, `-p19.1`, `-p21.1` |
| `the-refutation-of-all-heresies/book-viii/contents` | `iii.iii.vi.i` | `-p5`, `-p6`, `-p7`, `-p9` to `-p12` | `-p1` "Book VIII." with its note `-p1.2`, which the stored passage inlines as its opening words "Much that we have in this book is quite new…"; `-p3` rule, `-p4` "Contents."; notes `-p7.1`, `-p12.1` (Coxe) |
| `the-refutation-of-all-heresies/book-ix/contents` | `iii.iii.vii.i` | `-p4` to `-p7`, `-p9` | `-p1` "Book IX.", `-p2` rule, `-p3` "Contents."; note `-p7.1` |
| `the-refutation-of-all-heresies/book-x/contents` | `iii.iii.viii.i` | `-p4` to `-p7` | `-p1` "Book X.", `-p2` rule, `-p3` "Contents." |

Sources for the "authorial" column: Litwa xxviii and xliv, Legge vol. 1 pp. 31 n. 2 and 66, and MacMahon's notes listed in section 2. The "Book N." and "Contents." lines are ANF headings with no Greek equivalent; the Greek lead-in is the "The following are the contents…" sentence, which stays.

## 4. Rule for 1.8a

All ids are in `third-century-2.xml`.

1. **Keep these seven divs as passages:** `iii.iii.i.i`, `iii.iii.iii.i`, `iii.iii.iv.i`, `iii.iii.v.i`, `iii.iii.vi.i`, `iii.iii.vii.i`, `iii.iii.viii.i`. Each is a `div4` titled `Contents.`. As specified, `EDITORIAL_DIV_TITLE` strips the trailing period and includes `contents`, so it would skip all seven. 1.8a must exempt them. Two options: exempt these ids, or match `contents` only as the existing exact front-matter title (today's `_SKIP_TITLES` entry, inherited by `_SKIP_WORK_TITLES`, which already drops the editorial "Contents" divs in `confessions.xml` and `on-the-holy-trinity.xml`). The vendored Fathers sources have no other `Contents.` divs. The same exemption applies to 1.8a's acceptance check "0 passages with a label matching `EDITORIAL_DIV_TITLE`": the seven passages keep their "Book N · Contents" labels until 1.8c relabels them, so the check must skip these ids or match labels exactly.
2. **Remove these paragraphs as `span` entries** (reason `rule-g-editorial`), because the passages survive:
   - `iii.iii.i.i-p1` to `iii.iii.i.i-p6`
   - `iii.iii.iii.i-p1` to `-p3`, `iii.iii.iv.i-p1` to `-p3`, `iii.iii.v.i-p1` to `-p3`, `iii.iii.vii.i-p1` to `-p3`, `iii.iii.viii.i-p1` to `-p3`
   - `iii.iii.vi.i-p1`, `-p3`, `-p4` (Book VIII has no `-p2`; its rule is `-p3`)

   `strip_editorial_lines` already covers `-p2` of Book I (the translator credit) and the rule lines. The "Book N." and "Contents." headings count as title lines. The chapter label "Book N · Contents" keeps the same information.
3. **Keep everything else in these divs**, from the "The following are the contents…" paragraph onward.
4. **The endnotes inside them belong to 1.10's note strip, not 1.8a.** That includes the note on the Book VIII heading, which currently opens the stored Book VIII passage.
5. **None of the removed text carries an authenticity judgment.** The judgment regex has nothing to copy from these spans. Note 20 (`iii.iii.i.i-p8`) records the manuscripts' ascription to Origen, but it is a note and goes with 1.10.

On the label: Litwa and Legge both call these the book's "tables of contents", so "Book N · Contents" describes them correctly. 1.8a's Changes say to relabel authorial contents "Book N · Summary" in 1.8c. That is 1.8c's design choice, and this memo does not change it.

## Sources

- M. David Litwa, *Refutation of All Heresies*, Writings from the Greco-Roman World 40 (Atlanta: SBL Press, 2016), introduction pp. xxvii–xxviii (manuscripts, title) and p. xliv ("Organization"). Read through a web copy of the book; page numbers are the printed ones.
- F. Legge, trans., *Philosophumena; or, The Refutation of All Heresies*, vol. 1 (London: SPCK, 1921), pp. 1, 19–20, 31 n. 2, 66. Public domain: https://archive.org/details/philosophumenaor01hippuoft
- E. Miller, ed., *Origenis Philosophumena sive Omnium Haeresium Refutatio* (Oxford, 1851), Praefatio pp. v–vi (description of P). https://archive.org/details/origenisphilosop00hipp
- ANF05 ThML, `third-century-2.xml`: translator's notes and Coxe's Introductory Note, Elucidations and General Note, as cited by id above.
- Reviews of Litwa, checked for comment on the tables (none found): P. W. van der Horst, BMCR 2016.12.05, https://bmcr.brynmawr.edu/2016/2016.12.05/; A. Cosentino, RBL 01/2018, https://mdavidlitwa.com/wp-content/uploads/2018/01/cosentino-review-of-litwa-refutation.pdf; P.-H. Poirier, *Laval théologique et philosophique* 74.3 (2018) 447–453, https://www.erudit.org/fr/revues/ltp/2018-v74-n3-ltp04744/1061892ar/
- **Not reached:** M. Marcovich, ed., *Hippolytus: Refutatio omnium haeresium*, PTS 25 (Berlin: de Gruyter, 1986); P. Wendland, ed., GCS 26 (Leipzig, 1916). Google Books asked for a CAPTCHA, which was not attempted, and the copies found were offline.

## For Carter

Nothing to decide. The sources agree.
