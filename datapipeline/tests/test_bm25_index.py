import pytest
from stages.bm25_index import encode, build_sparse_update


class _Sparse:
    def __init__(self, indices, values): self.indices = indices; self.values = values


class _Model:
    def embed(self, texts):
        return [_Sparse([1, 5, 9], [0.2, 0.5, 0.1]) for _ in texts]


def test_encode_returns_indices_and_values():
    idx, vals = encode(_Model(), "the eucharist")
    assert idx == [1, 5, 9] and vals == [0.2, 0.5, 0.1]


def test_build_sparse_update_names_both_vectors():
    upd = build_sparse_update("cid1", [1, 2], [0.1, 0.2], [3, 4], [0.3, 0.4])
    assert upd["id"] == "cid1"
    assert set(upd["vector"].keys()) == {"sparse_content", "sparse_annotation"}
    assert upd["vector"]["sparse_content"].indices == [1, 2]
    assert upd["vector"]["sparse_annotation"].values == [0.3, 0.4]
