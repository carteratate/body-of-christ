import sys, os

# Set required env vars before importing ingest.encyclicals, which imports load → config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.encyclicals import parse_encyclical_paragraphs, group_paragraphs

SAMPLE_HTML_PPN = """<html><body>
<p>To Our Venerable Brethren... [intro not numbered]</p>
<p>1. That the spirit of revolutionary change, which has long been disturbing the nations of the world, should have passed beyond the sphere of politics.</p>
<p>2. It is not surprising that, with the growth of new industries settling in new lands, and with the surge of new economic forces.</p>
<p>3. To remedy these wrongs the socialists, working on the poor man's envy of the rich, are striving to do away with private property.</p>
<p>4. But all agree, and there can be no question whatever, that some remedy must be found, and found quickly.</p>
<p>5. We approach the subject with confidence, and in the exercise of the rights which manifestly appertain to Us.</p>
</body></html>"""

def test_parse_encyclical_extracts_numbered_paragraphs():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert len(paras) == 5
    assert paras[0][0] == 1
    assert "revolutionary change" in paras[0][1]

def test_parse_encyclical_skips_unnumbered_intro():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert all(p[0] is not None for p in paras)

def test_group_paragraphs_groups_three():
    paras = [(i, f"content of paragraph {i} " * 10) for i in range(1, 6)]
    groups = group_paragraphs(paras, chunk_size=3)
    assert len(groups) == 2
    content0, ref0, pos0 = groups[0]
    assert "§1-3" in ref0
    assert pos0 == 0
    content1, ref1, pos1 = groups[1]
    assert "§4-5" in ref1
    assert pos1 == 1

def test_group_paragraphs_skips_short():
    paras = [(1, "short"), (2, "x" * 100), (3, "x" * 100), (4, "x" * 100)]
    groups = group_paragraphs(paras, chunk_size=3, min_length=50)
    # §1 skipped, remaining 3 form one group
    assert len(groups) == 1

def test_parse_encyclical_strips_number_prefix():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert not paras[0][1].startswith("1.")
    assert "revolutionary change" in paras[0][1]
