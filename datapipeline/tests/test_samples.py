import os, json
from samples import SampleWriter
from stages.enrich_io import annotation_prose
from enrichment.schema import MergedEnrichment
from model import Passage


def test_sample_writer_creates_timestamped_file(tmp_path):
    w = SampleWriter("bible", str(tmp_path))
    assert w.path.startswith(str(tmp_path))
    assert "bible-" in os.path.basename(w.path) and w.path.endswith(".jsonl")
    w.write({"chunk_id": "c1"})
    assert json.loads(open(w.path).read().strip())["chunk_id"] == "c1"


def test_preview_contains_facets_and_annotation(tmp_path):
    w = SampleWriter("bible", str(tmp_path))
    merged = MergedEnrichment.model_validate({
        "facets": [{"confidence": "traditional", "kind": "devotional",
                    "text": "Augustine's cry.", "question": "What does he mean?"}],
        "annotation": "SUMMARY: s\n\n[DEVOTIONAL | traditional]: d"})
    p = Passage(content="Late have I loved thee", reference="Confessions X.27",
                anchor="a", chapter_key="k", chapter_label="Book X", position=0)
    out = w.preview(merged, p)
    assert "Confessions X.27" in out
    assert "devotional | traditional" in out
    assert "What does he mean?" in out
    assert "SUMMARY: s" in out


def test_annotation_prose_strips_segment_labels():
    ann = "SUMMARY: overall\n\n[DEVOTIONAL | traditional]: body one\n[DOCTRINAL | explicit]: body two"
    prose = annotation_prose(ann)
    assert "[" not in prose and "|" not in prose
    assert "overall" in prose and "body one" in prose and "body two" in prose
