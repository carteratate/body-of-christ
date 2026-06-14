from normalize.footnotes import strip_footnote_markers


def test_strips_inline_endnote_anchors():
    assert strip_footnote_markers("on the condition of the working classes.[1] It is") \
        == "on the condition of the working classes. It is"


def test_strips_after_quote():
    assert strip_footnote_markers('became poor”;[18] and who') == 'became poor”; and who'


def test_leaves_text_without_markers():
    assert strip_footnote_markers("no markers here") == "no markers here"
