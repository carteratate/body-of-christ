# Headings inside passages: survey and proposal

Research and design only (22 Nov 2026). Nothing in the app, the datapipeline or production
changed. The survey read the live corpus on production through a read-only transaction.
The build issue this proposes is linked from the PR that adds this file.

## Summary

- **About 4,600 heading lines sit inside about 4,200 of the 51,438 live passages**, in eight
  of the ten collections. The Bible and Canon Law have none. Almost all of them are in the
  text **on purpose**: the adapters for Vatican II (1.1), the papal collections (1.3a), Trent
  (1.2e) and the Catechism's US edition (#279) move each heading onto the passage it
  introduces, and City of God's capitula stay by decision. Only a small set are leftovers
  (listed below).
- **The card shows them at body size** because `PassageText` renders the whole passage as one
  `whitespace-pre-wrap` paragraph. **The reader is worse**: `Passage.tsx` has no `white-space`
  rule, so every paragraph break collapses. The heading runs into the first sentence
  ("§79 SECTION 1 The Avoidance of War Even though recent wars…"), and the paragraphs of
  12,079 passages run together. That reader defect is web-only and can be fixed without a
  publish.
- **Proposal: three heading levels and an epigraph style, the same in every collection,**
  set in the passage's own face (Geist on the card, Georgia in the reader). No new tokens.
  `font-brand` stays out of passages. The reader hides a level-1 heading that repeats the
  chapter heading directly above it (611 passages).
- **Recommendation: mark headings in the data at build time** as character offsets in
  `chunks.metadata.headings`, the way `metadata.footnotes` already works. The words stay in
  `content`, so search, embeddings and IDs do not change. Only the build knows Trent's
  dotted titles, the Catechism's structural titles, papal epigraphs and the chapter tier,
  and a text heuristic in the web app would misread about 400 lines it cannot tell apart. It
  needs a metadata-only republish of seven collections after the republish lock lifts on
  4 Dec 2026.
- Mock-ups for both themes and both widths are in `docs/screenshots/2026-11-22-passage-headings/`.

## 1. Survey

### Method

All live, searchable passages (`retired_at IS NULL` on the passage and its document,
`searchable` true): 51,438 rows read once into a scratch file and classified in Python.
Paragraphs are the `\n\n`-separated blocks of `content`. A paragraph is a heading candidate
when it is one line of at most about 110 characters, does not open with `§`, a verse marker
or a quotation mark, and has no closing sentence punctuation, or when it matches a
division pattern (`PART`/`SECTION`/`CHAPTER`/`ARTICLE`… with a number, a Roman or letter
numeral, `Chapter N.—Title`). Kinds and positions were recorded and every bucket was
spot-checked by eye (12 to 16 random lines each). Collection-specific second passes caught
what the general rule cannot: Trent's and Anselm's titles end in a full stop.

The datapipeline's dry-run build was not run. The live corpus is what the 20 Nov 2026
republish built, and readers see it. Counts are heuristic: treat them as accurate to a few
percent, with the false positives named below removed.

### Counts

| Collection | Passages | With a heading line | Heading lines | Where they sit |
|---|---:|---:|---:|---|
| Catechism | 787 | 673 (86%) | 866 | 667 opening, 199 inside; opening stacks up to 5 lines |
| Apostolic exhortations | 2,968 | 1,356 (46%) | 1,538 | 1,340 opening, 198 inside |
| Papal documents | 487 | 167 (34%) | 184 | 165 opening, 17 inside, **2 trailing** |
| Encyclicals | 5,237 | 1,105 (21%) | 1,176 | 1,089 opening, 86 inside, **1 trailing** |
| Councils | 1,728 | about 259 (15%) | about 260 | Trent's 201 printed chapter titles plus 59 Vatican II heads, all opening |
| Medieval | 444 | about 90 (20%) | about 90 | Anselm's chapter titles: Monologium 74, Proslogium 12, Cur Deus Homo 4 |
| Church Fathers | 6,776 | 516 (8%) | 516 | City of God's capitula, opening; **10 pieces hold only the capitulum** |
| Summa | 27,730 | 9 | 9 | Question titles in 9 prologues (a leftover) |
| Bible | 3,535 | 0 | 0 | One paragraph per passage with `{{v:N}}` markers; the source has no section heads |
| Canon Law | 1,746 | 0 | 0 | Book/Part/Title/Chapter live in chapter labels only |
| **Total** | **51,438** | **about 4,175** | **about 4,640** | |

### Patterns by collection, with real examples

**Catechism** (US edition, #279). Four kinds, which the printed book tells apart by case:

- Structural titles, a level label then its title on its own line, in capitals: `Article 1`
  / `THE REVELATION OF GOD` (CCC §51–53), `CHAPTER TWO` / `I BELIEVE IN JESUS CHRIST, HIS
  ONLY SON, OUR LORD`, `PART TWO:` / `THE CELEBRATION OF THE CHRISTIAN MYSTERY`. The label is
  printed `Article 1` 61 times and `ARTICLE 2` 4 times. `Paragraph 1. I BELIEVE IN GOD` is the
  same level inside Article 1 of the Creed.
- Roman-numeral heads in capitals: `I. GOD REVEALS HIS "PLAN OF LOVING GOODNESS"`,
  `III. THE DIFFERENT KINDS OF SINS` (244).
- Sub-heads in sentence case: `Legitimate defense` (§2263–2267), `Avoiding war`
  (§2307–2315), `Divorce`, `The punishments of sin` (about 320). Some end in `…` because
  they quote: `In the person of Christ the Head …`.
- `IN BRIEF`, 81 times (its passages are already flagged `metadata.is_in_brief`), and `PROLOGUE`.

The deepest opening stack is CCC §456–460: `Article 3` / `WHO WAS CONCEIVED BY THE HOLY
SPIRIT, BORN OF THE VIRGIN MARY` / `Paragraph 1. THE SON OF GOD BECAME MAN` / `I. WHY DID
THE WORD BECOME FLESH?`.

**Councils.** Vatican II: `SECTION 1 The Avoidance of War` (Gaudium et Spes §79, six more
sections in GS and six in Presbyterorum Ordinis; one prints `SECTION THREE` in words),
`ARTICLE 1: Christian Witness` (Ad Gentes), `I. Diocesan Bishops` and `2. The diocesan
curia and commissions` (Christus Dominus), `A) General norms` to `F) The Promotion of
Pastoral-Liturgical Action` (Sacrosanctum Concilium), and Gravissimum Educationis's titled
sections (`Christian Education`). Trent: Waterworth's printed chapter titles, which end in a
full stop: `On the gift of Perseverance.`, `Property is wholly prohibited to Regulars.` (201
of 209 chapters).

**Papal (encyclicals, exhortations, papal documents).** The source prints three tiers, in
whatever case each document uses: named divisions (`CHAPTER ONE: WHAT IS HAPPENING TO OUR
COMMON HOME`, `PART ONE: THE EUCHARIST, A MYSTERY TO BE BELIEVED`, `CHAPTER III - THE HOLY
SPIRIT: THE PRINCIPAL AGENT OF MISSION`), numbered sections (`I. POLLUTION AND CLIMATE
CHANGE`, `I - STAGES OF PASTORAL CARE OF THE FAMILY`, `D. The inculturation of the Gospel
and the evangelization of culture`) and plain headings (`Climate as a common good`, `The
table of the word`, `An Annual Novena Decreed`). Also `INTRODUCTION` and `CONCLUSION`
(64). Stacks of two or three are common: Familiaris Consortio §65 opens with all
three tiers. Scripture **epigraphs** sit under some headings: `"This is the work of God:
that you believe in him whom he has sent" ( Jn 6:29)` (Sacramentum Caritatis §6), and the
adapter already tokenizes them as `epigraph` (`ingest/papal_common.py`).

**Church Fathers.** City of God only: `Chapter 26.—That in Certain Peculiar Cases the
Examples of the Saints are Not to Be Followed.` (516 chapters).

**Medieval.** Anselm's chapter titles under bare labels ("Chapter XXIV"): `How it is better
understood to exist always than at every time.` Most end in a full stop.

**Summa.** Nine prologues open with the question title in capitals, `OF VOWS (TWELVE
ARTICLES)`, while their chapter label carries a treatise heading ("Question 88 - Service by
Promise (Q. 88) — Prologue"). The other 606 prologues have the title in the label and not in
the text ("Question 76 - OF CURSING (FOUR ARTICLES) — Prologue").

### False positives (short lines that are text)

These must not be styled as headings. Counts are what the general rule matched before the
filters removed them.

| Kind | Where | Examples |
|---|---|---|
| Quotation lead-ins ending `:—` | Fathers (268), medieval | `And Pindar:—`, `Then he adds:—` |
| Verse lines | Fathers (40), Summa, Catechism | `While others purge their guilt deep-dyed`, `"Gather, uphold, spur on` |
| Lines opening with a quotation mark | everywhere (4,970, mostly Summa objections) | filtered by their first character |
| One-line replies with no stop | Summa (61) | `This suffices for the Reply to the First Objection` |
| Signatures | papal (about 80), Trent | `JOHN PAUL II`, `PIUS PP. IX.`, `FRANCISCUS`, `A. Cardinal FARNESE, Vice-Chancellor` |
| Dating lines and salutations | papal (about 90) | `Given at Rome…`, `Venerable Brethren, Greetings and Apostolic Benediction` |
| Session lines and intitulations | Trent (about 20) | `Celebrated on the seventh day of the month of January, 1546.`, `PAUL, bishop, servant of the servants of God…` |
| Table rows | Catechism §2051 | the Decalogue's `You shall have no other gods before me …` |
| Epigraphs | Catechism, papal | `You shall not kill.`, `"Teacher, what must I do …?"` (styled, but as epigraphs) |
| Numbered canons and list items | Apostolic Canons, Canon Law, Summa | `XLVII.1. Let a bishop be ordained…`, `(1) What is a vow?`, `- the use of arms must not…` |
| `§` paragraphs | Canon Law (864 passages), Catechism | `§1. Universal or particular customs…` |

## 2. Existing rules: on purpose or left over

### Kept in the text on purpose

| Collection | Rule | Where it is recorded |
|---|---|---|
| Councils (Vatican II) | "A short unnumbered paragraph with no final punctuation and mostly capitals … is a subheading. Prepend it as the first line of the next section rather than creating a card." | 1.1, `P1a-…md` |
| Councils (Trent) | "A chapter's printed title is its first paragraph." | 1.2e, `P1a-…md` |
| Papal | "A heading moves to the start of the next section, chapter headings too, and packing keeps a heading on the same card as its paragraph." The top tier becomes the reader chapters. | 1.3a (C-08), `P1a-…md` |
| Catechism | #279 carries "heading text inside passages" over to the US edition's words; `catechism_headings.py` corrects misprints for the labels, the tree and the text. Sentence case is the US edition's. | Decision log "Catechism US edition (#279)"; 1.6 as built |
| City of God | "City of God's ancient capitula stay in the text." Later editors' titles elsewhere (On the Trinity, On Christian Doctrine, the Banquet, Tertullian) moved into labels. | Decision log "Editors' chapter titles in passage text" (9 Oct 2026) |
| Fathers (1.9) | A title line that repeats a full label leaves the text under rule G, so the title appears once. Three passages. | Decision log "Title lines that repeat a full label (1.9)" |
| Summa, Catechism trees | The hierarchy is navigation data in `document_contents` (0040, #250), built by `summa.build_contents` (#254) and `catechism.build_contents` (#253). It is separate from passage text. | CLAUDE.md §4 |

Rule G removes editors' headings and tables of contents, not authors'. Every heading kind
above is the author's or the official edition's.

### Leftovers (fix in the build, separately from styling)

1. **Trailing headings: 3.** A heading left at the end of a passage instead of opening the
   next one: Mater et Magistra §237 (`When Differences Arise …`), Rosarium Virginis Mariae §26
   (`A valid method …`) and §40 (`The family: parents …`). 1.3a found 982 of these and moved
   them; these three are run-in headings its rule misses because they end in `…`.
2. **City of God pieces that hold only the capitulum: 10.** For example "Book V · Chapter 2
   (part 1 of 2)" is just `Chapter 2.—On the Difference in the Health of Twins.` The splitter
   cut after the title. Packing should keep a title with its first paragraph, as 1.3a does for
   papal headings.
3. **Summa question titles in the text: 9 prologues** (q. 71 of I-II; qq. 63, 77, 78, 88 of
   II-II; q. 72 of III; Suppl. qq. 29, 34, 41). The title belongs in the chapter label, which
   took a treatise heading instead. Moving it fixes both.
4. **Anselm's chapter titles: about 90.** No decision covers them. They sit in the text
   under bare "Chapter N" labels, which is City of God's position. If they are Anselm's own
   capitula, they stay and take level 3. If they are the translator's, rule G moves them
   into the label. This needs Carter's call.

### How the reader and card show structure today

- **Reader chapter heading:** `ChapterSection.tsx` renders `chapter_label` as an `h2`, 20px
  semibold Georgia (`text-xl`). Passages follow in 16px Georgia at line-height 1.8 by default
  (reader settings 14/16/18px, 1.55/1.8/2.1).
- **Contents tree:** `ContentsTree.tsx`, 14px sans, level 1 semibold, a range label under
  each node in 12px muted. Only the Summa and the Catechism store one, and the Catechism's
  is refused (403) while it is excerpt-only.
- **Passage text in the reader:** `Passage.tsx`, a single `<p>` with no `white-space` rule
  (nothing in `components/reader` or `globals.css` sets one), so `\n\n` collapses to a space.
  The `unit_label` superscript (`§79`) sits before the first word, which today is the
  heading's.
- **Passage text on a card:** `PassageText.tsx`, one `<p>` at `text-sm leading-relaxed
  whitespace-pre-wrap`: headings at body size, separated by blank lines.
  `AttachedPassage.tsx` and `BookmarkCard.tsx` do the same.
- **Repeats:** 611 passages open with their own reader chapter's heading (exhortations 284,
  encyclicals 275, papal documents 40, councils 12), so the reader prints it twice in a row,
  once as the `h2` and once run into the text. The Catechism has 90 more, unseen while its
  reader is closed.

## 3. Proposal

### Levels

One scheme for every collection. The build assigns the level, because only it knows the
document's tiers.

| Role | What it is | Card | Reader |
|---|---|---|---|
| **Level 1**, division | A heading the reader's chapter label names: a Part, Section, Chapter or Article and its title, or a papal top-tier heading | 11px, semibold, capitals, tracking .08em, `brand-muted` | Same style at 12px, **hidden when the passage opens its chapter and the heading repeats the `h2`** |
| **Level 2**, section | One tier below the chapter | 12.5px, semibold, capitals, tracking .05em, `brand-primary` | 13.5px, same treatment |
| **Level 3**, sub-section | Anything deeper, and a work's own chapter titles inside a labelled chapter | 14px (body size), semibold, case as printed, `brand-primary` | 17px semibold, case as printed |
| **Epigraph** | A scripture line set under a heading | 13px `brand-muted`, a 2px rule at 30% and a 12px inset (the reader's "Earlier text" idiom) | 15px italic `brand-muted`, 1.25em inset |

Spacing: a heading's top space is always larger than its bottom space, so it reads with the
text below it. Stacked headings lose their top space. Card: level 2 20px above and 6px
below, level 3 18px and 4px, and paragraph gaps of 1em replace today's blank lines (the same
rhythm). Reader: 1.9em/.5em, 1.8em/.45em and 1.5em/.3em, paragraphs .9em apart. Body text
does not change size, face or colour anywhere.

**Case.** Levels 1 and 2 are set in capitals with CSS. Sources print the same level both
ways ("Article 1" and "ARTICLE 2"; papal documents in capitals or title case at random), and
uppercase-plus-tracking is the one treatment that makes them agree without rewriting stored
text. Level 3 keeps the printed case: the Catechism's sentence case is the US edition's
(#279), and a sentence-case sub-head in capitals would shout. Stored text never changes
case, so copying a passage copies what the source prints.

**Paired lines.** A level label printed on its own line before its title (`Article 1` /
`THE REVELATION OF GOD`, `CHAPTER TWO` / `I BELIEVE IN JESUS CHRIST…`) is one level-1
heading, shown on one line as "Article 1 · The Revelation of God". The build marks the pair.

**The unit marker.** In the reader, the `§N` superscript moves to the first body paragraph
after the opening headings, so it marks the paragraph and not the heading.

**Semantics.** In the reader, level 1–3 headings become `h3`/`h4`/`h5` under the chapter's
`h2`, so screen-reader heading navigation works. On cards they stay styled paragraphs: a
results page holds up to ten cards, and real headings would flood its outline.

**`font-brand` stays out.** CLAUDE.md §9 makes Judson in capitals the *brand* heading
font. Passage headings are corpus text that is searched, copied and quoted, and they should
read as the document's, not as TheoCorpus chrome. Judson's forced capitals would also erase
the case that carries level 3 in the Catechism, and it loads one weight, so it cannot show a
semibold. The passage's own face (Geist on the card, Georgia in the reader) keeps each
heading inside the passage it belongs to.

### By collection

| Collection | Level 1 | Level 2 | Level 3 | Epigraph |
|---|---|---|---|---|
| Catechism | Part, Section, Chapter, Article, "Paragraph N." with title, paired | Roman-numeral heads; `IN BRIEF` | sentence-case sub-heads | scripture under article titles (`You shall not kill.`) |
| Councils | (Vatican II chapters are labels, not text) | `SECTION 1 …`, `ARTICLE 1: …`, `I. …` | `A) …`, `2. …`, Gravissimum Educationis's titles, Trent's printed chapter titles | none |
| Encyclicals, exhortations, papal documents | the top tier (the chapter's own heading) | the next tier where a document prints one | plain headings | `epigraph` tokens |
| Church Fathers | none | none | City of God's capitula | none |
| Medieval | none | none | Anselm's titles, if they stay (leftover 4) | none |
| Summa | none: the 9 titles move to their labels | none | none | none |
| Bible, Canon Law | none | none | none | none |

Only the Catechism's cards change while it is excerpt-only. Its reader rules apply when it
is unblocked.

### Two ways to get there

**A. Mark headings in the data at build time.** Each adapter already finds its headings
before it joins them into the text: `papal_common.tokens` emits `heading` and `epigraph`
tokens and picks the chapter tier, `build_vatican2` keeps a `pending` list of subheadings,
`councils_trent` reads `<center>` titles, `catechism_us` knows each heading item's
`kind == "structure"`, and the Fathers editor already finds chapter title lines
(`editorial.CHAPTER_TITLE_WORKS` moves them into labels; City of God's would be marked
instead). The build would
write `chunks.metadata.headings = [{at, end, level, role}]`, character offsets into
`content` (`role` = `heading` or `epigraph`, plus `pairs_next` for a label line and
`chapter_title` when the heading repeats the chapter label). This is the pattern of
`metadata.footnotes` (`[{n, text, at}]`, #279): one API reader (`app/footnotes.py` is the
model), sent with each `chunk` event and reader passage, and drawn by one web component.

- `content` does not change, so embeddings, the keyword index, passage IDs, anchors and
  footnote offsets do not change, and the headings' words keep helping search ("legitimate
  defense" is a good match for its passage).
- It is exact. The build knows Trent's dotted titles, epigraphs, Catechism pairs and the
  chapter tier, and it never marks a signature, a verse line or a Summa reply.
- A check can hold it: every marked span is one whole paragraph, levels never skip
  downwards within a stack, and no marked span ends a passage (which also catches leftover 1).
- **Cost: a corpus publish.** The release report would show metadata changes only (no new,
  moved or retired passages and no re-embedding) for seven collections: Catechism, councils,
  the three papal collections, Fathers and medieval. No publish can run until the
  `republish-2026-10` lock entry is removed after its rollback window closes on 4 Dec 2026
  (4.1b step 13). It also touches six adapters, the API and the web.

**B. Detect headings in the web app.** A `lib/passage-headings.ts` with rules per collection.

- Ships with no publish and no API change.
- It cannot be exact. It would need about a dozen collection rules that copy what the
  adapters already know, in a second language. It still misses Trent's 201 titles and
  Anselm's 90, all of which end in a full stop, along with the epigraphs. It must filter
  about 400 lines that look like headings (Fathers lead-ins, signatures, Summa replies, the
  Decalogue table), and every new source would need a new rule.
- Levels would be guessed from case and numbering, which the sources use inconsistently, and
  pairs and chapter repeats would be matched by string comparison.

**Recommendation: A**, in one build PR plus the API and web, published with the next
metadata publish after 4 Dec. Write the web renderer so that it draws marks when present and
nothing otherwise, with no heuristic fallback, so collections switch over cleanly when
their marks arrive.

One piece needs no publish and is worth doing now as a small web PR: **keep paragraph
breaks in the reader** (render `content` as paragraphs, or add `whitespace-pre-line`). It
fixes the run-in heading and the run-together paragraphs of 12,079 passages, and Canon Law's
`§` paragraphs. A partial heuristic is not recommended in the meantime: it would style some
collections and not others until the publish, which is the inconsistency this work is meant
to end.

The three leftovers (trailing headings, title-only City of God pieces, Summa question
titles) belong in the same build work, and leftover 4 waits for Carter.

## 4. Mock-ups

Static HTML with the real tokens from `apps/web/src/app/globals.css`, both themes, phone
(390px) and laptop widths. It shows the three examples as card before and after, the GS 79
reader before and after, the hidden repeat, one example per collection with headings
(Catechism stack and epigraph, Trent, Laudato Si', Familiaris Consortio, Dies Domini, City
of God, Monologium, and the Summa leftover), and the specification table. Screenshots:
`docs/screenshots/2026-11-22-passage-headings/`. The mock-up uses Gelasio, which matches
Georgia's metrics, where Georgia is not installed.

## 5. Questions for Carter

1. Anselm's chapter titles (leftover 4): Anselm's own, so they stay and take level 3, or the
   translator's, so they move into labels?
2. Should the reader hide a level-1 heading that repeats its chapter heading (proposed), or
   keep it as a small eyebrow?
3. Should epigraphs be styled (proposed), or left as body text until a later item?

## Appendix: reproducing the survey

1. Read the passages in a read-only transaction, without sourcing the `.env` (the script
   reads `DATABASE_URL` from the file itself):
   `SELECT c.id, d.collection, d.title, c.reference, c.anchor, c.chapter_label, c.content
   FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.retired_at IS NULL AND
   d.retired_at IS NULL AND coalesce(c.searchable, true)`.
2. Split `content` on blank lines and classify each paragraph as described under Method. The
   scratch scripts were not committed. The filters are the table under "False positives".
