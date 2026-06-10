# datapipeline/tests/test_medieval.py
import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.medieval import fix_multi_work_refs, merge_short_chunks


# ── fix_multi_work_refs ──────────────────────────────────────────────────────

def test_fix_multi_work_refs_rewrites_work_as_author():
    """Refs like 'Proslogium — Chapter I' become 'Anselm — Proslogium, Chapter I'."""
    chunks = [
        ("content", "Proslogium — Chapter I", 0, {}),
        ("content", "Cur Deus Homo — Book II, Chapter III", 1, {}),
    ]
    fixed = fix_multi_work_refs(chunks, "Anselm")
    assert fixed[0][1] == "Anselm — Proslogium, Chapter I"
    assert fixed[1][1] == "Anselm — Cur Deus Homo, Book II, Chapter III"


def test_fix_multi_work_refs_leaves_correct_refs_alone():
    """Refs already starting with the real author name are not touched."""
    chunks = [("content", "Anselm — Proslogium, Chapter I", 0, {})]
    fixed = fix_multi_work_refs(chunks, "Anselm")
    assert fixed[0][1] == "Anselm — Proslogium, Chapter I"


def test_fix_multi_work_refs_preserves_positions():
    """Position values are passed through unchanged."""
    chunks = [("a", "Work — Ch I", 5, {}), ("b", "Work — Ch II", 6, {})]
    fixed = fix_multi_work_refs(chunks, "Author")
    assert fixed[0][2] == 5
    assert fixed[1][2] == 6


# ── merge_short_chunks ───────────────────────────────────────────────────────

def test_merge_short_chunks_merges_below_min():
    """Two short chunks below min_chars are merged into one."""
    chunks = [
        ("short text A", "Work — Ch I", 0, {"k": "v"}),
        ("short text B", "Work — Ch II", 1, {"k": "v"}),
    ]
    result = merge_short_chunks(chunks, min_chars=100, ceiling=3500)
    assert len(result) == 1
    assert "short text A" in result[0][0]
    assert "short text B" in result[0][0]
    assert result[0][2] == 0  # position reset to 0


def test_merge_short_chunks_does_not_merge_above_min():
    """A chunk at or above min_chars is emitted as-is."""
    long_content = "x" * 500
    chunks = [
        (long_content, "Work — Ch I", 0, {}),
        ("short", "Work — Ch II", 1, {}),
    ]
    result = merge_short_chunks(chunks, min_chars=400, ceiling=3500)
    # First chunk should be separate; short chunk goes into next group
    assert result[0][0] == long_content


def test_merge_short_chunks_respects_ceiling():
    """Accumulated content never exceeds ceiling before flushing."""
    big_content = "x" * 1800
    chunks = [(big_content, f"Work — Ch {i}", i, {}) for i in range(3)]
    result = merge_short_chunks(chunks, min_chars=400, ceiling=3500)
    for content, _, _, _ in result:
        assert len(content) <= 3500 + 200  # allow slight overshoot from joining


def test_merge_short_chunks_reassigns_positions_sequentially():
    """Output positions are 0, 1, 2... regardless of input positions."""
    chunks = [("x" * 50, f"W — Ch {i}", i * 10, {}) for i in range(4)]
    result = merge_short_chunks(chunks, min_chars=300, ceiling=3500)
    positions = [pos for _, _, pos, _ in result]
    assert positions == list(range(len(positions)))
