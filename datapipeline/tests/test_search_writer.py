from model import Passage, Document
from writers.search_writer import build_embedding_input, build_point


def _p(pos, content, anchor):
    return Passage(content=content, reference=f"r{pos}", anchor=anchor,
                   chapter_key="john/3", chapter_label="John 3", position=pos)


def test_embedding_input_adds_neighbor_context_within_chapter():
    ps = [_p(0, "Aaa.", "john/3/1"), _p(1, "Bbb.", "john/3/2"), _p(2, "Ccc.", "john/3/3")]
    out = build_embedding_input(ps, 1, k_prev=10, k_next=10, prefix="[John 3] ")
    assert out.startswith("[John 3] ")
    assert "Bbb." in out and "Aaa." in out and "Ccc." in out


def test_embedding_input_does_not_cross_chapter():
    a = _p(0, "Aaa.", "john/3/1")
    b = Passage(content="Bbb.", reference="r", anchor="john/4/1",
                chapter_key="john/4", chapter_label="John 4", position=1)
    out = build_embedding_input([a, b], 1, k_prev=50, k_next=50, prefix="")
    assert "Aaa." not in out  # previous passage is a different chapter


def test_build_point_uses_named_dense_vector():
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses")
    p = Passage(content="x", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)
    pt = build_point(doc, p, [0.1, 0.2, 0.3])
    assert pt.vector == {"dense": [0.1, 0.2, 0.3]}
    assert pt.payload["collection"] == "bible"
    assert pt.payload["content"] == "x"
