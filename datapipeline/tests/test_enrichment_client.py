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

import json

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
    out, usage = await c.generate("sys", "ctx", temperature=0.7)
    assert out.facets[0].text == "t"
    assert out.facets[0].takeaway == "tk"
    assert usage.input_tokens == 100 and usage.output_tokens == 50
    # forced tool choice was used
    assert fake.messages.calls[0]["tool_choice"]["type"] == "tool"


@pytest.mark.asyncio
async def test_generate_forwards_temperature_to_the_api_call():
    fake = _FakeAnthropic({"facets": [{"text": "t", "takeaway": "tk", "question": "q"}]})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    await c.generate("sys", "ctx", temperature=0.7)
    assert fake.messages.calls[0]["temperature"] == 0.7


@pytest.mark.asyncio
async def test_generate_appends_retry_errors():
    fake = _FakeAnthropic({"facets": [{"text": "t", "takeaway": "tk", "question": "q"}]})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    await c.generate("sys", "ctx", temperature=0.7, retry_errors="facet[0] word_count: too short")
    msg = str(fake.messages.calls[0]["messages"])
    assert "facet[0] word_count: too short" in msg


@pytest.mark.asyncio
async def test_generate_raises_schema_validation_error_on_missing_field():
    fake = _FakeAnthropic({"facets": [{"text": "t", "question": "q"}]})  # missing takeaway
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.generate("sys", "ctx", temperature=0.7)
    assert exc_info.value.raw == {"facets": [{"text": "t", "question": "q"}]}


@pytest.mark.asyncio
async def test_classify_parses_labels():
    fake = _FakeAnthropic({"labels": [{"facet_id": "f1", "grounding": "explicit",
                                        "evidence": "quoted words", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    out, _ = await c.classify("sys", "ctx", [("f1", "facet text 0", "question 0")], temperature=0.0)
    assert out.labels[0].kind == "doctrinal"
    assert out.labels[0].facet_id == "f1"
    # the facet id, texts, and questions are included in the user message
    msg = str(fake.messages.calls[0]["messages"])
    assert "f1" in msg
    assert "facet text 0" in msg
    assert "question 0" in msg


@pytest.mark.asyncio
async def test_classify_forwards_temperature_to_the_api_call():
    fake = _FakeAnthropic({"labels": [{"facet_id": "f1", "grounding": "explicit",
                                        "evidence": "e", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    assert fake.messages.calls[0]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_classify_appends_retry_errors():
    fake = _FakeAnthropic({"labels": [{"facet_id": "f1", "grounding": "explicit",
                                        "evidence": "x", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0, retry_errors="label count mismatch")
    msg = str(fake.messages.calls[0]["messages"])
    assert "label count mismatch" in msg


@pytest.mark.asyncio
async def test_assemble_annotation_parses_output():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL | explicit]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    out, _ = await c.assemble_annotation("sys", "ctx", facets, temperature=0.3)
    assert out.annotation.startswith("SUMMARY:")
    msg = str(fake.messages.calls[0]["messages"])
    assert "doctrinal | explicit" in msg


@pytest.mark.asyncio
async def test_assemble_annotation_forwards_temperature_to_the_api_call():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL | explicit]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    await c.assemble_annotation("sys", "ctx", facets, temperature=0.3)
    assert fake.messages.calls[0]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_assemble_annotation_includes_secondary_kind():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL/MORAL | settled]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "settled",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": "moral"}]
    await c.assemble_annotation("sys", "ctx", facets, temperature=0.3)
    msg = str(fake.messages.calls[0]["messages"])
    assert "doctrinal/moral | settled" in msg


@pytest.mark.asyncio
async def test_classify_raises_schema_validation_error_on_bad_enum():
    fake = _FakeAnthropic({"labels": [{"facet_id": "f1", "grounding": "not-a-real-value",
                                        "evidence": "e", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    assert exc_info.value.raw == {"labels": [{"facet_id": "f1", "grounding": "not-a-real-value",
                                                "evidence": "e", "kind": "doctrinal"}]}
    assert exc_info.value.usage.input_tokens == 100


# --- stringified `labels` repair (client._repair_stringified_labels) ---

@pytest.mark.asyncio
async def test_classify_leaves_native_labels_array_unchanged(caplog):
    fake = _FakeAnthropic({"labels": [{"facet_id": "f1", "grounding": "explicit",
                                        "evidence": "quoted words", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with caplog.at_level("INFO"):
        out, _ = await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    assert out.labels[0].kind == "doctrinal"
    assert "repaired_stringified_labels" not in caplog.text


@pytest.mark.asyncio
async def test_classify_repairs_valid_stringified_labels_array(caplog):
    stringified = json.dumps([{"facet_id": "f1", "grounding": "explicit",
                               "evidence": "quoted words", "kind": "doctrinal"}])
    fake = _FakeAnthropic({"labels": stringified})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with caplog.at_level("INFO"):
        out, usage = await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    # repaired and otherwise valid -> parses cleanly, no exception, one API call
    assert out.labels[0].kind == "doctrinal"
    assert out.labels[0].grounding == "explicit"
    assert len(fake.messages.calls) == 1
    assert "event=repaired_stringified_labels count=1" in caplog.text
    # the log event never includes the label content itself
    assert "quoted words" not in caplog.text


@pytest.mark.asyncio
async def test_classify_repair_leaves_whitespace_padded_stringified_array_intact():
    stringified = "  " + json.dumps(
        [{"facet_id": "f1", "grounding": "settled", "evidence": "e", "kind": "moral"}]) + "  "
    fake = _FakeAnthropic({"labels": stringified})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    out, _ = await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    assert out.labels[0].kind == "moral"


@pytest.mark.asyncio
async def test_classify_invalid_json_string_still_fails():
    # Looks like an array (starts with '[' / ends with ']') but is not valid JSON.
    fake = _FakeAnthropic({"labels": "[{grounding: explicit, not valid json}]"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError):
        await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)


@pytest.mark.asyncio
async def test_classify_stringified_object_still_fails():
    # A stringified JSON object, not an array -> not repaired, fails normal validation.
    fake = _FakeAnthropic({"labels": json.dumps({"grounding": "explicit"})})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError):
        await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)


@pytest.mark.asyncio
async def test_classify_stringified_scalar_still_fails():
    fake = _FakeAnthropic({"labels": "5"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError):
        await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)


@pytest.mark.asyncio
async def test_classify_decoded_list_with_invalid_label_objects_still_fails():
    # Valid JSON array syntax, decodes to a list, but the label inside has a
    # bad enum value -> repair succeeds structurally, strict schema validation
    # still rejects it (repair is not a substitute for real validation).
    stringified = json.dumps([{"facet_id": "f1", "grounding": "not-a-real-value",
                               "evidence": "e", "kind": "doctrinal"}])
    fake = _FakeAnthropic({"labels": stringified})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.classify("sys", "ctx", [("f1", "t", "q")], temperature=0.0)
    # the repaired (decoded-to-list) payload is what's carried on the error
    assert isinstance(exc_info.value.raw["labels"], list)


@pytest.mark.asyncio
async def test_assemble_annotation_raises_schema_validation_error_on_missing_field():
    fake = _FakeAnthropic({})  # missing required `annotation` field
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    with pytest.raises(SchemaValidationError) as exc_info:
        await c.assemble_annotation("sys", "ctx", facets, temperature=0.3)
    assert exc_info.value.raw == {}


@pytest.mark.asyncio
async def test_assemble_annotation_appends_retry_errors():
    fake = _FakeAnthropic({"annotation": "SUMMARY: x\n\n[DOCTRINAL | explicit]: y"})
    c = EnrichmentClient(api_key="k", model="claude-sonnet-4-6", concurrency=2)
    c._client = fake
    facets = [{"text": "t", "question": "q", "grounding": "explicit",
               "evidence": "e", "kind": "doctrinal", "kind_secondary": None}]
    await c.assemble_annotation("sys", "ctx", facets, temperature=0.3,
                                retry_errors="segment count mismatch")
    msg = str(fake.messages.calls[0]["messages"])
    assert "segment count mismatch" in msg
