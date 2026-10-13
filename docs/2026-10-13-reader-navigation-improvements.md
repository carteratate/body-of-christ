# Reader navigation improvements (beyond the contents trees)

Written 13 Oct 2026 after a review of the reader for the Catechism and the Summa. The
contents trees for those two works are tracked as GitHub issues (see "Contents trees"
below). This file holds everything else the review found, so it can be split into issues
when each item is picked up.

The Bible reader was out of scope. Its book and chapter grid works.

## Why

People open the Catechism and the Summa mostly to reach a known place: "CCC 1471",
"I-II q. 90 a. 1", "the article on Penance". The sites they compare us with treat the
text's own structure as the way in:

- vatican.va shows the Catechism under Part, Section, Chapter and Article, with paragraph
  numbers and footnotes. Catholic Crossreference and the Catechism apps add lookup by
  paragraph number and linked footnotes.
- New Advent lists the Summa by Part and Question, shows a question's prologue and all its
  articles on one page, and starts each paragraph with a bold "Objection 1", "On the
  contrary", "I answer that" or "Reply to Objection 1". aquinas.cc adds the Latin and a
  citation for every part of an article.

Our reader today:

- Catechism contents are 29 buckets named "CCC §§0–99".
- Summa contents are a flat list of 3,120 articles shown 30 at a time. 39 entries begin
  "Question 1 -" and none says which Part it belongs to.
- Inside a chapter every passage is a plain `<p>`.

The reader's plumbing is good and should stay: opening at a search result's anchor,
Back to the right page, saved reading position, prefetching the next chapter.

## Contents trees

Tracked in GitHub. The parent issue is "Reader contents trees for the Catechism and the
Summa", with child issues for:

1. the contents-tree data contract, storage and `/toc` field,
2. the Catechism adapter emitting its tree (extends [1.6], #168),
3. the Summa adapter emitting its tree (extends [1.7], #169),
4. the `ContentsTree` web component and the overview page,
5. the contents panel inside the reader.

The term is "contents tree" on purpose. "Reader outline" already names the flat chapter
list from migration 0037 (`document_chapters`).

## Other improvements

Ordered by value. Each item says whether it can ship before the corpus republish (P4) or
has to wait for the trees or for 1.6 and 1.7.

### 1. A "Go to" box that reads citations

Ships before P4 for the Catechism. The Summa half waits for 1.7.

One input on the overview page and in the reader header. It accepts:

- Catechism: `1471`, `CCC 1471`, `ccc 1471`, `§1471`.
- Summa: `I q.2 a.3`, `I-II 90.1`, `ST II-II q.64 a.6`, `II-II, q. 64, a. 6`, `III 1.1`,
  and the part names spelled out ("First Part", "Prima Secundae").

The parser lives in one pure module per collection, `apps/web/src/lib/citations/`, with
unit tests. It turns input into a structured target. A new route
`GET /v1/documents/{id}/resolve?ref=...` turns the target into a `chapter_key` and an
`anchor`, and the reader opens at that anchor with the passage highlighted.

The Catechism half works on today's data. Every Catechism chunk already stores
`metadata.ccc_paragraphs`, the list of paragraph numbers it holds, so the route only needs
a query that finds the chunk containing the number. Today's overview search matches a
number to its 100-paragraph bucket and opens the bucket at the top, which is the main
complaint this item fixes.

The Summa half needs 1.7's clean part names and article keys. Until then the route
returns 404 for Summa citations and the box says it can't find the article.

### 2. Open at the paragraph, not the chapter

Ships with item 1.

When any route lands on a Catechism paragraph that sits inside a multi-paragraph chunk,
scroll to that chunk and highlight it. After 1.6 adds the inline `§N` markers, scroll to
the marker itself. The reader already accepts `?anchor=`; this item makes the overview
search, the "Go to" box and paragraph links use it.

### 3. Make the structure visible in the text

Part of this ships before P4.

- Headings inside chunk text render as headings. Catechism content contains text like
  `CHAPTER TWO\n\nTHE SACRAMENTS OF HEALING\n\nThrough the sacraments...`. `Passage.tsx`
  puts all of it in one `<p>` with no `white-space` rule, so the breaks collapse and the
  heading runs into the first sentence. The fix splits the content on blank lines and
  renders each block as a paragraph. A short all-caps or "Article N" block renders as a
  heading. Confirm the current behavior in the browser before changing it.
- Summa argument labels ("Objection 1", "On the contrary", "I answer that", "Reply to
  Objection 1") render as a bold run-in label at the start of the paragraph, as every
  printed edition does. Today they are 10px grey superscripts. The Catechism's `§N` label
  moves to the margin on desktop and stays inline on mobile.
- After 1.6, every `§N` marker inside a chunk renders as a margin number, so §1412 is
  visible inside a chunk that starts at §1406.
- After 1.7, entering the first article of a question shows the question header and its
  prologue once, above Article 1.

### 4. Actions on a passage in the reader

Ships before P4.

Each passage gets a small menu (on hover on desktop, on tap on mobile) with:

- Bookmark. This uses the existing `POST /v1/bookmarks`. Today you can only bookmark
  from a search result.
- Copy citation. For example "CCC 1471" or "Summa Theologiae I, q. 2, a. 3, co.", plus
  the text. It uses the passage's `reference`.
- Copy link. The reader URL with `?anchor=`.

Guests get Copy citation and Copy link. Bookmark asks them to sign up, the same as on
search cards.

### 5. A breadcrumb in the header

Waits for the trees.

It replaces the truncated chapter label and the "17 of 29" counter, for example
`Part Two › Section Two › Ch. 2 › Art. 4 · Penance` or `I-II › Treatise on Law › Q. 90 ›
Art. 1`. Each segment opens the contents panel at that branch. On mobile it shrinks to
the last two segments and the whole breadcrumb opens the panel.

### 6. Previous and Next at the end of a chapter, with titles

Ships before P4.

Today Previous and Next appear only in the header. Add them below the last passage of the
last loaded chapter, with the neighbour's short label: "Next: Art. 3 · Whether sacred
doctrine is one science?". Add keyboard shortcuts, `[` and `]` for previous and next
chapter, ignored while focus is in an input.

### 7. Jumps inside a Summa article

Waits for 1.7. Reply links wait for the stitching follow-up that reads `reply_targets`.

A row of chips under each article heading: Objections, On the contrary, I answer that,
Replies. Each scrolls to the first passage of that part. Once replies carry
`reply_targets`, "Reply to Objection 2" links back to Objection 2 and the objection links
forward to its reply.

The contents tree stops at the article on purpose. Putting the four argument parts into it
would add about 12,000 nodes for something these chips do better.

### 8. Search this work

Ships before P4.

A search limited to the open document, using the existing `search_vector` full-text index,
not the RAG pipeline. Results show as a list of places (chapter label plus a snippet), and
choosing one opens the reader at its anchor. It also covers Ctrl-F, which today only finds
text in chapters already loaded.

New route `GET /v1/documents/{id}/search?q=`, with its own per-user rate limit. This lookup
costs no LLM call, so it doesn't count against the search quota.

### 9. A smaller header on mobile

Ships before P4. Do it with the contents panel issue if they land together.

On mobile the header is three stacked rows (status, title and buttons, Previous and
Next). Collapse it to one row: Back, the breadcrumb or title (it opens the contents
panel), and settings. Previous and Next move to the end of the chapter (item 6). Hide the
header when scrolling down and show it when scrolling up.

### 10. Catechism footnotes and cross-references

A data project. Not before P4.

The CCC's footnotes cite Scripture, councils and Fathers, and its margin cross-references
link paragraphs to each other. Both are much of the reason people read it online. Check
what `sources/catechism/ccc.json` carries before scoping this. If it lacks them, this
needs a source decision and belongs in the corpus plan.

## Other collections that should get a tree

The contents-tree contract is generic (any depth, any node kind), so other collections can
adopt it by having their adapter emit nodes. No web work is needed per collection.

- **Canon law. Yes, next after these two.** 1,747 canons in 233 flat chapters labelled
  like "Book I: General Norms — Title I". The Code's real structure is Book, Part,
  Section, Title, Chapter, Article. People look canons up by number, so it also wants the
  "Go to" box (`c. 1055`, `can. 1055 §2`). Do it with or after [1.5a] (#157).
- **Church Fathers and medieval. Yes, two levels, for the long works.** City of God has
  685 chapters labelled "Book I · Chapter 1", and the Imitation of Christ is labelled
  "Book · Chapter" too. A Book → Chapter tree helps any work with more than about 40
  chapters. The ThML sources mark books as `div` levels, so the adapter emits the tree
  from the source, not from label strings. Wait for the Fathers adapter items (1.8 to
  1.10).
- **Encyclicals, apostolic exhortations, papal documents. Not needed now.** Most have
  5 to 40 headings, and the flat list is fine at that size. The largest (Vita Consecrata,
  112) has sub-sections and could use two levels later. What these documents want more is
  lookup by paragraph number ("Laudato Si' 49"), which is item 1 applied to them.
- **Councils. Later.** Most have fewer than 10 chapters today. Trent (sessions, then
  decrees and canons) and Vatican II (16 documents) would benefit once the council
  re-sourcing in 1.2 settles their structure.
- **Bible. No.** The book and chapter grid already is the right tree.
