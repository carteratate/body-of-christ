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
from enrichment.client import EnrichmentClient, Usage


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
    fake = _FakeAnthropic({"facets": [{"text": "t", "question": "q"}], "annotation": "SUMMARY: x"})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake  # inject
    out, usage = await c.generate("sys", "ctx")
    assert out.facets[0].text == "t"
    assert usage.input_tokens == 100 and usage.output_tokens == 50
    # forced tool choice was used
    assert fake.messages.calls[0]["tool_choice"]["type"] == "tool"


@pytest.mark.asyncio
async def test_classify_parses_labels():
    fake = _FakeAnthropic({"labels": [{"confidence": "explicit", "kind": "doctrinal"}]})
    c = EnrichmentClient(api_key="k", model="claude-opus-4-8", concurrency=2)
    c._client = fake
    out, _ = await c.classify("sys", "ctx", ["facet text 0"])
    assert out.labels[0].kind == "doctrinal"
    # the facet texts are included in the user message
    assert "facet text 0" in str(fake.messages.calls[0]["messages"])
