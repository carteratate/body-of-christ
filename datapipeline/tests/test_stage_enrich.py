import os

# config.py constructs its module-level singleton at import time via
# _require_env(), which raises if these vars are absent. The real
# datapipeline/.env does not define QDRANT_URL/QDRANT_API_KEY, so we need
# placeholders present before the first `import config` in this process
# (matching the convention used by other test files, e.g.
# tests/test_enrichment_client.py). setdefault() never overwrites a real
# value and is a one-time bootstrap, not per-test monkeypatching.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import asyncio
import dataclasses

import pytest
from model import Document, Passage
from cache import Cache
from config import settings as base_settings
from enrichment.backup import Backup
from enrichment.client import SchemaValidationError, Usage
from enrichment.validation import ValidationFailedError
import stages.enrich as enrich_mod
from stages.enrich import enrich_one, enrich_collection, EnrichDeps


def _labels(kinds, grounding="explicit"):
    return [{"facet_id": f"f{i + 1}", "grounding": grounding, "evidence": f"e{i}", "kind": k}
            for i, k in enumerate(kinds)]


def _valid_facet_dict(tag):
    """A GenFacet dict that passes validate_generation()'s hard checks: 1
    sentence, 30-70 words, no banned opener, a capitalized non-initial token
    ("David's") for concreteness, and a `text` clearly distinct from the
    takeaway so the anti-copy check doesn't trip."""
    return {
        "text": f"This is the raw working treatment for facet {tag}, written out in "
                f"full theological detail for the purposes of this test.",
        "takeaway": (
            f"This passage establishes David's kingship through a theological claim "
            f"labeled {tag} that remains distinct from any other reading, grounded "
            f"firmly in the surrounding narrative context and consistent with sound "
            f"doctrine throughout."
        ),
        "question": f"q{tag}",
    }


class _StubGenClient:
    def __init__(self):
        self.gen_calls = 0

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.gen_calls += 1
        from enrichment.schema import GenerationOutput
        return GenerationOutput.model_validate(
            {"facets": [_valid_facet_dict("0"), _valid_facet_dict("1")]}
        ), Usage(10, 5)


class _StubClassifyClient:
    def __init__(self):
        self.cls_calls = 0
        self.ann_calls = 0

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": _labels(["doctrinal", "typological"], grounding="settled")}
        ), Usage(8, 3)

    async def assemble_annotation(self, system, context, facets_with_labels, temperature=None, retry_errors=None):
        self.ann_calls += 1
        from enrichment.schema import AnnotationOutput
        segments = "\n".join(
            f"[{f['kind'].upper()}{'/' + f['kind_secondary'].upper() if f.get('kind_secondary') else ''} "
            f"| {f['grounding']}]: text for facet {i}"
            for i, f in enumerate(facets_with_labels)
        )
        return AnnotationOutput.model_validate(
            {"annotation": f"SUMMARY: overview.\n\n{segments}"}
        ), Usage(6, 4)


def _doc():
    p = Passage(content="In the beginning", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)
    return Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p])


def _deps(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    writes = []
    async def writer(chunk_id, annotation): writes.append((chunk_id, annotation))
    return EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=_StubClassifyClient(),
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer), writes


@pytest.mark.asyncio
async def test_enrich_one_writes_everything(tmp_path):
    deps, writes = _deps(tmp_path)
    doc = _doc()
    merged, usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]
    assert [f.grounding for f in merged.facets] == ["settled", "settled"]
    assert usage.input_tokens == 24  # 10 (gen) + 8 (classify) + 6 (annotate)
    # cache populated for all three passes plus the merged record
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_generation(cid, ch) is not None
    assert deps.cache.get_classification(cid, ch) is not None
    assert deps.cache.get_annotation(cid, ch) is not None
    assert deps.cache.get_enrichment(cid, ch) is not None
    # supabase writer called
    assert writes and writes[0][0] == cid
    # backup written (3 lines: generation + classification + annotation)
    import os
    lines = open(os.path.join(deps.backup.dir_path, "bible.jsonl")).read().strip().splitlines()
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_enrich_one_second_run_hits_cache_for_all_passes(tmp_path):
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    gen_calls_before = deps.gen_client.gen_calls
    cls_calls_before = deps.classify_client.cls_calls
    ann_calls_before = deps.classify_client.ann_calls
    _, usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.gen_client.gen_calls == gen_calls_before
    assert deps.classify_client.cls_calls == cls_calls_before
    assert deps.classify_client.ann_calls == ann_calls_before
    assert usage.input_tokens == 0  # fully-merged cache hit short-circuits everything


# --- cache dependency graph: classification/annotation/merged must invalidate
# when an UPSTREAM artifact changes, not just their own prompt hash ---

@pytest.mark.asyncio
async def test_classification_reruns_when_cached_generation_hash_mismatches(tmp_path):
    """Simulates: generation reran (for any reason) and produced different
    facets, so the previously-cached classification's stored generation_hash
    no longer matches — even though classification's OWN prompt/model/
    temperature never changed, it must be treated as stale."""
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    cls_row = deps.cache.get_classification(cid, ch)
    # Corrupt the stored generation_hash to simulate "generation's output
    # changed since this classification was computed".
    deps.cache.put_classification(
        cid, ch, cls_row["labels"], cls_row["prompt_hash"], cls_row["model"],
        temperature=cls_row["temperature"], schema_version=cls_row["schema_version"],
        generation_hash="stale-generation-hash-does-not-match-current-facets")
    deps.cache.conn.execute("DELETE FROM enrichment WHERE chunk_id=?", (cid,))
    deps.cache.conn.commit()

    cls_calls_before = deps.classify_client.cls_calls
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.classify_client.cls_calls == cls_calls_before + 1


@pytest.mark.asyncio
async def test_annotation_reruns_when_cached_classification_hash_mismatches(tmp_path):
    """Simulates: classification reran and produced different labels, so the
    previously-cached annotation's stored classification_hash no longer
    matches — even though annotation's OWN prompt/model/temperature never
    changed."""
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    ann_row = deps.cache.get_annotation(cid, ch)
    deps.cache.put_annotation(
        cid, ch, ann_row["annotation"], ann_row["prompt_hash"], ann_row["model"],
        temperature=ann_row["temperature"], schema_version=ann_row["schema_version"],
        generation_hash=ann_row["generation_hash"],
        classification_hash="stale-classification-hash-does-not-match-current-labels")
    deps.cache.conn.execute("DELETE FROM enrichment WHERE chunk_id=?", (cid,))
    deps.cache.conn.commit()

    ann_calls_before = deps.classify_client.ann_calls
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.classify_client.ann_calls == ann_calls_before + 1


@pytest.mark.asyncio
async def test_annotation_reruns_when_cached_generation_hash_mismatches(tmp_path):
    """Same as above but for the generation_hash leg of annotation's two
    upstream dependencies — a change further up the chain must still be
    caught even if classification_hash happens to still match."""
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    ann_row = deps.cache.get_annotation(cid, ch)
    deps.cache.put_annotation(
        cid, ch, ann_row["annotation"], ann_row["prompt_hash"], ann_row["model"],
        temperature=ann_row["temperature"], schema_version=ann_row["schema_version"],
        generation_hash="stale-generation-hash", classification_hash=ann_row["classification_hash"])
    deps.cache.conn.execute("DELETE FROM enrichment WHERE chunk_id=?", (cid,))
    deps.cache.conn.commit()

    ann_calls_before = deps.classify_client.ann_calls
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.classify_client.ann_calls == ann_calls_before + 1


@pytest.mark.asyncio
async def test_merged_cache_cannot_bypass_an_upstream_hash_mismatch(tmp_path):
    """The merged-result cache must not be trusted merely because
    (chunk_id, content_hash) matches — it must also match all three current
    dependency hashes. Here we corrupt the merged row's stored
    annotation_hash directly; the merged cache must be recomputed (via a
    cheap in-memory merge, no new API calls) rather than returned as-is."""
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    merged_row = deps.cache.get_enrichment(cid, ch)
    # Poison the merged row with a bogus stored annotation_hash but leave the
    # persisted facets/annotation alone as an obviously-wrong sentinel — if
    # the merged cache were incorrectly trusted, this sentinel would come back.
    poisoned_facets = [{**f, "kind": "STALE_SENTINEL"} for f in merged_row["facets"]]
    deps.cache.put_enrichment(
        cid, ch, poisoned_facets, "STALE SENTINEL ANNOTATION",
        generation_hash=merged_row["generation_hash"],
        classification_hash=merged_row["classification_hash"],
        annotation_hash="stale-annotation-hash-does-not-match-current-annotation",
        schema_version=merged_row["schema_version"])

    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert merged.annotation != "STALE SENTINEL ANNOTATION"
    assert all(f.kind != "STALE_SENTINEL" for f in merged.facets)
    # no new API calls were needed — all three stages still hit their own cache
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]


@pytest.mark.asyncio
async def test_generation_cache_miss_when_temperature_setting_changed(tmp_path, monkeypatch):
    """A generation cache row is only trusted when its stored temperature
    still matches the current configured PASS1_TEMPERATURE — a config change
    (even with the prompt unchanged) must force a fresh Pass 1 call."""
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    patched_settings = dataclasses.replace(base_settings, PASS1_TEMPERATURE=0.5)
    monkeypatch.setattr(enrich_mod, "settings", patched_settings)

    gen_calls_before = deps.gen_client.gen_calls
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.gen_client.gen_calls == gen_calls_before + 1


@pytest.mark.asyncio
async def test_sample_mode_writes_nothing(tmp_path):
    deps, writes = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=True)
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_generation(cid, ch) is None
    assert deps.cache.get_classification(cid, ch) is None
    assert deps.cache.get_annotation(cid, ch) is None
    assert deps.cache.get_enrichment(cid, ch) is None
    assert writes == []
    import os
    assert not os.path.exists(os.path.join(deps.backup.dir_path, "bible.jsonl"))


@pytest.mark.asyncio
async def test_enrich_collection_bounds_concurrency(tmp_path, monkeypatch):
    deps, _ = _deps(tmp_path)
    docs = []
    for i in range(3):
        p = Passage(content=f"In the beginning {i}", reference=f"Gen 1:{i}",
                    anchor=f"genesis/1/{i}", chapter_key="genesis/1",
                    chapter_label="Genesis 1", position=i)
        docs.append(Document(id=f"d{i}", collection="bible", title="Genesis",
                             author="Moses", passages=[p]))

    concurrent = 0
    max_concurrent = 0
    orig_generate = deps.gen_client.generate

    async def tracked_generate(system, context):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await asyncio.sleep(0.01)
        result = await orig_generate(system, context)
        concurrent -= 1
        return result

    deps.gen_client.generate = tracked_generate

    patched_settings = dataclasses.replace(base_settings, OPUS_CONCURRENCY=2)
    monkeypatch.setattr(enrich_mod, "settings", patched_settings)

    stats = await enrich_collection(docs, "bible", deps, sample=False)

    assert max_concurrent <= 2
    assert stats.processed == 3


@pytest.mark.asyncio
async def test_enrich_collection_sample_mode_skips_status_and_writes(tmp_path):
    deps, writes = _deps(tmp_path)
    doc = _doc()
    await enrich_collection([doc], "bible", deps, sample=True)
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_generation(cid, ch) is None
    assert deps.cache.get_classification(cid, ch) is None
    assert deps.cache.get_enrichment(cid, ch) is None
    assert deps.cache.get_collection_status("bible") is None
    assert writes == []
    import os
    assert not os.path.exists(os.path.join(deps.backup.dir_path, "bible.jsonl"))


class _PartiallyFailingClassifyClient(_StubClassifyClient):
    """Like _StubClassifyClient, but returns a mismatched facet/label count for
    one specific chunk (identified by reference), causing merge() to raise
    MergeError for that chunk only."""

    def __init__(self, bad_reference):
        super().__init__()
        self.bad_reference = bad_reference

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        if f"reference: {self.bad_reference}" in context:
            # Only one label for two facets -> merge() raises MergeError.
            return ClassificationOutput.model_validate(
                {"labels": _labels(["doctrinal"], grounding="settled")}), Usage(8, 3)
        return ClassificationOutput.model_validate(
            {"labels": _labels(["doctrinal", "typological"], grounding="settled")}), Usage(8, 3)


@pytest.mark.asyncio
async def test_enrich_collection_isolates_per_chunk_failures(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _PartiallyFailingClassifyClient(bad_reference="Gen 1:1")
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)

    docs = []
    for i in range(3):
        p = Passage(content=f"In the beginning {i}", reference=f"Gen 1:{i}",
                    anchor=f"genesis/1/{i}", chapter_key="genesis/1",
                    chapter_label="Genesis 1", position=i)
        docs.append(Document(id=f"d{i}", collection="bible", title="Genesis",
                             author="Moses", passages=[p]))

    stats = await enrich_collection(docs, "bible", deps, sample=False)

    from identity import passage_id
    good_ids = [passage_id(f"d{i}", f"genesis/1/{i}") for i in (0, 2)]
    bad_id = passage_id("d1", "genesis/1/1")

    # whole batch does not raise; successes are cached
    for cid, i in zip(good_ids, (0, 2)):
        ch = Cache.content_hash(f"In the beginning {i}")
        assert cache.get_enrichment(cid, ch) is not None

    # failed chunk's enrichment is not cached
    ch_bad = Cache.content_hash("In the beginning 1")
    assert cache.get_enrichment(bad_id, ch_bad) is None

    # collection status reflects the failure
    status = cache.get_collection_status("bible")
    assert status is not None
    assert status["complete"] == 0
    assert status["total_chunks"] == 3
    assert status["enriched"] == 2

    # failure surfaced on stats
    assert stats.processed == 3
    assert len(stats.failed) == 1
    assert stats.failed[0][0] == bad_id
    assert stats.failed[0][1] == "Gen 1:1"


@pytest.mark.asyncio
async def test_enrich_collection_sets_status_when_not_sample(tmp_path):
    deps, _ = _deps(tmp_path)
    doc = _doc()
    stats = await enrich_collection([doc], "bible", deps, sample=False)
    status = deps.cache.get_collection_status("bible")
    assert status is not None
    assert status["complete"] == 1
    assert status["total_chunks"] == 1
    assert status["enriched"] == 1
    assert stats.processed == 1


# --- Pass 2/3 validation + retry-once-then-mark-failed policy ---

class _BadThenGoodClassifyClient(_StubClassifyClient):
    """Fails classification validation on the first call (evidence not found
    in the passage), then succeeds on the retry."""

    def __init__(self):
        super().__init__()

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        if retry_errors is None:
            return ClassificationOutput.model_validate(
                {"labels": [{"facet_id": "f1", "grounding": "explicit",
                            "evidence": "not in the passage anywhere", "kind": "doctrinal"},
                           {"facet_id": "f2", "grounding": "settled", "evidence": "e1",
                            "kind": "typological"}]}
            ), Usage(8, 3)
        return ClassificationOutput.model_validate(
            {"labels": _labels(["doctrinal", "typological"], grounding="settled")}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_retries_once_on_validation_failure_then_succeeds(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _BadThenGoodClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert client.cls_calls == 2
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]


class _CapturingBadThenGoodClassifyClient(_StubClassifyClient):
    """Like _BadThenGoodClassifyClient, but records the retry_errors text the
    retry call actually received, so the test can assert on its exact content
    rather than merely that a retry happened."""

    def __init__(self):
        super().__init__()
        self.retry_errors_seen: str | None = None

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        if retry_errors is None:
            return ClassificationOutput.model_validate(
                {"labels": [{"facet_id": "f1", "grounding": "explicit",
                            "evidence": "not in the passage anywhere", "kind": "doctrinal"},
                           {"facet_id": "f2", "grounding": "settled", "evidence": "e1",
                            "kind": "typological"}]}
            ), Usage(8, 3)
        self.retry_errors_seen = retry_errors
        return ClassificationOutput.model_validate(
            {"labels": _labels(["doctrinal", "typological"], grounding="settled")}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_explicit_grounding_retry_message_is_surgical_and_self_sufficient(tmp_path):
    """Item 7: the retry context for a failed explicit-grounding facet must
    name the exact failing facet_id, state the contiguous-span rule precisely
    (punctuation/whitespace-normalized containment, not byte-for-byte
    verbatim), give concrete remediation options, and restate the full
    facet_id bijection requirement — since this text is the model's ONLY
    context for the retry attempt (_call_with_retry appends it verbatim)."""
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _CapturingBadThenGoodClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)

    msg = client.retry_errors_seen
    assert msg is not None
    assert "Facet f1 failed" in msg
    assert "grounding=explicit" in msg
    assert "contiguous span" in msg
    assert "punctuation/whitespace-normalized containment, not byte-for-byte verbatim" in msg
    assert "not in the passage anywhere" in msg  # the exact evidence that failed, quoted back
    assert "Reclassify f1 only" in msg
    assert "settled or inferential" in msg
    assert "full ID bijection" in msg
    # must not mention f2 as failing — only f1's evidence was bad
    assert "Facet f2 failed" not in msg


class _AlwaysBadClassifyClient(_StubClassifyClient):
    """Always fails classification validation (evidence never in the passage)."""

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"facet_id": "f1", "grounding": "explicit",
                        "evidence": "not in the passage anywhere", "kind": "doctrinal"},
                       {"facet_id": "f2", "grounding": "settled", "evidence": "e1",
                        "kind": "typological"}]}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_marks_chunk_failed_after_second_validation_failure(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _AlwaysBadClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    with pytest.raises(ValidationFailedError):
        await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert client.cls_calls == 2

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    status = cache.get_chunk_status(cid, ch)
    assert status is not None
    assert status["status"] == "classification_failed"
    assert status["raw_response"] is not None
    assert "not found" in status["validation_errors"] or "evidence" in status["validation_errors"]


@pytest.mark.asyncio
async def test_classification_failure_never_persisted_in_sample_mode(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _AlwaysBadClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    with pytest.raises(ValidationFailedError):
        await enrich_one(doc, doc.passages[0], deps, sample=True)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert cache.get_chunk_status(cid, ch) is None


class _BadAnnotationClient(_StubClassifyClient):
    """Classification succeeds; annotation assembly always omits a segment,
    which fails the hard segment-count check."""

    async def assemble_annotation(self, system, context, facets_with_labels, temperature=None, retry_errors=None):
        self.ann_calls += 1
        from enrichment.schema import AnnotationOutput
        return AnnotationOutput.model_validate(
            {"annotation": "SUMMARY: overview.\n\n[DOCTRINAL | settled]: only one segment"}
        ), Usage(6, 4)


@pytest.mark.asyncio
async def test_annotation_marks_chunk_failed_after_second_validation_failure(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _BadAnnotationClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    with pytest.raises(ValidationFailedError):
        await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert client.ann_calls == 2

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    status = cache.get_chunk_status(cid, ch)
    assert status is not None
    assert status["status"] == "annotation_failed"
    # classification itself succeeded and should still be cached independently
    assert cache.get_classification(cid, ch) is not None
    assert cache.get_enrichment(cid, ch) is None


class _SchemaBreakingClassifyClient(_StubClassifyClient):
    """First call returns a malformed enum (schema-level failure surfaced as
    SchemaValidationError by the client), second call (retry) succeeds."""

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        if retry_errors is None:
            raise SchemaValidationError(
                raw={"labels": [{"grounding": "bogus", "evidence": "e", "kind": "doctrinal"}]},
                usage=Usage(8, 3), original=ValueError("invalid grounding enum value"))
        return ClassificationOutput.model_validate(
            {"labels": _labels(["doctrinal", "typological"], grounding="settled")}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_retries_once_on_schema_validation_error_then_succeeds(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _SchemaBreakingClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert client.cls_calls == 2
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]


class _QuoteSpanningVerseBoundaryClassifyClient(_StubClassifyClient):
    """Returns an `explicit` label whose evidence is a real, contiguous quote
    from the passage as the model actually saw it (verse markers stripped),
    but which straddles a raw {{v:N}} marker in the stored passage content."""

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"facet_id": "f1", "grounding": "explicit",
                        "evidence": "no beauty that we should desire him. He was despised",
                        "kind": "doctrinal"},
                       {"facet_id": "f2", "grounding": "settled", "evidence": "e1",
                        "kind": "typological"}]}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_validates_quotes_against_verse_marker_stripped_content(tmp_path):
    """Regression test: validation must check evidence against the same cleaned
    text (verse markers stripped) that was actually sent to the model — not the
    raw stored content, which still has {{v:N}} markers splitting sentences."""
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _QuoteSpanningVerseBoundaryClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    p = Passage(content="there is no beauty that we should desire him. {{v:3}} He was despised "
                        "and rejected by men.",
               reference="Isaiah 53:2-3", anchor="isaiah/53/2", chapter_key="isaiah/53",
               chapter_label="Isaiah 53", position=0)
    doc = Document(id="d1", collection="bible", title="Isaiah", author=None, passages=[p])

    merged, _usage = await enrich_one(doc, p, deps, sample=False)
    assert client.cls_calls == 1  # no retry needed — the quote was valid
    assert merged.facets[0].grounding == "explicit"


class _ReorderedClassifyClient(_StubClassifyClient):
    """Returns labels in the opposite order from the facets they classify —
    valid because identity is established by facet_id, not position."""

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"facet_id": "f2", "grounding": "settled", "evidence": "e1",
                        "kind": "typological"},
                       {"facet_id": "f1", "grounding": "settled", "evidence": "e0",
                        "kind": "doctrinal"}]}
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_accepts_reordered_labels_realigned_by_facet_id(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _ReorderedClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    # no retry needed; the reversed order was accepted and realigned to facet order
    assert client.cls_calls == 1
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]


class _MissingFacetIdClassifyClient(_StubClassifyClient):
    """Always omits one facet's classification entirely (facet_id set never
    covers all supplied facets) — a hard failure, never silently repaired."""

    async def classify(self, system, context, facets, temperature=None, retry_errors=None):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"facet_id": "f1", "grounding": "settled", "evidence": "e0",
                        "kind": "doctrinal"},
                       {"facet_id": "f1", "grounding": "settled", "evidence": "e0",
                        "kind": "moral"}]}  # duplicate f1, f2 never classified
        ), Usage(8, 3)


@pytest.mark.asyncio
async def test_classification_marks_chunk_failed_on_missing_and_duplicate_facet_id(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    async def writer(chunk_id, annotation): pass
    client = _MissingFacetIdClassifyClient()
    deps = EnrichDeps(cache=cache, gen_client=_StubGenClient(), classify_client=client,
                      backup=Backup(str(tmp_path / "bak")), annotation_writer=writer)
    doc = _doc()
    with pytest.raises(ValidationFailedError) as exc_info:
        await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert client.cls_calls == 2  # retried once, still failed
    assert any("duplicate facet_id" in e or "missing classification" in e
               for e in exc_info.value.errors)


@pytest.mark.asyncio
async def test_legacy_classification_cache_row_without_dependency_hash_is_not_reused(tmp_path):
    """A classification cache row written before facet ids / dependency hashes
    existed lacks `facet_id` on its labels AND lacks a stored generation_hash.
    Per the cache-dependency-graph rule (prefer safe recomputation over
    questionable legacy reuse), such a row must NOT be trusted merely because
    content_hash and prompt_hash still match — it must trigger a fresh Pass 2
    call rather than silently reusing stale, unproven data."""
    deps, _ = _deps(tmp_path)
    doc = _doc()

    # Seed a fresh run so generation is cached, then overwrite the
    # classification cache row with a legacy shape (no facet_id keys, no
    # generation_hash/temperature/schema_version).
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    cls_prompt_hash = deps.cache.get_classification(cid, ch)["prompt_hash"]
    legacy_labels = [{"grounding": "settled", "evidence": "stale legacy evidence 0", "kind": "moral"},
                     {"grounding": "settled", "evidence": "stale legacy evidence 1", "kind": "historical"}]
    deps.cache.put_classification(cid, ch, legacy_labels, cls_prompt_hash, "claude-sonnet-4-6")
    # Also clear the fully-merged cache so enrich_one re-derives from the
    # (now legacy-shaped) classification cache row instead of short-circuiting.
    deps.cache.conn.execute("DELETE FROM enrichment WHERE chunk_id=?", (cid,))
    deps.cache.conn.commit()

    cls_calls_before = deps.classify_client.cls_calls
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    # a fresh Pass 2 call happened — the legacy row was not trusted
    assert deps.classify_client.cls_calls == cls_calls_before + 1
    # the result reflects the FRESH classification, not the stale legacy one
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]
    assert [f.id for f in merged.facets] == ["f1", "f2"]


# --- Pass 1 (generation/takeaway) validation + retry-once-then-mark-failed policy ---

class _BadThenGoodGenClient(_StubGenClient):
    """First takeaway is far too short (fails word_count); the retry produces a
    valid one."""

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.gen_calls += 1
        from enrichment.schema import GenerationOutput
        if retry_errors is None:
            return GenerationOutput.model_validate(
                {"facets": [{"text": "working text", "takeaway": "Too short.", "question": "q0"},
                           _valid_facet_dict("1")]}
            ), Usage(10, 5)
        return GenerationOutput.model_validate(
            {"facets": [_valid_facet_dict("0"), _valid_facet_dict("1")]}
        ), Usage(10, 5)


@pytest.mark.asyncio
async def test_generation_retries_once_on_validation_failure_then_succeeds(tmp_path):
    deps, _ = _deps(tmp_path)
    deps.gen_client = _BadThenGoodGenClient()
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.gen_client.gen_calls == 2
    assert len(merged.facets) == 2


class _AlwaysBadGenClient(_StubGenClient):
    """Always returns a takeaway that fails word_count validation."""

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.gen_calls += 1
        from enrichment.schema import GenerationOutput
        return GenerationOutput.model_validate(
            {"facets": [{"text": "working text", "takeaway": "Too short.", "question": "q0"},
                       _valid_facet_dict("1")]}
        ), Usage(10, 5)


@pytest.mark.asyncio
async def test_generation_marks_chunk_failed_after_second_validation_failure(tmp_path):
    deps, _ = _deps(tmp_path)
    deps.gen_client = _AlwaysBadGenClient()
    doc = _doc()
    with pytest.raises(ValidationFailedError):
        await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.gen_client.gen_calls == 2

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    status = deps.cache.get_chunk_status(cid, ch)
    assert status is not None
    assert status["status"] == "generation_failed"
    assert status["raw_response"] is not None


@pytest.mark.asyncio
async def test_generation_failure_never_persisted_in_sample_mode(tmp_path):
    deps, _ = _deps(tmp_path)
    deps.gen_client = _AlwaysBadGenClient()
    doc = _doc()
    with pytest.raises(ValidationFailedError):
        await enrich_one(doc, doc.passages[0], deps, sample=True)

    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_chunk_status(cid, ch) is None


# --- naming discipline: downstream of Pass 1, "text"/"facet" means the takeaway ---

@pytest.mark.asyncio
async def test_merged_facet_text_is_takeaway_not_working_text(tmp_path):
    deps, _ = _deps(tmp_path)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert "David's kingship" in merged.facets[0].text  # the takeaway
    assert "raw working treatment" not in merged.facets[0].text


@pytest.mark.asyncio
async def test_working_text_dropped_by_default_pilot_mode_off(tmp_path):
    deps, _ = _deps(tmp_path)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert all(f.working_text is None for f in merged.facets)


@pytest.mark.asyncio
async def test_working_text_persisted_when_pilot_mode_on(tmp_path, monkeypatch):
    from identity import passage_id
    deps, _ = _deps(tmp_path)
    patched_settings = dataclasses.replace(base_settings, PILOT_MODE=True)
    monkeypatch.setattr(enrich_mod, "settings", patched_settings)
    doc = _doc()
    merged, _usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert all(f.working_text is not None for f in merged.facets)
    assert "raw working treatment" in merged.facets[0].working_text

    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    cached = deps.cache.get_enrichment(cid, ch)
    assert cached["facets"][0]["working_text"] is not None
