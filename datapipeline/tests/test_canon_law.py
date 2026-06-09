import sys, os

# Set required env vars before importing ingest.canon_law, which imports load → config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.canon_law import parse_canon_page, deduplicate_urls

SAMPLE_HTML = """<html><body><table><tbody><tr><td>
<p align="center"><b>CODE OF CANON LAW</b></p>
<p>Can. 1 The canons of this Code regard only the Latin Church.</p>
<p>Can. 2 For the most part the Code does not define the rites which must be observed.</p>
<p>Can. 5 §1. Universal or particular customs presently in force which are contrary to the prescripts.</p>
<p>§2. Universal or particular customs beyond the law are preserved.</p>
<p>Can. 6 §1. When this Code takes force, the following are abrogated:</p>
<p>1/ the Code of Canon Law promulgated in 1917;</p>
<p>2/ other universal or particular laws contrary to the prescripts;</p>
</td></tr></tbody></table></body></html>"""

def test_parse_canon_page_extracts_canons():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4  # Can. 1, 2, 5, 6

def test_parse_canon_strips_can_prefix():
    canons = parse_canon_page(SAMPLE_HTML)
    num, text, _ = canons[0]
    assert num == 1
    assert not text.startswith("Can.")
    assert text.startswith("The canons")

def test_parse_canon_appends_subparagraphs():
    canons = parse_canon_page(SAMPLE_HTML)
    can5 = next(c for c in canons if c[0] == 5)
    assert "§1." in can5[1]
    assert "§2." in can5[1]

def test_parse_canon_appends_numbered_items():
    canons = parse_canon_page(SAMPLE_HTML)
    can6 = next(c for c in canons if c[0] == 6)
    assert "1/" in can6[1]
    assert "2/" in can6[1]

def test_parse_canon_skips_headers():
    canons = parse_canon_page(SAMPLE_HTML)
    texts = [c[1] for c in canons]
    assert not any("CODE OF CANON LAW" in t for t in texts)

def test_deduplicate_urls_strips_fragments():
    urls = [
        "/archive/cic_lib1-cann1-6_en.html",
        "/archive/cic_lib1-cann1-6_en.html#Art._1.",
        "/archive/cic_lib1-cann1-6_en.html#Art._2.",
        "/archive/cic_lib1-cann7-22_en.html",
    ]
    result = deduplicate_urls(urls, base="http://www.vatican.va")
    assert len(result) == 2
    assert "http://www.vatican.va/archive/cic_lib1-cann1-6_en.html" in result
    assert "http://www.vatican.va/archive/cic_lib1-cann7-22_en.html" in result


HIERARCHY_HTML = """<html><body><table><tbody><tr><td>
<p>BOOK II. THE PEOPLE OF GOD</p>
<p>TITLE I. THE OBLIGATIONS AND RIGHTS OF ALL THE CHRISTIAN FAITHFUL</p>
<p>Can. 208 In virtue of their rebirth in Christ, there exists among all the Christian faithful a true equality.</p>
<p>Can. 209 §1. The Christian faithful, even in their own manner of acting, are always obliged to maintain communion with the Church.</p>
<p>§2. With great diligence they are to lead a holy life.</p>
<p>CHAPTER I. OBLIGATIONS AND RIGHTS OF THE CHRISTIAN FAITHFUL</p>
<p>Can. 210 All the faithful must direct their efforts to lead a holy life.</p>
</td></tr></tbody></table></body></html>"""


def test_parse_canon_page_returns_3_tuple():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4
    num, text, ctx = canons[0]
    assert isinstance(num, int)
    assert isinstance(text, str)
    assert isinstance(ctx, dict)


def test_parse_canon_page_context_has_required_keys():
    canons = parse_canon_page(SAMPLE_HTML)
    _, _, ctx = canons[0]
    assert "book" in ctx
    assert "part" in ctx
    assert "title" in ctx
    assert "chapter" in ctx
    assert "article" in ctx


def test_parse_canon_header_updates_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    assert "BOOK II" in ctx["book"] or "THE PEOPLE OF GOD" in ctx["book"]
    assert "TITLE I" in ctx["title"] or "OBLIGATIONS" in ctx["title"]


def test_parse_canon_chapter_header_updates_chapter_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    can210 = next(c for c in canons if c[0] == 210)
    ctx = can210[2]
    assert ctx["chapter"] != ""


def test_parse_canon_header_resets_lower_levels():
    """When a TITLE header appears, chapter and article must reset to ''."""
    canons = parse_canon_page(HIERARCHY_HTML)
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    assert ctx["chapter"] == ""
    assert ctx["article"] == ""
