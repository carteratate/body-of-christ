import os

# config.py constructs its module-level singleton at import time via
# _require_env(), which raises if these vars are absent. The real
# datapipeline/.env does not define QDRANT_URL/QDRANT_API_KEY, so we need
# placeholders present before the first `import config` in this process
# (matching the convention used by other test files, e.g.
# tests/test_enrichment_merge.py). setdefault() never overwrites a real
# value and is a one-time bootstrap, not per-test monkeypatching.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import pytest
from enrichment.client import EnrichmentClient, Usage, SchemaValidationError


class _FakeToolUse:
    def __init__(self, data):
        self.type = "tool_use"
        self.input = data


class _FakeResp:
    def __init__(self, data, in_tok=100, out_tok=50):
        self.content = [_FakeToolUse(data)]
        class U: pass
        self.usage = U(); self.usage.input_tokens = in_tok; self.usage.output_tokens = out_tok


class _FakeMessages:
    def __init__(self, data): self._data = data; self.calls = []
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResp(self._data)


class _FakeAnthropic:
    def __init__(self, data): self.messages = _FakeMessages(data)
    async def close(self): pass


def test_usage_cost():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert u.cost(5.0, 25.0) == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_generate_parses_tool_output(monkeypatch):
    fake = _FakeAnthropic({"facets": [{"text": "t", "takeaway": "tk", "question": "q"}]})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake  # inject
    out, usage = await c.generate("sys", "ctx")
    assert out.facets[0].text == "t"
    assert out.facets[0].takeaway == "tk"
    assert usage.input_tokens == 100 and usage.output_tokens == 50
    # forced tool choice was used
    assert fake.messages.calls[0]["tool_choice"]["type"] == "tool"


@pytest.mark.asyncio
async def test_generate_appends_retry_errors():
    fake = _FakeAnthropic({"facets": [{"text": "t", "takeaway": "tk", "question": "q"}]})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    await c.generate("sys", "ctx", retry_errors="facet[0] word_count: too short")
    msg = str(fake.messages.calls[0]["messages"])
    assert "facet[0] word_count: too short" in msg


@pytest.mark.asyncio
async def test_generate_raises_schema_validation_error_on_missing_field():
    fake = _FakeAnthropic({"facets": [{"text": "t", "question": "q"}]})  # missing takeaway
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.generate("sys", "ctx")
    assert exc_info.value.raw == {"facets": [{"text": "t", "question": "q"}]}


@pytest.mark.asyncio
async def test_classify_parses_labels():
    fake = _FakeAnthropic({"labels": [{"grounding": "explicit", "evidence": "quoted words",
                                        "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    out, _ = await c.classify("sys", "ctx", [("facet text 0", "question 0")])
    assert out.labels[0].kind == "doctrinal"
    # the facet texts and questions are included in the user message
    msg = str(fake.messages.calls[0]["messages"])
    assert "facet text 0" in msg
    assert "question 0" in msg


@pytest.mark.asyncio
async def test_classify_appends_retry_errors():
    fake = _FakeAnthropic({"labels": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    await c.classify("sys", "ctx", [("t", "q")], retry_errors="label count mismatch")
    msg = str(fake.messages.calls[0]["messages"])
    assert "label count mismatch" in msg


@pytest.mark.asyncio
async def test_assemble_annotation_parses_output():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL | explicit]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    out, _ = await c.assemble_annotation("sys", "ctx", facets)
    assert out.annotation.startswith("SUMMARY:")
    msg = str(fake.messages.calls[0]["messages"])
    assert "doctrinal | explicit" in msg


@pytest.mark.asyncio
async def test_assemble_annotation_includes_secondary_kind():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL/MORAL | settled]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "settled",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": "moral"}]
    await c.assemble_annotation("sys", "ctx", facets)
    msg = str(fake.messages.calls[0]["messages"])
    assert "doctrinal/moral | settled" in msg


@pytest.mark.asyncio
async def test_classify_raises_schema_validation_error_on_bad_enum():
    fake = _FakeAnthropic({"labels": [{"grounding": "not-a-real-value", "evidence": "e",
                                        "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.classify("sys", "ctx", [("t", "q")])
    assert exc_info.value.raw == {"labels": [{"grounding": "not-a-real-value", "evidence": "e",
                                                "kind": "doctrinal"}]}
    assert exc_info.value.usage.input_tokens == 100


@pytest.mark.asyncio
async def test_assemble_annotation_raises_schema_validation_error_on_missing_field():
    fake = _FakeAnthropic({})  # missing required `annotation` field
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.assemble_annotation("sys", "ctx", facets)
    assert exc_info.value.raw == {}


@pytest.mark.asyncio
async def test_assemble_annotation_appends_retry_errors():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL | explicit]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    await c.assemble_annotation("sys", "ctx", facets, retry_errors="segment count mismatch")
    msg = str(fake.messages.calls[0]["messages"])
    assert "segment count mismatch" in msg
