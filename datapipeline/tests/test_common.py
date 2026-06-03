import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.common import parse_thml_string, ThmlDocument

STANDARD_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>augustine</authorID>
      <bookID>confess</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>The Confessions of Saint Augustine</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Augustine, Saint, Bishop of Hippo (345-430)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="Book I" n="i" id="bk1">
      <div2 title="Chapter I" n="i" id="bk1.ch1">
        <p id="p1">Great art Thou, O Lord, and greatly to be praised; great is Thy power, and Thy wisdom infinite. And Thee would man praise; man, but a particle of Thy creation.</p>
        <p id="p2">And Thee would man praise; he, but a particle of Thy creation. Thou awakest us to delight in Thy praise.</p>
      </div2>
      <div2 title="Chapter II" n="ii" id="bk1.ch2">
        <p id="p3">And how shall I call upon my God, my God and Lord, since, when I call for Him, I shall be calling Him to myself? and what room is there within me, whither my God can come into me?</p>
      </div2>
    </div1>
    <div1 title="Book II" n="ii" id="bk2">
      <div2 title="Chapter I" n="i" id="bk2.ch1">
        <p id="p4">I will now call to mind my past foulness, and the carnal corruptions of my soul; not because I love them, but that I may love Thee, O my God.</p>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

SUMMA_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>aquinas</authorID>
      <bookID>summa</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>Summa Theologica</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Thomas Aquinas, Saint (1225?-1274)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="First Part" n="i" id="FP">
      <div2 title="Treatise on Sacred Doctrine" n="i" id="FP.i">
        <div3 title="Question 1" n="i" id="FP_Q1">
          <div4 title="Article 1 - Whether sacred doctrine is necessary?" n="i" id="FP_Q1_A1">
            <p id="a1p1">Objection 1: It seems that it is not necessary.</p>
            <p id="a1p2">On the contrary, It is written: Instruction in every gracious art.</p>
            <p id="a1p3">I answer that, It was necessary for man salvation that there should be a knowledge revealed by God.</p>
            <p id="a1p4">Reply to Objection 1: Sciences are differentiated according to the various means through which knowledge is obtained.</p>
          </div4>
          <div4 title="Article 2 - Whether sacred doctrine is a science?" n="ii" id="FP_Q1_A2">
            <p id="a2p1">Objection 1: It seems that sacred doctrine is not a science.</p>
            <p id="a2p2">I answer that, Sacred doctrine is a science because it proceeds from principles established by the light of a higher science.</p>
          </div4>
        </div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""


def test_parse_thml_title():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.title == "The Confessions of Saint Augustine"

def test_parse_thml_author_cleaned():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.author == "Augustine, Saint, Bishop of Hippo"

def test_parse_thml_year_from_death():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.year == 430

def test_parse_thml_standard_chunks_by_chapter():
    doc = parse_thml_string(STANDARD_THML)
    assert len(doc.chunks) == 3  # Book I Ch I, Book I Ch II, Book II Ch I

def test_parse_thml_chapter_content_joined():
    doc = parse_thml_string(STANDARD_THML)
    content, ref, pos = doc.chunks[0]
    assert "Great art Thou" in content
    assert "Thee would man praise" in content  # both paragraphs merged

def test_parse_thml_reference_format():
    doc = parse_thml_string(STANDARD_THML)
    _, ref0, _ = doc.chunks[0]
    _, ref1, _ = doc.chunks[1]
    assert ref0 == "Book I, Chapter I"
    assert ref1 == "Book I, Chapter II"

def test_parse_thml_positions_sequential():
    doc = parse_thml_string(STANDARD_THML)
    positions = [c[2] for c in doc.chunks]
    assert positions == list(range(len(doc.chunks)))

def test_parse_thml_strips_xml_tags():
    thml = STANDARD_THML.replace('<p id="p1">', '<p id="p1"><i>Great</i> art Thou,')
    doc = parse_thml_string(thml)
    assert "<i>" not in doc.chunks[0][0]

def test_parse_thml_summa_chunks_at_article():
    doc = parse_thml_string(SUMMA_THML)
    assert len(doc.chunks) == 2  # 2 articles

def test_parse_thml_summa_reference_format():
    doc = parse_thml_string(SUMMA_THML)
    _, ref0, _ = doc.chunks[0]
    assert "Article 1" in ref0
    assert "Question 1" in ref0

def test_parse_thml_summa_article_content_complete():
    doc = parse_thml_string(SUMMA_THML)
    content, _, _ = doc.chunks[0]
    assert "Objection 1" in content
    assert "I answer that" in content
    assert "Reply to Objection" in content

def test_parse_thml_skips_short_chapters():
    # Chapter with < 100 chars of text should be skipped
    short_thml = STANDARD_THML.replace(
        '<p id="p3">And how shall I call upon my God, my God and Lord, since, when I call for Him, I shall be calling Him to myself? and what room is there within me, whither my God can come into me?</p>',
        '<p id="p3">Short.</p>'
    )
    doc = parse_thml_string(short_thml)
    refs = [c[1] for c in doc.chunks]
    assert "Book I, Chapter II" not in refs

def test_parse_author_handles_approximate_dates():
    from ingest.common import _parse_author
    author, year = _parse_author("Athanasius, St. Archbishop of Alexandria (c.296-c.373)")
    assert year == 373
    assert "c.296" not in author
    assert "(c.296-c.373)" not in author

def test_chunk_standard_falls_back_to_div1_when_no_div2():
    thml = """<?xml version="1.0"?>
<ThML>
  <ThML.head>
    <electronicEdInfo><authorID>athanasius</authorID><bookID>incarnation</bookID></electronicEdInfo>
    <DC><DC.Title>On the Incarnation</DC.Title></DC>
  </ThML.head>
  <ThML.body>
    <div1 title="Chapter I" n="i" id="ch1">
      <p id="p1">The Word of God, incorporeal and incorruptible and immaterial, came into our world. He was not previously distant from it, for no part of creation had ever been without Him.</p>
      <p id="p2">He enters the world in a new way, stooping to our level in his love and self-revealing to us. He saw the reasonable race perishing and death reigning over them.</p>
    </div1>
    <div1 title="Chapter II" n="ii" id="ch2">
      <p id="p3">Let us then consider this matter from the beginning, taking up the discussion with reference to the origin of the universe and its maker, God.</p>
    </div1>
  </ThML.body>
</ThML>"""
    from ingest.common import parse_thml_string
    doc = parse_thml_string(thml)
    assert len(doc.chunks) == 2
    assert doc.chunks[0][1] == "Chapter I"
    assert doc.chunks[1][1] == "Chapter II"
    assert "Word of God" in doc.chunks[0][0]
