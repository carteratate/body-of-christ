import sys, os

# Set required env vars before importing ingest.catechism, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.catechism import parse_ccc_paragraphs

SAMPLE_DATA = {
    "page_nodes": {
        "toc-1": {
            "paragraphs": [
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 1},
                        {"type": "text", "text": "God, infinitely perfect and blessed in himself, in a plan of sheer goodness freely created man."},
                        {"type": "ref", "number": 1},
                    ]
                },
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 2},
                        {"type": "text", "text": "The Father willed that his eternal Son should become man and save all men from sin."},
                    ]
                },
            ]
        },
        "toc-2": {
            "paragraphs": [
                {
                    "elements": [
                        {"type": "text", "text": "Section title with no paragraph number"}
                    ]
                },
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 3},
                        {"type": "text", "text": "Short."},
                    ]
                },
            ]
        },
    }
}

def test_parse_ccc_extracts_paragraphs():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    assert len(paras) == 2  # §3 too short, no-ref-ccc skipped

def test_parse_ccc_correct_ref_number():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    assert paras[0][0] == 1
    assert paras[1][0] == 2

def test_parse_ccc_concatenates_text_elements():
    data = {
        "page_nodes": {"t": {"paragraphs": [{
            "elements": [
                {"type": "ref-ccc", "ref_number": 10},
                {"type": "text", "text": "First part. This is a longer text. "},
                {"type": "ref", "number": 5},
                {"type": "text", "text": "Second part. More text here."},
            ]
        }]}}
    }
    paras = parse_ccc_paragraphs(data)
    assert paras[0][1] == "First part. This is a longer text.  Second part. More text here."

def test_parse_ccc_skips_no_ref_ccc():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    para_nums = [p[0] for p in paras]
    assert 3 not in para_nums  # §3 too short

def test_parse_ccc_sorted_by_para_num():
    data = {
        "page_nodes": {
            "b": {"paragraphs": [{"elements": [{"type": "ref-ccc", "ref_number": 20}, {"type": "text", "text": "x" * 40}]}]},
            "a": {"paragraphs": [{"elements": [{"type": "ref-ccc", "ref_number": 5}, {"type": "text", "text": "x" * 40}]}]},
        }
    }
    paras = parse_ccc_paragraphs(data)
    assert paras[0][0] == 5
    assert paras[1][0] == 20
