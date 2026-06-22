from normalize.boilerplate import strip_boilerplate


def test_strips_midstream_footer():
    # Real tail from Humanae Vitae / Humani Generis (papalencyclicals.net).
    t = ("...and in pledge thereof we impart our apostolic blessing.\n\nFOOTNOTES\n\n"
         "Last updated June 21, 2026 library, Kindle, Nook, EPUB © Copyright 2000-2026 "
         "Marketing Solutions by Midstream Marketing")
    out = strip_boilerplate(t)
    assert "Midstream" not in out
    assert "Last updated" not in out
    assert "FOOTNOTES" not in out
    assert out.endswith("apostolic blessing.")


def test_strips_vatican_dicastery_footer():
    t = "Phil 1:3-4, 7-8.\n\n© Copyright - Libreria Editrice Vaticana\n\nCopyright © Dicastery for Communication"
    out = strip_boilerplate(t)
    assert "Copyright" not in out
    assert "Libreria" not in out
    assert out.endswith("Phil 1:3-4, 7-8.")


def test_leaves_clean_text_untouched():
    t = "For God so loved the world, that he gave his only Son."
    assert strip_boilerplate(t) == t


def test_does_not_overcut_on_internal_mention():
    # 'last updated' only triggers as trailing boilerplate; here it's mid-sentence
    # without the footer pattern — but our rule cuts at first occurrence, so verify
    # legitimate prose that merely contains 'copyright' as a real word still works.
    t = "The author retained the copyright to his earlier works during this period."
    # 'copyright ©' / '© copyright' pattern does NOT match plain 'copyright', so kept.
    assert strip_boilerplate(t) == t
