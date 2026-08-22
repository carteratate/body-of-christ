"""Attach the passage that makes a Summa result intelligible.

A Summa article is a formal disputation, and `ingest/summa.py` splits it into one chunk
per move. Retrieval returns a single move, which creates TWO different problems:

    kind                  whose voice        misattributes alone?  hard to follow alone?
    Objection N           an opponent's      YES                   yes
    On the contrary       quoted authority   no                    somewhat
    I answer that         Aquinas            no                    no
    Reply to Objection N  Aquinas            no                    YES

An **objection** states a position Aquinas demolishes. Shown alone it attributes to him
the opposite of what he teaches — the failure this line of work started from (the Arian
argument against Christ's eternity, and a passage concluding "one may, without sin, kill
an innocent person", both retrievable and both attributed to him). What it lacks is his
ANSWER.

A **reply** is Aquinas's own voice, correctly attributed, so nothing is misrepresented.
But it rebuts one specific objection and begins mid-thought — "The Philosopher is
speaking of those who..." means nothing until you know what the Philosopher said. What
it lacks is the OBJECTION it answers.

Each role is therefore completed by a different passage. An earlier design attached the
determination to both, applying one remedy to two different ailments: of the 90 live
Summa results that need anything at all, 86 are replies, so the dominant card read as
Aquinas answering himself.

For scale, across all 212 persisted Summa retrievals: 112 determinations, 86 replies, 10
sed contra, 4 objections. The modal Summa result needs nothing, and the misattribution
case this work began from is the rarest of the four.

A sed contra is excluded from both: it is a quoted authority pointing AT the
determination, so it neither misattributes nor dangles.

Ordering on the card follows the argument, not the match. An objection is shown first
with its answer beneath; a reply is shown BENEATH the objection it answers, because that
is the only order in which it reads. The matched passage is always present and always
identified — never replaced.

THIS STEP NEVER ADDS OR REMOVES A RESULT.
`assemble` is a pure order-preserving map: one output card per input chunk, always, in
the input's order. An earlier version tried to be cleverer — when a determination ranked
in its own right AND an objection from the same article also ranked, it collapsed them
into one card. That deleted matched results: `[Objection 1, I answer that, Objection 2]`
came back as ONE card, silently dropping a passage the reranker had scored, which the
user could then neither bookmark nor restore, below the quota they asked for. It also
made the step non-idempotent, so replaying it over saved rows produced a different list
than the live search had shown.

The cost of not collapsing is that a determination which ranked separately appears twice
on the page: once as its own card, once inside the objection's attachment. That is a
cosmetic repetition. Deleting a scored result is a functional loss. The trade is not
close, and repetition is the only behaviour that survives being run twice.

For the same reason a reply is attached to its objection even when that objection also
ranked separately. Alone, a reply is unreadable — the whole reason this exists — and the
objection may be many cards away.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace

from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

# What the attached passage IS, relative to the matched one. The API exposes this so a
# renderer never has to infer placement from a label: `answered_by` renders below the
# match, `answers` above it.
#
# These strings are the wire contract, mirrored as a TS union in apps/web/src/lib/api.ts
# and as a Literal in app/models/search.py. Changing either value alone flips every card
# to the wrong side of its attachment without failing a type check.
ANSWERED_BY = "answered_by"
ANSWERS = "answers"

_DETERMINATION = "I answer that"
_SUMMA = "summa"

# How this translation opens each subsequent objection in a series. It is the corpus's
# own signal that a passage begins a NEW argument rather than continuing the previous one.
_NEW_ARGUMENT = "Further,"

_OBJECTION_RE = re.compile(r"^Objection (\d+)$")
_REPLY_RE = re.compile(r"^Reply to Objection (\d+)$")


@dataclass(frozen=True)
class Stitched:
    """A result card plus the passage that completes it.

    `chunk` keeps the matched passage's identity — id, score, reference — so
    persistence, bookmarking and feedback all continue to address what the user actually
    matched. `parts` is presentation only.
    """

    chunk: RankedChunk
    parts: list[RankedChunk]
    relation: str | None = None

    @property
    def is_stitched(self) -> bool:
        return bool(self.parts)


def _objection_number(chunk: RankedChunk) -> str | None:
    if chunk.collection != _SUMMA or not chunk.unit_label:
        return None
    match = _OBJECTION_RE.match(chunk.unit_label)
    return match.group(1) if match else None


def _reply_number(chunk: RankedChunk) -> str | None:
    if chunk.collection != _SUMMA or not chunk.unit_label:
        return None
    match = _REPLY_RE.match(chunk.unit_label)
    return match.group(1) if match else None


def is_determination(chunk: RankedChunk) -> bool:
    return (
        chunk.collection == _SUMMA
        and bool(chunk.unit_label)
        and chunk.unit_label.startswith(_DETERMINATION)
    )


def attachment_relation(chunk: RankedChunk) -> str | None:
    """What this passage needs attached, or None if it stands on its own.

    Restricted to the Summa: `unit_label` elsewhere is a locator ("Can. 33", "§17"),
    naming a passage's position rather than its role in an argument, and no other
    collection in the corpus is a staged debate.
    """
    if _objection_number(chunk) is not None:
        return ANSWERED_BY
    if _reply_number(chunk) is not None:
        return ANSWERS
    return None


def articles_needed(chunks: list[RankedChunk]) -> set[str]:
    """Chapter keys to fetch: those holding a result that needs something attached.

    A key is fetched WHOLE — see `fetch_context` — because the passage that completes a
    result is found by scanning its neighbours, and because a determination is often
    split across several chunks that only make sense together.
    """
    return {
        chunk.chapter_key
        for chunk in chunks
        if attachment_relation(chunk) is not None and chunk.chapter_key
    }


# WHY PROXIMITY RATHER THAN ARTICLE SEGMENTATION
#
# An earlier version tried to split a chapter_key into articles and then look inside the
# matched passage's article. That rested on "an article states each move once, so a
# repeated unit_label begins the next article" — which the corpus does not honour. Of
# 3,120 Summa keys, 3,072 follow the textbook shape (objections, sed contra,
# determination, replies) and 48 do not: 4 split the sed contra across chunks, 16 have no
# determination at all, and others strand an objection among the replies. Only 3 keys
# genuinely hold two disputations. The rule mistook a split sed contra for a new article
# and cut 46 keys in half, stranding 102 passages with nothing attached — including the
# objections the feature exists to protect.
#
# Scanning neighbours needs no such premise. It reads the disputation the way it is laid
# out: the answer to an objection is the determination that comes next, and the objection
# a reply answers is the last one bearing that number before it. Both scans stop at the
# shape's own landmarks (below), and where the text is too damaged to answer they return
# nothing — the honest pre-stitching behaviour rather than another article's words.
#
# The stop conditions are sufficient for the corpus as it stands, not unconditionally.
# `_determination_after` is stopped only by a reply, so an article with objections but
# NEITHER a determination nor any reply, immediately followed by another disputation,
# would reach into the next one. No such key exists (verified over all 3,120), and the
# 3 genuine two-disputation keys all carry full reply runs. If ingest ever produces
# `O…C` followed by `O…C…A`, this needs a second landmark.


def _determination_after(passages: list[RankedChunk], index: int) -> list[RankedChunk]:
    """The determination answering the objection at `index`, in reading order.

    Scans forward and stops at the first reply: replies come after the determination, so
    reaching one means this objection's own article never had a determination and the
    scan is about to enter the next. 16 keys have no determination at all, and those
    correctly attach nothing.

    Returns the whole contiguous run, because 109 articles split the determination across
    chunks (averaging 4,770 chars) and half an answer presented as the answer is its own
    misrepresentation.
    """
    for position in range(index + 1, len(passages)):
        passage = passages[position]
        if _reply_number(passage) is not None:
            return []
        if is_determination(passage):
            run = []
            while position < len(passages) and is_determination(passages[position]):
                run.append(passages[position])
                position += 1
            return run
    return []


def _objection_before(passages: list[RankedChunk], index: int,
                      number: str) -> list[RankedChunk]:
    """The objection numbered `number` that the reply at `index` answers.

    Scans backward for that exact number and stops at a reply encountered AFTER passing a
    determination: within one article every reply follows the determination, so a reply
    on the far side of one belongs to the article before this one.

    That landmark is the determination and not the objections deliberately. Backwards
    from a reply the order is determination, sed contra, objections — so stopping at "a
    reply seen after any objection" would fire inside the 2 keys that strand an objection
    among the replies, cutting their later replies off from objections that are genuinely
    theirs.

    The cost is that in the 16 keys with no determination at all the guard never arms,
    and a reply whose number is absent from its own article can scan back into the
    previous one. No such key currently holds a second disputation, so nothing crosses
    today — the same conditional soundness `_determination_after` documents, on the
    mirror-image trigger.

    Returns the contiguous run of that number, since an objection can be split too.
    """
    seen_determination = False
    for position in range(index - 1, -1, -1):
        passage = passages[position]
        if is_determination(passage):
            seen_determination = True
        elif seen_determination and _reply_number(passage) is not None:
            return []
        elif _objection_number(passage) == number:
            run = []
            while position >= 0 and _objection_number(passages[position]) == number:
                run.insert(0, passages[position])
                position -= 1
            return _without_mislabelled_neighbours(run)
    return []


def _without_mislabelled_neighbours(run: list[RankedChunk]) -> list[RankedChunk]:
    """Trim a same-numbered run at the point it stops being one objection.

    The run exists because a passage can be split across chunks, as 109 determinations
    are. For objections it never is: of the 4 adjacent same-numbered pairs in the corpus,
    all 4 have a second member opening "Further," and none begins mid-sentence. Those are
    ingest mislabels — a later objection stamped with an earlier one's number — so
    returning the whole run would render two different arguments under a single
    "Objection N — answered below" heading, presenting both as the one thing the reply
    answers.

    Numbering runs top-down, so the earliest member is the one that carries the number.
    Anything after it that opens a new argument is dropped; a genuine continuation, which
    would not, is still returned whole.
    """
    kept = run[:1]
    for part in run[1:]:
        if (part.content or "").lstrip().startswith(_NEW_ARGUMENT):
            break
        kept.append(part)
    return kept


def assemble(chunks: list[RankedChunk],
             articles: dict[tuple[str, str], list[RankedChunk]]) -> list[Stitched]:
    """One card per input chunk, in input order, each with what completes it.

    `articles` is `fetch_context.articles`: (document_id, chapter_key) -> every passage
    under that key, position-ordered. Keyed by document too, because `chapter_key` is
    unique only within a document and migrations 0008/0014 exist to let a second
    translation of the Summa be loaded — at which point two documents' passages would
    otherwise merge into one bucket with overlapping positions.

    Never adds, drops, reorders or merges a result. See the module docstring for why
    that is a rule rather than an accident.
    """
    out: list[Stitched] = []
    unplaceable = unmatched = 0
    for chunk in chunks:
        relation = attachment_relation(chunk)
        parts: list[RankedChunk] = []

        if relation is not None and chunk.chapter_key:
            passages = articles.get((chunk.document_id, chunk.chapter_key), [])
            index = next((i for i, p in enumerate(passages)
                          if p.chunk_id == chunk.chunk_id), None)
            if index is None:
                # Three different causes, and only two are worth a log line.
                #
                # The article was fetched and does not contain the passage that matched
                # it: the stores disagree about chunk ids — a re-chunk without a
                # reconcile, the failure already recorded against this corpus.
                if passages:
                    unplaceable += 1
                # The lookup returned articles, but none under this result's
                # (document_id, chapter_key). `document_id` on the live path comes
                # straight from the Qdrant payload and is never reconciled against
                # Postgres, so a divergence there silently empties EVERY bucket: no
                # attachment anywhere, and `fetch_context`'s own missing-key counter
                # cannot see it, because the key did come back — filed under a different
                # document.
                elif articles:
                    unmatched += 1
                # Otherwise the lookup degraded entirely and returned {}, which
                # `fetch_context` has already reported through `record_recovery`.
                # Counting it again here would point an operator at drift that did not
                # happen.
            elif relation == ANSWERED_BY:
                parts = _determination_after(passages, index)
            else:
                parts = _objection_before(passages, index, _reply_number(chunk))

        # 21 Summa chunks hold an empty passage, 17 of them objections a reply points
        # back to. An empty attachment renders as a blank block under a header naming a
        # voice, and tells the explanation model to read a passage that is not there.
        parts = [part for part in parts if part.content and part.content.strip()]

        out.append(Stitched(chunk=chunk, parts=parts,
                            relation=relation if parts else None))

    if unplaceable:
        logger.warning(
            "stitch: %d result(s) not found in the article fetched for them; "
            "chunk ids may have drifted from the search index", unplaceable,
        )
    if unmatched:
        logger.warning(
            "stitch: %d result(s) had no article under their (document_id, chapter_key) "
            "though other articles were returned; the search index and the database may "
            "disagree about document_id", unmatched,
        )
    return out


def parts_text(stitched: Stitched) -> str:
    """The attached parts joined in document order, or "" if there are none."""
    return "\n\n".join(part.content for part in stitched.parts)


# The boundary markers `with_stitched_content` inserts. `explain._EXPLAIN_SYSTEM` tells
# the model what each one means, so the two must agree exactly; `test_stitch.py` asserts
# every marker below appears verbatim in that prompt.
ANSWERS_MARKER = ", which the passage below answers:"
REPLY_MARKER = " — Aquinas's reply:"
ANSWERED_BY_MARKER = " — Aquinas answers:"


def with_stitched_content(stitched: Stitched) -> RankedChunk:
    """The matched chunk with its attached passage inlined, for the explanation input.

    Ordered as the card is: an objection above its answer, a reply below the objection it
    answers. The model must see what the user sees, or the prose it writes — persisted to
    `retrievals.explanation` and re-served forever — describes something else.

    This deliberately puts framing text into the passage body, which `explain.py`
    otherwise forbids for the role label, on the grounds that a model told to "be
    faithful to what the passage says" must not read a header as source text. The
    boundary marker is the exception, and `_EXPLAIN_SYSTEM` names it explicitly so the
    model knows which side of it carries the header's role.
    """
    if not stitched.is_stitched:
        return stitched.chunk

    matched = stitched.chunk.content
    attached = parts_text(stitched)

    if stitched.relation == ANSWERS:
        # The objection comes first: the reply's own opening sentence refers back to it,
        # so the reverse order is unreadable.
        body = (
            f"[{stitched.parts[0].unit_label}{ANSWERS_MARKER}]\n\n"
            f"{attached}\n\n"
            f"[{stitched.chunk.unit_label}{REPLY_MARKER}]\n\n{matched}"
        )
    else:
        body = (
            f"{matched}\n\n"
            f"[{stitched.chunk.unit_label}{ANSWERED_BY_MARKER}]\n\n{attached}"
        )
    return replace(stitched.chunk, content=body)
