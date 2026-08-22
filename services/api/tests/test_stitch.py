"""Tests for attaching the passage that completes a Summa result.

Two roles, two different ailments, two different remedies:

  Objection N          misattributes Aquinas when alone  -> attach his determination
  Reply to Objection N reads mid-thought when alone      -> attach the objection it answers

An earlier design attached the determination to both, which applied one remedy to two
ailments. 82 of the 86 live Summa results that need anything are replies, so the
dominant card read as Aquinas answering himself. Much of what follows pins that the two
roles stay distinct.

The other thing pinned here is that this step is a PURE MAP. An earlier version merged
a ranked determination into an objection's card, which deleted scored results and made
the step non-idempotent, so a restored search showed a different list than the live one.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.steps import fetch_context, stitch
from app.rag.steps.types import RankedChunk


def _chunk(chunk_id="c1", unit_label="Objection 1", chapter_key="summa/q1/a1",
           collection="summa", content="It would seem that...", score=0.9,
           position=1):
    return RankedChunk(
        chunk_id=chunk_id, content=content, reference="ST I q1 a1",
        collection=collection, document_id="d1", document_title="Summa Theologiae",
        author="Thomas Aquinas", reranker_score=score, unit_label=unit_label,
        chapter_key=chapter_key, position=position,
    )


def _article(chapter_key="summa/q1/a1", start=0, objections=2, determination_parts=1,
             replies=2, label_suffix=""):
    """One complete article's passages in document order, as fetch_context returns them.

    Shape follows the disputation: objections, sed contra, determination, replies.
    """
    out, position = [], start
    for number in range(1, objections + 1):
        out.append(_chunk(f"o{number}{label_suffix}", f"Objection {number}", chapter_key,
                          content=f"OBJECTION {number}{label_suffix}", position=position))
        position += 1
    out.append(_chunk(f"sc{label_suffix}", "On the contrary", chapter_key,
                      content=f"SED CONTRA{label_suffix}", position=position))
    position += 1
    for part in range(determination_parts):
        out.append(_chunk(f"d{part}{label_suffix}", "I answer that", chapter_key,
                          content=f"DETERMINATION {part}{label_suffix}", position=position))
        position += 1
    for number in range(1, replies + 1):
        out.append(_chunk(f"r{number}{label_suffix}", f"Reply to Objection {number}",
                          chapter_key, content=f"REPLY {number}{label_suffix}",
                          position=position))
        position += 1
    return out


def replace_position(chunk, position):
    from dataclasses import replace
    return replace(chunk, position=position)


def replace_label(chunk, unit_label):
    from dataclasses import replace
    return replace(chunk, unit_label=unit_label)


def replace_content(chunk, content):
    from dataclasses import replace
    return replace(chunk, content=content)


# ---------------------------------------------------------------------------
# Which passage each role needs
# ---------------------------------------------------------------------------

def test_an_objection_needs_the_determination_below_it():
    assert stitch.attachment_relation(_chunk(unit_label="Objection 3")) == stitch.ANSWERED_BY


def test_a_reply_needs_its_objection_above_it():
    """A reply is Aquinas's own voice — nothing is misattributed. What it lacks is the
    argument it answers, without which its first sentence refers to nothing."""
    assert stitch.attachment_relation(
        _chunk(unit_label="Reply to Objection 2")) == stitch.ANSWERS


def test_the_determination_needs_nothing():
    assert stitch.attachment_relation(_chunk(unit_label="I answer that")) is None


def test_a_sed_contra_needs_nothing():
    """A quoted authority pointing AT the determination: it neither misattributes nor
    dangles."""
    assert stitch.attachment_relation(_chunk(unit_label="On the contrary")) is None


def test_non_summa_passages_are_never_stitched():
    """unit_label elsewhere is a locator ("Can. 33"), naming position not argument role."""
    assert stitch.attachment_relation(
        _chunk(unit_label="Can. 33", collection="canon-law")) is None
    assert stitch.attachment_relation(
        _chunk(unit_label="Objection 1", collection="councils")) is None
    assert stitch.attachment_relation(_chunk(unit_label=None)) is None


def test_an_unknown_relation_is_rejected_at_the_api_boundary():
    """The renderer switches on these two values to decide which side of the matched
    passage the attachment goes. A third value would reach a client that cannot place
    it, so it must fail here rather than render somewhere arbitrary."""
    import pydantic

    from app.models.search import AttachedContext

    with pytest.raises(pydantic.ValidationError):
        AttachedContext(relation="sideways", parts=[])


def test_the_relation_values_are_the_wire_contract():
    """These exact strings are mirrored as a TS union in apps/web/src/lib/api.ts and as
    a Literal in app/models/search.py, and the renderer switches on them to decide
    whether the attachment goes above or below the match. Swapping the two values type
    checks everywhere and puts every attachment on the wrong side of its passage."""
    assert stitch.ANSWERED_BY == "answered_by"
    assert stitch.ANSWERS == "answers"


# ---------------------------------------------------------------------------
# Finding what completes a result, in a corpus that does not follow its own shape
#
# Of 3,120 Summa keys, 3,072 are the textbook sequence and 48 are not. The shapes below
# are all real: `O`=objection, `C`=sed contra, `A`=determination, `R`=reply.
# ---------------------------------------------------------------------------

def _shaped(pattern, chapter_key="summa/q1/a1", document_id="d1", prefix="a"):
    """An article built from a role pattern, numbering objections and replies in turn."""
    labels, objections, replies = [], 0, 0
    for role in pattern:
        if role == "O":
            objections += 1
            labels.append(f"Objection {objections}")
        elif role == "R":
            replies += 1
            labels.append(f"Reply to Objection {replies}")
        elif role == "C":
            labels.append("On the contrary")
        elif role == "A":
            labels.append("I answer that")
        else:
            labels.append(None)
    return [
        RankedChunk(chunk_id=f"{document_id}-{prefix}{i}",
                    content=f"{label or 'text'} #{prefix}{i}",
                    reference="ST I q1 a1", collection="summa", document_id=document_id,
                    document_title="Summa Theologiae", author="Thomas Aquinas",
                    reranker_score=0.9, unit_label=label, chapter_key=chapter_key,
                    position=i)
        for i, label in enumerate(labels)
    ]


def _attach(passages, index):
    [item] = stitch.assemble([passages[index]], _articles(passages))
    return [p.content for p in item.parts]


def test_a_split_sed_contra_does_not_hide_the_determination():
    """OOOCCARRR — 4 keys chunk the sed contra in two. A rule that read the repeat as a
    new article left every objection AND every reply in these articles unattached: the
    objections on one side of the cut, the determination on the other."""
    passages = _shaped("OOOCCARRR")

    assert _attach(passages, 0) == ["I answer that #a5"]
    assert _attach(passages, 6) == ["Objection 1 #a0"]


def test_a_stray_objection_after_the_sed_contra_still_finds_the_answer():
    """OOOOCOARRRRR exactly — 5 keys; 12 keys strand an objection somewhere between the
    sed contra and the determination."""
    passages = _shaped("OOOOCOARRRRR")

    assert _attach(passages, 5) == ["I answer that #a6"]


def test_a_sed_contra_after_the_determination_changes_nothing():
    """OOOCACRRR — 3 keys."""
    passages = _shaped("OOOCACRRR")

    assert _attach(passages, 0) == ["I answer that #a4"]


def test_a_split_determination_is_attached_whole():
    """109 keys split the answer across chunks. Half an answer presented as the answer
    is its own misrepresentation."""
    passages = _shaped("OOOCAAARRR")

    assert _attach(passages, 0) == [
        "I answer that #a4", "I answer that #a5", "I answer that #a6"]


def test_an_article_with_no_determination_attaches_nothing():
    """OOOCRRR — 16 keys have no determination at all. The scan must stop at the replies
    rather than run on into whatever follows."""
    passages = _shaped("OOOCRRR")

    assert _attach(passages, 0) == []


def test_an_objection_never_takes_the_next_articles_determination():
    """The 3 keys that really do hold two disputations. Reaching a reply means this
    article had no determination and the scan is about to cross into the next one."""
    passages = _shaped("OOOCRRR") + _shaped("OOOCARRR", prefix="b")
    passages = [replace_position(p, i) for i, p in enumerate(passages)]

    assert _attach(passages, 0) == []


def test_each_disputation_gets_its_own_determination():
    passages = [replace_position(p, i) for i, p in
                enumerate(_shaped("OOOCARRR") + _shaped("OOOCARRR", prefix="b"))]

    assert _attach(passages, 0) == ["I answer that #a4"]
    assert _attach(passages, 8) == ["I answer that #b4"]   # second article's own copy


def test_a_reply_never_takes_the_previous_articles_objection():
    """A reply on the far side of a determination belongs to the article before."""
    passages = [replace_position(p, i) for i, p in
                enumerate(_shaped("OOOCARRR") + _shaped("CARR", prefix="b"))]
    reply = next(i for i, p in enumerate(passages)
                 if i > 8 and p.unit_label == "Reply to Objection 1")

    assert _attach(passages, reply) == []


def test_each_disputation_gets_its_own_objection():
    passages = [replace_position(p, i) for i, p in
                enumerate(_shaped("OOOCARRR") + _shaped("OOOCARRR", prefix="b"))]

    assert _attach(passages, 5) == ["Objection 1 #a0"]
    assert _attach(passages, 13) == ["Objection 1 #b0"]    # second article's own copy


def test_a_reply_matches_its_objection_number_exactly():
    """Objection numbers reach 16, and 12 keys carry a two-digit one. Matching by prefix
    would hand `Reply to Objection 1` every objection from 10 to 16 — seven unrelated
    positions rendered above Aquinas's reply and fed to the explanation model."""
    passages = _shaped("O" * 16 + "CA" + "R" * 16)
    reply_1 = next(i for i, p in enumerate(passages)
                   if p.unit_label == "Reply to Objection 1")

    [item] = stitch.assemble([passages[reply_1]], _articles(passages))

    assert [p.unit_label for p in item.parts] == ["Objection 1"]


def test_a_two_digit_reply_finds_its_own_objection():
    passages = _shaped("O" * 16 + "CA" + "R" * 16)
    reply_13 = next(i for i, p in enumerate(passages)
                    if p.unit_label == "Reply to Objection 13")

    [item] = stitch.assemble([passages[reply_13]], _articles(passages))

    assert [p.unit_label for p in item.parts] == ["Objection 13"]


def test_a_split_objection_is_attached_whole_to_its_reply():
    """10 keys carry a duplicate `Objection N` label."""
    passages = _shaped("OOCARR")
    passages[1] = replace_label(passages[1], "Objection 1")

    [item] = stitch.assemble([passages[4]], _articles(passages))
    assert [p.position for p in item.parts] == [0, 1]


def test_an_empty_passage_is_never_attached():
    """21 Summa chunks hold empty content, 17 of them objections a reply points back to.
    An empty attachment renders a blank block under a header naming a voice, and tells
    the explanation model to read a passage that is not there."""
    passages = _shaped("OOCARR")
    passages[0] = replace_content(passages[0], "   ")

    [item] = stitch.assemble([passages[4]], _articles(passages))
    assert item.parts == [] and item.relation is None


def test_passages_from_another_document_are_never_reachable():
    """chapter_key is unique only within a document, and migrations 0008/0014 exist so a
    second translation can be loaded. Keyed by chapter_key alone, its passages would
    merge into one bucket with overlapping positions."""
    mine = _shaped("OOOCRRR", document_id="d1")
    theirs = _shaped("OOOCARRR", document_id="d2", prefix="b")

    [item] = stitch.assemble([mine[0]], _articles(mine + theirs))

    assert item.parts == []


# ---------------------------------------------------------------------------
# assemble: a pure order-preserving map
# ---------------------------------------------------------------------------

def _assembled(results, passages):
    return stitch.assemble(results, _articles(passages))


def _articles(passages):
    """Passages bucketed the way fetch_context returns them."""
    out = {}
    for passage in passages:
        out.setdefault((passage.document_id, passage.chapter_key), []).append(passage)
    return out


def test_an_objection_card_puts_the_determination_below_the_match():
    passages = _article()
    [item] = _assembled([passages[0]], passages)

    assert item.relation == stitch.ANSWERED_BY
    assert [p.content for p in item.parts] == ["DETERMINATION 0"]


def test_a_reply_card_puts_its_own_objection_above_the_match():
    """Reply to Objection 2 gets Objection 2, not Objection 1 and not the answer."""
    passages = _article()
    reply = next(p for p in passages if p.unit_label == "Reply to Objection 2")
    [item] = _assembled([reply], passages)

    assert item.relation == stitch.ANSWERS
    assert [p.content for p in item.parts] == ["OBJECTION 2"]


def test_a_split_determination_is_attached_whole_in_reading_order():
    passages = _article(determination_parts=3)
    [item] = _assembled([passages[0]], passages)

    assert [p.content for p in item.parts] == [
        "DETERMINATION 0", "DETERMINATION 1", "DETERMINATION 2"]


def test_every_result_survives_assembly_in_its_original_order():
    """The step must never add, drop or reorder a card. An earlier version merged a
    ranked determination into an objection's card and returned a SHORTER list:
    [Objection 1, I answer that, Objection 2] came back as one card, silently deleting
    a passage the reranker had scored, below the quota the user asked for."""
    passages = _article()
    results = [passages[0], passages[3], passages[1]]   # Obj1, determination, Obj2

    out = _assembled(results, passages)

    assert [item.chunk.chunk_id for item in out] == [p.chunk_id for p in results]


def test_assembly_is_idempotent():
    """Restore replays this over the saved rows. A step that changes the list on the
    second run shows a different search than the one that was persisted."""
    passages = _article()
    results = [passages[0], passages[3], passages[1]]

    once = [item.chunk for item in _assembled(results, passages)]
    twice = [item.chunk for item in _assembled(once, passages)]

    assert [c.chunk_id for c in once] == [c.chunk_id for c in twice]


def test_an_objection_keeps_its_answer_even_when_the_determination_also_ranked():
    """The repetition is deliberate: shown alone the objection attributes to Aquinas the
    opposite of what he teaches, and the determination's own card may be far away."""
    passages = _article()
    out = _assembled([passages[3], passages[0]], passages)   # determination ranks first

    assert out[1].relation == stitch.ANSWERED_BY
    assert [p.content for p in out[1].parts] == ["DETERMINATION 0"]


def test_a_reply_keeps_its_objection_even_when_that_objection_also_ranked():
    """Alone a reply is unreadable, which is the whole reason this exists."""
    passages = _article()
    reply = next(p for p in passages if p.unit_label == "Reply to Objection 1")
    out = _assembled([passages[0], reply], passages)

    assert out[1].relation == stitch.ANSWERS
    assert [p.content for p in out[1].parts] == ["OBJECTION 1"]


def test_a_result_is_attached_to_the_article_it_actually_came_from():
    """Two articles share a chapter_key. Pairing by key alone would glue the second
    article's determination onto the first article's objection and label the pair as
    Aquinas's answer — a fabricated attribution, the failure this feature exists to
    prevent."""
    passages = _article(start=0) + _article(start=100, label_suffix="B")
    second_objection = passages[6]
    assert second_objection.content == "OBJECTION 1B"

    [item] = stitch.assemble([second_objection], _articles(passages))

    assert [p.content for p in item.parts] == ["DETERMINATION 0B"]


def test_a_reply_under_a_shared_key_gets_its_own_articles_objection():
    """10 keys carry a duplicate 'Objection N' label across 16 (key, label) pairs, so
    selecting by number alone is a coin flip between two different articles."""
    passages = _article(start=0) + _article(start=100, label_suffix="B")
    reply = next(p for p in passages if p.content == "REPLY 1B")

    [item] = stitch.assemble([reply], _articles(passages))

    assert [p.content for p in item.parts] == ["OBJECTION 1B"]


def test_a_result_missing_from_its_own_article_is_reported():
    """The article was fetched but does not contain the passage that matched it: the two
    stores disagree about chunk ids. Silent, that is every Summa card quietly losing its
    attachment with nothing to look at."""
    import logging

    passages = _article()
    stranger = _chunk("not-in-this-article", "Objection 1", position=0)

    with patch.object(stitch.logger, "warning") as warned:
        [item] = stitch.assemble([stranger], _articles(passages))

    assert item.parts == []
    warned.assert_called_once()


def test_a_placeable_result_reports_nothing():
    passages = _article()
    with patch.object(stitch.logger, "warning") as warned:
        stitch.assemble([passages[0]], _articles(passages))

    warned.assert_not_called()


def test_a_result_that_cannot_be_placed_is_left_unattached():
    """Attaching nothing is the pre-stitching behaviour. Attaching the wrong article's
    text would be worse than attaching none."""
    passages = _article(start=0)
    orphan = _chunk("far", "Objection 1", position=9999)

    [item] = stitch.assemble([orphan], _articles(passages))

    assert item.parts == [] and item.relation is None


def test_a_result_with_no_position_is_left_unattached():
    passages = _article(start=0)
    [item] = stitch.assemble([_chunk("np", "Objection 1", position=None)],
                             _articles(passages))

    assert item.parts == []


def test_an_article_with_no_determination_degrades_to_a_bare_objection():
    """16 live articles have objections but no determination chunk."""
    passages = [p for p in _article() if p.unit_label != "I answer that"]
    [item] = _assembled([passages[0]], passages)

    assert item.parts == [] and item.relation is None


def test_a_reply_with_no_matching_objection_degrades_to_a_bare_reply():
    passages = [p for p in _article() if p.unit_label != "Objection 2"]
    reply = next(p for p in passages if p.unit_label == "Reply to Objection 2")
    [item] = _assembled([reply], passages)

    assert item.parts == [] and item.relation is None


def test_non_summa_results_pass_through_untouched():
    passages = _article()
    verse = _chunk("v1", None, chapter_key="john/1", collection="bible", position=1)
    out = stitch.assemble([verse], _articles(passages))

    assert out[0].chunk is verse and out[0].parts == []


def test_the_sed_contra_is_never_stitched_even_inside_a_fetched_article():
    passages = _article()
    [item] = _assembled([passages[2]], passages)

    assert item.relation is None and item.parts == []


# ---------------------------------------------------------------------------
# The matched passage keeps its identity
# ---------------------------------------------------------------------------

def test_the_card_keeps_the_matched_passage_identity():
    """Persistence, bookmarking and feedback all address the matched chunk, so the
    attachment must not overwrite its id, score or reference."""
    passages = _article()
    [item] = _assembled([passages[0]], passages)

    assert item.chunk.chunk_id == "o1"
    assert item.chunk.reranker_score == 0.9
    assert item.chunk.reference == "ST I q1 a1"


def test_the_matched_chunk_is_never_mutated():
    passages = _article()
    matched = passages[0]
    [item] = _assembled([matched], passages)

    stitch.with_stitched_content(item)

    assert matched.content == "OBJECTION 1"


# ---------------------------------------------------------------------------
# The text handed to the explanation model
# ---------------------------------------------------------------------------

def test_an_objection_is_explained_with_the_answer_below_it():
    passages = _article()
    [item] = _assembled([passages[0]], passages)

    body = stitch.with_stitched_content(item).content

    assert body.index("OBJECTION 1") < body.index("DETERMINATION 0")
    assert f"[Objection 1{stitch.ANSWERED_BY_MARKER}]" in body


def test_a_reply_is_explained_with_the_objection_above_it():
    """A reply opens mid-thought; the reverse order is unreadable, and the model's prose
    is persisted to retrievals.explanation and re-served forever."""
    passages = _article()
    reply = next(p for p in passages if p.unit_label == "Reply to Objection 1")
    [item] = _assembled([reply], passages)

    body = stitch.with_stitched_content(item).content

    assert body.index("OBJECTION 1") < body.index("REPLY 1")
    assert f"[Objection 1{stitch.ANSWERS_MARKER}]" in body
    assert f"[Reply to Objection 1{stitch.REPLY_MARKER}]" in body


def test_a_split_answer_reaches_the_model_in_reading_order():
    """assemble's `parts` list is not what the model sees — `parts_text` is. 109 articles
    split the determination, and a reversed join hands the model the second half of
    Aquinas's answer before the first, in prose persisted to retrievals.explanation and
    re-served forever.

    No persisted Summa retrieval attaches more than one part today; this guards the 476
    corpus passages that would."""
    passages = _shaped("OOOCAAARRR")
    [item] = stitch.assemble([passages[0]], _articles(passages))

    body = stitch.with_stitched_content(item).content

    assert body.index("#a4") < body.index("#a5") < body.index("#a6")


def test_an_unstitched_chunk_passes_through_unchanged():
    chunk = _chunk(unit_label="I answer that", content="the answer")
    item = stitch.Stitched(chunk=chunk, parts=[])

    assert stitch.with_stitched_content(item) is chunk


@pytest.mark.parametrize("marker", [
    stitch.ANSWERED_BY_MARKER, stitch.ANSWERS_MARKER, stitch.REPLY_MARKER])
def test_every_boundary_marker_is_described_to_the_explanation_model(marker):
    """The prompt tells the model which side of each boundary carries which voice. A
    marker the prompt does not name is a boundary the model was told to look for
    somewhere it never appears — and the resulting prose is persisted forever."""
    from app.rag.steps.explain import _EXPLAIN_SYSTEM

    assert marker in _EXPLAIN_SYSTEM


# ---------------------------------------------------------------------------
# Which articles get fetched
# ---------------------------------------------------------------------------

def test_only_articles_holding_a_needy_result_are_fetched():
    chunks = [_chunk("o1", "Objection 1", "summa/q1/a1"),
              _chunk("r1", "Reply to Objection 1", "summa/q2/a2"),
              _chunk("d1", "I answer that", "summa/q3/a3"),
              _chunk("sc", "On the contrary", "summa/q4/a4"),
              _chunk("v1", None, "john/1", collection="bible")]

    assert stitch.articles_needed(chunks) == {"summa/q1/a1", "summa/q2/a2"}


def test_nothing_is_fetched_for_a_search_with_no_summa_debate():
    assert stitch.articles_needed([_chunk("v1", None, "john/1", collection="bible")]) == set()


# ---------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------

def _row(chunk_id="x", unit_label="I answer that", chapter_key="summa/q1/a1",
         content="text", position=3):
    return {"chunk_id": chunk_id, "content": content, "reference": "ST I q1 a1",
            "anchor": "a/1", "chapter_key": chapter_key, "position": position,
            "unit_label": unit_label, "document_id": "d1",
            "document_title": "Summa Theologiae", "author": "Thomas Aquinas",
            "collection": "summa"}


def test_the_lookup_returns_whole_articles_grouped_by_key():
    pool = AsyncMock()
    pool.fetch.return_value = [
        _row("a", "Objection 1", "summa/q1/a1", position=1),
        _row("b", "I answer that", "summa/q1/a1", position=2),
        _row("c", "Objection 1", "summa/q2/a2", position=1),
    ]
    with patch("app.rag.steps.fetch_context.get_pool", return_value=pool):
        out = asyncio.run(fetch_context.articles({"summa/q1/a1", "summa/q2/a2"}))

    assert [c.chunk_id for c in out[("d1", "summa/q1/a1")]] == ["a", "b"]
    assert [c.chunk_id for c in out[("d1", "summa/q2/a2")]] == ["c"]


def test_the_lookup_fetches_every_role_not_just_the_determination():
    """Replies need objections and objections need determinations, and splitting a
    shared key into articles needs the sed contra to see the boundary. A query filtered
    to one label cannot serve any of that."""
    assert "unit_label LIKE" not in fetch_context._SQL
    assert "unit_label =" not in fetch_context._SQL


def test_the_lookup_orders_by_position():
    """Position ordering is what splits a shared key back into articles and what keeps a
    split determination in reading order rather than presenting its halves backwards."""
    assert "ORDER BY c.document_id, c.chapter_key, c.position" in fetch_context._SQL


def test_the_lookup_is_restricted_to_the_summa():
    assert "d.collection = 'summa'" in fetch_context._SQL


def test_fetched_parts_are_marked_stitched_not_scored():
    """Nothing downstream may mistake a fetched passage for a measured relevance
    judgement."""
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    with patch("app.rag.steps.fetch_context.get_pool", return_value=pool):
        out = asyncio.run(fetch_context.articles({"summa/q1/a1"}))

    part = out[("d1", "summa/q1/a1")][0]
    assert part.score_source == "stitched" and part.reranker_score == 0.0


def test_the_lookup_does_not_query_when_nothing_is_needed():
    with patch("app.rag.steps.fetch_context.get_pool") as get_pool:
        assert asyncio.run(fetch_context.articles(set())) == {}
        get_pool.assert_not_called()


def test_the_lookup_degrades_to_empty_when_the_pool_is_unavailable():
    with patch("app.rag.steps.fetch_context.get_pool", return_value=None):
        assert asyncio.run(fetch_context.articles({"summa/q1/a1"})) == {}


def test_the_lookup_degrades_to_empty_when_the_query_fails():
    pool = AsyncMock()
    pool.fetch.side_effect = RuntimeError("connection reset")
    with patch("app.rag.steps.fetch_context.get_pool", return_value=pool):
        assert asyncio.run(fetch_context.articles({"summa/q1/a1"})) == {}


def test_a_lookup_failure_is_a_recovery_not_a_degradation():
    """A degradation marks the run quality- and latency-ineligible and discards the eval
    row, and under DegradationPolicy.RAISE the record call itself raises — turning a
    missing presentation flourish into a failed search."""
    pool = AsyncMock()
    pool.fetch.side_effect = RuntimeError("connection reset")
    with (
        patch("app.rag.steps.fetch_context.get_pool", return_value=pool),
        patch("app.rag.steps.degradation.record_recovery") as recovery,
        patch("app.rag.steps.degradation.record") as record,
    ):
        asyncio.run(fetch_context.articles({"summa/q1/a1"}))

    recovery.assert_called_once()
    record.assert_not_called()


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def test_the_runner_indexes_context_by_chunk_id():
    from app.rag.pipelines.runner import _apply_stitching

    passages = _article()
    context = _apply_stitching([passages[0]], _articles(passages))

    assert set(context) == {"o1"}
    assert context["o1"].relation == stitch.ANSWERED_BY


def test_the_runner_leaves_unstitched_results_out_of_the_context_map():
    from app.rag.pipelines.runner import _apply_stitching

    passages = _article()
    context = _apply_stitching([passages[2], passages[3]], _articles(passages))

    assert context == {}


async def _timed_async(step, coro):
    return await coro


def _timed_sync(step, fn):
    return fn()


def test_the_runner_attaches_context_end_to_end():
    """The guard around stitching swallows ANY exception, including a NameError from the
    helper reaching for something that is not in its scope. Without a success-path
    assertion, that ships the whole feature dead behind a green suite — every result
    unattached, no error anywhere."""
    from app.rag.pipelines import runner

    passages = _article()
    with patch("app.rag.steps.fetch_context.articles",
               new=AsyncMock(return_value=_articles(passages))):
        context = asyncio.run(runner._stitching_context(
            [passages[0]], _timed_async, _timed_sync))

    assert context["o1"].relation == stitch.ANSWERED_BY
    assert [p.content for p in context["o1"].parts] == ["DETERMINATION 0"]


def test_the_runner_passes_the_pipelines_own_timing_helpers():
    """Passed in, not looked up: they close over run_from_candidates' timings list."""
    import inspect

    from app.rag.pipelines import runner

    source = inspect.getsource(runner.run)
    assert "_stitching_context(final, _timed_async, _timed_sync)" in source


def test_a_stitching_failure_does_not_fail_the_search():
    """By this point HyDE, embedding, retrieval, reranking and quota capping have all
    succeeded and nothing has been streamed. An exception in presentation ASSEMBLY — not
    just in the lookup — must not discard a complete paid-for result set behind a ranking
    error."""
    from app.rag.pipelines import runner

    passages = _article()
    with (
        patch("app.rag.steps.fetch_context.articles",
              new=AsyncMock(return_value=_articles(passages))),
        patch("app.rag.steps.stitch.assemble", side_effect=RuntimeError("assembly bug")),
    ):
        result = asyncio.run(runner._stitching_context(
            [passages[0]], _timed_async, _timed_sync))

    assert result == {}


def test_a_stitching_failure_is_a_recovery_not_a_degradation():
    """degradation.record RAISES under DegradationPolicy.RAISE, and this call sits inside
    an except block — so recording a degradation here would escape the guard entirely and
    fail the search it was written to protect."""
    from app.rag.pipelines import runner

    with (
        patch("app.rag.steps.fetch_context.articles",
              new=AsyncMock(side_effect=RuntimeError("db down"))),
        patch("app.rag.steps.degradation.record_recovery") as recovery,
        patch("app.rag.steps.degradation.record") as record,
    ):
        assert asyncio.run(runner._stitching_context(
            [_chunk()], _timed_async, _timed_sync)) == {}

    recovery.assert_called_once()
    record.assert_not_called()


# ---------------------------------------------------------------------------
# The restore path — a saved search must show the card a live search would.
# ---------------------------------------------------------------------------

def _restore_row(chunk_id="c1", unit_label="Objection 1", collection="summa",
                 chapter_key="summa/q1/a1", position=1, document_id="d1"):
    return {"chunk_id": chunk_id, "collection": collection, "position": position,
            "unit_label": unit_label, "chapter_key": chapter_key,
            "document_id": document_id}


def test_restore_applies_the_same_role_rules_as_the_live_path():
    from app.routes.search import _as_chunk

    assert stitch.attachment_relation(
        _as_chunk(_restore_row(unit_label="Objection 3"))) == stitch.ANSWERED_BY
    assert stitch.attachment_relation(
        _as_chunk(_restore_row(unit_label="Reply to Objection 2"))) == stitch.ANSWERS
    assert stitch.attachment_relation(
        _as_chunk(_restore_row(unit_label="On the contrary"))) is None
    assert stitch.attachment_relation(
        _as_chunk(_restore_row(unit_label="Can. 33", collection="canon-law"))) is None


def test_the_restore_shim_carries_the_fields_stitching_depends_on():
    """chunk_id keys the context back to its row; position locates the passage inside
    its article when a chapter_key covers more than one."""
    from app.routes.search import _as_chunk

    chunk = _as_chunk(_restore_row(chunk_id="abc", position=7))

    assert chunk.chunk_id == "abc" and chunk.position == 7


def test_restore_builds_an_objection_card():
    from app.routes.search import _restore_context

    with patch("app.rag.steps.fetch_context.articles",
               new=AsyncMock(return_value=_articles(_article()))):
        result = asyncio.run(_restore_context([_restore_row(chunk_id="o1", position=0)]))

    assert result["o1"].relation == stitch.ANSWERED_BY
    assert [p.content for p in result["o1"].parts] == ["DETERMINATION 0"]


def test_restore_builds_a_reply_card():
    from app.routes.search import _restore_context

    with patch("app.rag.steps.fetch_context.articles",
               new=AsyncMock(return_value=_articles(_article()))):
        result = asyncio.run(_restore_context(
            [_restore_row(chunk_id="r2", unit_label="Reply to Objection 2", position=5)]))

    assert result["r2"].relation == stitch.ANSWERS
    assert [p.content for p in result["r2"].parts] == ["OBJECTION 2"]


def test_restore_pairs_context_with_the_right_passage():
    """Keyed by chunk_id, never zipped against the row list. A positional pairing would
    hand one passage's context to another — attaching one article's objection to a
    different article's text, a fabricated attribution."""
    from app.routes.search import _restore_context

    rows = [_restore_row(chunk_id="sc", unit_label="On the contrary", position=2),
            _restore_row(chunk_id="o2", unit_label="Objection 2", position=1),
            _restore_row(chunk_id="r1", unit_label="Reply to Objection 1", position=4)]

    with patch("app.rag.steps.fetch_context.articles",
               new=AsyncMock(return_value=_articles(_article()))):
        result = asyncio.run(_restore_context(rows))

    assert set(result) == {"o2", "r1"}
    assert [p.content for p in result["o2"].parts] == ["DETERMINATION 0"]
    assert [p.content for p in result["r1"].parts] == ["OBJECTION 1"]


def test_restore_fetches_nothing_when_no_row_needs_context():
    from app.routes.search import _restore_context

    rows = [_restore_row(unit_label="I answer that"),
            _restore_row(unit_label=None, collection="bible")]
    with patch("app.rag.steps.fetch_context.articles", new=AsyncMock()) as fetch:
        assert asyncio.run(_restore_context(rows)) == {}
        fetch.assert_not_awaited()


def test_restore_degrades_to_empty_when_the_lookup_fails():
    """A saved search renders without context rather than failing to open."""
    from app.routes.search import _restore_context

    with patch("app.rag.steps.fetch_context.articles",
               new=AsyncMock(side_effect=RuntimeError("db down"))):
        assert asyncio.run(_restore_context([_restore_row()])) == {}


def _route_row(chunk_id, unit_label, position, rank=1):
    return {"rank": rank, "reranker_score": 0.9, "explanation": "why",
            "chunk_id": chunk_id, "content": "text", "reference": "ST I q1 a1",
            "position": position, "anchor": f"a/{position}",
            "chapter_key": "summa/q1/a1", "unit_label": unit_label,
            "collection": "summa", "document_title": "Summa Theologiae",
            "author": "Thomas Aquinas", "document_id": "d1"}


def _restore_pool(rows, context_delay=0.0):
    """A pool stubbed for get_search_results: one search row, then the retrieval rows."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": "s1", "query": "q", "filters": {},
                                 "result_count": len(rows)}
    pool.fetch.return_value = rows
    return pool


def _get_results(pool, articles_impl):
    from app.models.auth import AuthUser
    from app.routes import search

    user = AuthUser(user_id="00000000-0000-0000-0000-000000000009", email="a@b.c")
    with (
        patch("app.routes.search.get_pool", return_value=pool),
        patch("app.rag.steps.fetch_context.articles", new=articles_impl),
    ):
        return asyncio.run(search.get_search_results(
            "00000000-0000-0000-0000-000000000003", user))


def test_restore_is_bounded_by_the_request_timeout():
    """The context lookup is a second round trip on the same pool. Outside the 8s bound
    a stall there leaves History loading indefinitely — so a slow lookup must surface as
    a 504, not hang.

    The real bound is shortened for the test, and asserted separately, so this proves the
    lookup is INSIDE the timeout without spending 8 seconds to do it."""
    from fastapi import HTTPException

    requested: list[float] = []
    real_timeout = asyncio.timeout

    def short_timeout(seconds):
        requested.append(seconds)
        return real_timeout(0.05)

    async def never_returns(keys):
        await asyncio.sleep(30)
        return {}

    pool = _restore_pool([_route_row("o1", "Objection 1", 0)])
    with patch("asyncio.timeout", short_timeout), pytest.raises(HTTPException) as raised:
        _get_results(pool, never_returns)

    assert raised.value.status_code == 504
    assert requested == [8]


def test_the_restored_response_carries_the_context_it_rebuilt():
    """Rebuilding the context and then not attaching it to the response would leave
    History showing bare objections while live search showed complete cards."""
    passages = _article()
    pool = _restore_pool([_route_row("o1", "Objection 1", 0)])

    response = _get_results(pool, AsyncMock(return_value=_articles(passages)))

    assert response.results[0].context.relation == stitch.ANSWERED_BY
    assert [p.content for p in response.results[0].context.parts] == ["DETERMINATION 0"]


def test_a_restored_result_needing_nothing_carries_no_context():
    pool = _restore_pool([_route_row("d1", "I answer that", 3)])

    response = _get_results(pool, AsyncMock(return_value={}))

    assert response.results[0].context is None
