import sys, os, re

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.encyclicals import parse_encyclical

# ── Fixtures ─────────────────────────────────────────────────────────────────

SIMPLE_HTML = """<html><body>
<p>To Our Venerable Brethren... greeting and Apostolic Blessing.</p>
<p>1. That the spirit of revolutionary change, which has long been disturbing the nations, should have passed beyond the sphere of politics and made its influence felt in the cognate sphere of practical economics.</p>
<p>2. It is not surprising that, with the growth of new industries settling in new lands, and with the surge of new economic forces, a spirit of strident controversy should have grown up as well.</p>
<p>3. To remedy these wrongs the socialists, working on the poor man's envy of the rich, are striving to do away with private property, and contend that individual possessions should become the common property of all.</p>
<p>4. But all agree, and there can be no question whatever, that some remedy must be found, and found quickly.</p>
<p>5. We approach the subject with confidence, and in the exercise of the rights which manifestly appertain to Us, We make no pretence to deal with the question from an economic point of view.</p>
</body></html>"""

SECTION_HTML = """<html><body>
<p>1. Opening paragraph of the encyclical document with substantial content here.</p>
<p>2. Second paragraph continues the theme and adds more substance to the opening.</p>
<p><b>I. The Rights of Workers</b></p>
<p>3. Every man has by nature the right to possess property as his own and to make use of it for this purpose.</p>
<p>4. It is a most sacred law of nature that a father should provide food and necessities for those whom he has begotten.</p>
<p><b>II. The Role of the State</b></p>
<p>5. The State should not absorb the individual or the family. It is an injustice and a grave evil.</p>
</body></html>"""

LONG_SECTION_HTML = """<html><body>
<p><b>I. Introduction</b></p>
""" + "\n".join(
    f"<p>{i}. {'This is a substantial paragraph with enough content to matter for chunking purposes. ' * 8}</p>"
    for i in range(1, 30)
) + """
</body></html>"""


# ── Basic extraction ─────────────────────────────────────────────────────────

def test_parse_encyclical_returns_chunks():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    assert len(chunks) >= 1


def test_parse_encyclical_chunk_is_4_tuple():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, ref, pos, meta = chunks[0]
    assert isinstance(content, str)
    assert isinstance(ref, str)
    assert isinstance(pos, int)
    assert isinstance(meta, dict)


def test_parse_encyclical_intro_chunk_at_position_0():
    """First chunk should be the overview chunk when a preamble or sections exist."""
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, ref, pos, _ = chunks[0]
    assert pos == 0
    assert "Rerum Novarum" in content
    assert "Overview" in ref


def test_parse_encyclical_intro_includes_preamble():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, _, _, _ = chunks[0]
    assert "Venerable Brethren" in content


def test_parse_encyclical_document_prefix_in_every_chunk():
    """Every non-intro chunk must begin with 'In {Title} ({Author}, {Year})'."""
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body_chunks = [(c, r, p, m) for c, r, p, m in chunks if "Overview" not in r]
    assert body_chunks, "Expected at least one body chunk"
    for content, _, _, _ in body_chunks:
        assert content.startswith("In Rerum Novarum (Pope Leo XIII, 1891)")


def test_parse_encyclical_reference_format():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    ref = body[0][1]
    assert ref.startswith("Rerum Novarum, §")


def test_parse_encyclical_positions_sequential():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    positions = [c[2] for c in chunks]
    assert positions == list(range(len(chunks)))


def test_parse_encyclical_metadata_fields():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    _, _, _, meta = body[0]
    assert meta["year"] == 1891
    assert meta["pope"] == "Pope Leo XIII"
    assert "para_range" in meta
    assert "scripture_refs" in meta
    assert "section" in meta


# ── Section boundaries ───────────────────────────────────────────────────────

def test_parse_encyclical_section_flush():
    """A section header must flush the current chunk before starting a new one."""
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    refs = [c[1] for c in chunks]
    body_refs = [r for r in refs if "Overview" not in r]
    assert len(body_refs) >= 2


def test_parse_encyclical_section_label_in_content():
    """When a section header is active, it appears in the chunk content."""
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    contents = [c[0] for c in body]
    assert any("Rights of Workers" in c for c in contents)


def test_parse_encyclical_section_in_metadata():
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    metas = [c[3] for c in body]
    assert any(m["section"] and "Rights of Workers" in m["section"] for m in metas)


def test_parse_encyclical_intro_lists_sections():
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    intro_content = chunks[0][0]
    assert "Rights of Workers" in intro_content or "Role of the State" in intro_content


# ── Overlap ─────────────────────────────────────────────────────────────────

def test_parse_encyclical_overlap_within_section():
    """When a long section produces multiple chunks, the last para of chunk N
    appears as the first para of chunk N+1 (within same section)."""
    chunks = parse_encyclical(LONG_SECTION_HTML, "Test Doc", "Pope Test", 2024)
    body = [c for c in chunks if "Overview" not in c[1]]
    if len(body) >= 2:
        c0, c1 = body[0][0], body[1][0]
        last_para_of_c0 = [p for p in c0.split("\n\n") if p.strip()][-1]
        assert last_para_of_c0[:50] in c1


# ── Ceiling ──────────────────────────────────────────────────────────────────

def test_parse_encyclical_no_chunk_exceeds_ceiling():
    chunks = parse_encyclical(LONG_SECTION_HTML, "Test Doc", "Pope Test", 2024)
    for content, _, _, _ in chunks:
        assert len(content) <= 3500, f"Chunk exceeds 3500 chars: {len(content)}"
