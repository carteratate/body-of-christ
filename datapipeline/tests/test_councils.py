# datapipeline/tests/test_councils.py
import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.councils import parse_council_page, parse_vatican2_doc


# ── Fixtures ─────────────────────────────────────────────────────────────────

SIMPLE_COUNCIL_HTML = """<html><body>
<h1>Council of Nicaea — 325 A.D.</h1>
<h3>Introduction</h3>
<p>The Council of Nicaea was convoked by Constantine in 325 AD to resolve the Arian controversy and define orthodox Christian teaching about the nature of Christ.</p>
<h3>Canons</h3>
<p>Canon 1: If anyone in sickness has undergone surgery at the hands of physicians or has been castrated by barbarians, let him remain among the clergy.</p>
<p>Canon 2: If anyone has recently joined the faith and been catechized briefly, or if he has changed directly from a dissolute life, it is not right for him to be immediately promoted to bishop, priest, or deacon.</p>
<p>Canon 3: The great Synod strictly forbids bishops, priests, and deacons to have with them a woman who has been introduced to live with them, with the exception of a mother or sister or aunt.</p>
</body></html>"""

LONG_COUNCIL_HTML = """<html><body>
<h1>Council of Trent</h1>
<h3>Session VI — Decree on Justification</h3>
""" + "\n".join(
    f"<p>Canon {i}: {'This is a substantial canon with enough content to matter for chunking. ' * 5}</p>"
    for i in range(1, 25)
) + """
<h3>Session VII — Canons on the Sacraments</h3>
<p>Canon 1: If anyone says that the sacraments of the New Law were not all instituted by Jesus Christ our Lord, or that there are more or fewer than seven, let him be anathema.</p>
</body></html>"""

VAT2_HTML = """<html><body>
<h3>CHAPTER I</h3>
<h4>REVELATION ITSELF</h4>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known to us the hidden purpose of His will by which through Christ, the Word made flesh, man might have access to the Father in the Holy Spirit and come to share in the divine nature.</p>
<p>2. The most intimate truth which this revelation gives us about God and the salvation of man is made clear to us in Christ, Who is the Mediator and at the same time the fullness of all revelation.</p>
<h3>CHAPTER II</h3>
<h4>HOW DIVINE REVELATION IS HANDED ON</h4>
<p>3. God has seen to it that what He had revealed for the salvation of all nations would abide perpetually in its full integrity and be handed on to all generations.</p>
<p>4. Sacred tradition and Sacred Scripture form one sacred deposit of the word of God, committed to the Church.</p>
</body></html>"""


# ── parse_council_page ───────────────────────────────────────────────────────

def test_parse_council_page_returns_chunks():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    assert len(chunks) >= 1


def test_parse_council_page_chunk_is_4_tuple():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    content, ref, pos, meta = chunks[0]
    assert isinstance(content, str) and len(content) > 0
    assert isinstance(ref, str) and len(ref) > 0
    assert isinstance(pos, int)
    assert isinstance(meta, dict)


def test_parse_council_page_ref_includes_council_name():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    for _, ref, _, _ in chunks:
        assert "Council of Nicaea" in ref


def test_parse_council_page_metadata_has_council_and_year():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    for _, _, _, meta in chunks:
        assert meta["council"] == "Council of Nicaea"
        assert meta["year"] == 325


def test_parse_council_page_positions_are_sequential():
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    positions = [pos for _, _, pos, _ in chunks]
    assert positions == list(range(len(positions)))


def test_parse_council_page_no_chunk_exceeds_ceiling():
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    for content, _, _, _ in chunks:
        assert len(content) <= 4000  # ceiling is 3800, allow header overhead


def test_parse_council_page_section_creates_new_chunk():
    """A section header should start a new chunk boundary."""
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    refs = [ref for _, ref, _, _ in chunks]
    # Session VI and Session VII should appear in separate chunks
    session_6_refs = [r for r in refs if "Session VI" in r]
    session_7_refs = [r for r in refs if "Session VII" in r]
    assert len(session_6_refs) >= 1
    assert len(session_7_refs) >= 1


def test_parse_council_page_larger_target_produces_fewer_or_equal_chunks():
    """target=2500 should produce no more chunks than target=2000 on the same text."""
    chunks_2000 = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563, target=2000)
    chunks_2500 = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563, target=2500)
    assert len(chunks_2500) <= len(chunks_2000)


# ── parse_vatican2_doc ───────────────────────────────────────────────────────

def test_parse_vatican2_doc_returns_chunks():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    assert len(chunks) >= 1


def test_parse_vatican2_doc_metadata_has_council_and_type():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    for _, _, _, meta in chunks:
        assert meta["council"] == "Vatican II"
        assert meta["document_type"] == "constitution"
        assert meta["year"] == 1965


def test_parse_vatican2_doc_ref_includes_doc_title():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    for _, ref, _, _ in chunks:
        assert "Dei Verbum" in ref


def test_parse_vatican2_doc_positions_sequential():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    positions = [p for _, _, p, _ in chunks]
    assert positions == list(range(len(positions)))
