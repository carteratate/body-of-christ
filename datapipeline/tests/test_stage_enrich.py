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

import pytest
from model import Document, Passage
from cache import Cache
from enrichment.backup import Backup
from enrichment.client import Usage
from stages.enrich import enrich_one, EnrichDeps


class _StubClient:
    def __init__(self):
        self.gen_calls = 0
        self.cls_calls = 0
    async def generate(self, system, context):
        self.gen_calls += 1
        from enrichment.schema import GenerationOutput
        return GenerationOutput.model_validate(
            {"facets": [{"text": "t0", "question": "q0"}, {"text": "t1", "question": "q1"}],
             "annotation": "SUMMARY: x"}), Usage(10, 5)
    async def classify(self, system, context, facet_texts):
        self.cls_calls += 1
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"confidence": "explicit", "kind": "doctrinal"},
                        {"confidence": "traditional", "kind": "typological"}]}), Usage(8, 3)


def _doc():
    p = Passage(content="In the beginning", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)
    return Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p])


def _deps(tmp_path):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    writes = []
    async def writer(chunk_id, annotation): writes.append((chunk_id, annotation))
    return EnrichDeps(cache=cache, client=_StubClient(), backup=Backup(str(tmp_path / "bak")),
                      annotation_writer=writer), writes


@pytest.mark.asyncio
async def test_enrich_one_writes_everything(tmp_path):
    deps, writes = _deps(tmp_path)
    doc = _doc()
    merged, usage = await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert [f.kind for f in merged.facets] == ["doctrinal", "typological"]
    assert usage.input_tokens == 18  # 10 + 8
    # cache populated
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_enrichment(cid, ch) is not None
    # supabase writer called
    assert writes and writes[0][0] == cid
    # backup written (2 lines: generation + classification)
    import os
    lines = open(os.path.join(deps.backup.dir_path, "bible.jsonl")).read().strip().splitlines()
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_enrich_one_second_run_hits_cache(tmp_path):
    deps, _ = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    calls_before = deps.client.gen_calls
    await enrich_one(doc, doc.passages[0], deps, sample=False)
    assert deps.client.gen_calls == calls_before  # no new generation call


@pytest.mark.asyncio
async def test_sample_mode_writes_nothing(tmp_path):
    deps, writes = _deps(tmp_path)
    doc = _doc()
    await enrich_one(doc, doc.passages[0], deps, sample=True)
    from identity import passage_id
    cid = passage_id(doc.id, doc.passages[0].anchor)
    ch = Cache.content_hash(doc.passages[0].content)
    assert deps.cache.get_generation(cid, ch) is None
    assert deps.cache.get_enrichment(cid, ch) is None
    assert writes == []
    import os
    assert not os.path.exists(os.path.join(deps.backup.dir_path, "bible.jsonl"))
