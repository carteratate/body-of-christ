import pytest
from embeddings import EmbeddingClient


class _Emb:
    def __init__(self, i, v): self.index = i; self.embedding = v
class _Resp:
    def __init__(self, data): self.data = data
class _Embeddings:
    def __init__(self): self.calls = []
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        # return out of order to prove sorting
        return _Resp([_Emb(1, [0.9]), _Emb(0, [0.1])])
class _OpenAI:
    def __init__(self): self.embeddings = _Embeddings()
    async def close(self): pass


@pytest.mark.asyncio
async def test_embed_sorts_and_omits_dimensions():
    c = EmbeddingClient(api_key="k", model="text-embedding-3-large")
    c._client = _OpenAI()
    out = await c.embed(["a", "b"])
    assert out == [[0.1], [0.9]]                 # sorted by index
    assert "dimensions" not in c._client.embeddings.calls[0]  # native dims
    assert c._client.embeddings.calls[0]["model"] == "text-embedding-3-large"
