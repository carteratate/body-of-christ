import sys, os

# Set required env vars before importing ingest.bible, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.bible import parse_cpdv_json, parse_douay_rheims, chunk_book, _make_reference, BookVerses, Verse

def test_read_dr_from_local_file():
    """parse_douay_rheims should correctly parse the DR plain-text format."""
    sample = (
        "*** START OF THIS PROJECT GUTENBERG EBOOK ***\n"
        "Genesis Chapter 1\n"
        "\n"
        "1:1. In the beginning God created heaven and earth.\n"
        "\n"
        "*** END OF THIS PROJECT GUTENBERG EBOOK ***\n"
    )
    books = parse_douay_rheims(sample)
    assert len(books) == 1
    assert books[0].name == "Genesis"
    assert books[0].verses[0].text == "In the beginning God created heaven and earth."

def test_parse_cpdv_extracts_books():
    data = {
        "charset": "UTF-8",
        "Genesis": {"1": {"1": "In the beginning", "2": "The earth was empty"}},
        "Exodus": {"1": {"1": "These are the names"}},
    }
    books = parse_cpdv_json(data)
    assert len(books) == 2
    assert books[0].name == "Genesis"
    assert books[1].name == "Exodus"

def test_parse_cpdv_skips_charset_key():
    data = {"charset": "UTF-8", "Genesis": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    assert len(books) == 1

def test_parse_cpdv_extracts_verses():
    data = {"Genesis": {"1": {"1": "verse one", "2": "verse two", "3": "verse three"}}}
    books = parse_cpdv_json(data)
    assert len(books[0].verses) == 3
    assert books[0].verses[0].text == "verse one"
    assert books[0].verses[0].chapter == 1
    assert books[0].verses[0].verse == 1

def test_parse_cpdv_assigns_testament():
    data = {"Genesis": {"1": {"1": "text"}}, "Matthew": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    by_name = {b.name: b for b in books}
    assert by_name["Genesis"].testament == "OT"
    assert by_name["Matthew"].testament == "NT"

def test_parse_cpdv_skips_unknown_books():
    data = {"UnknownBook": {"1": {"1": "text"}}, "Genesis": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    assert len(books) == 1
    assert books[0].name == "Genesis"

def test_chunk_book_groups_four_verses():
    verses = [Verse("Genesis", 1, i, f"Verse {i} text here") for i in range(1, 9)]
    book = BookVerses("Genesis", "", "OT", verses)
    chunks = list(chunk_book(book, 4, 10))
    assert len(chunks) == 2
    content0, ref0, pos0 = chunks[0]
    assert ref0 == "Genesis 1:1-4"
    assert pos0 == 0
    assert "Verse 1" in content0

def test_chunk_book_never_crosses_chapters():
    ch1 = [Verse("Gen", 1, i, f"ch1 v{i}") for i in range(1, 4)]
    ch2 = [Verse("Gen", 2, i, f"ch2 v{i}") for i in range(1, 4)]
    book = BookVerses("Gen", "", "OT", ch1 + ch2)
    chunks = list(chunk_book(book, 4, 5))
    refs = [c[1] for c in chunks]
    assert all("1:" not in r or "2:" not in r for r in refs)

def test_chunk_book_skips_short_content():
    verses = [Verse("Gen", 1, 1, "hi")]
    book = BookVerses("Gen", "", "OT", verses)
    chunks = list(chunk_book(book, 4, 50))
    assert len(chunks) == 0

def test_parse_cpdv_sorts_verses_within_chapter():
    data = {"Genesis": {"1": {"3": "third verse", "1": "first verse", "2": "second verse"}}}
    books = parse_cpdv_json(data)
    verses = books[0].verses
    assert verses[0].verse == 1
    assert verses[0].text == "first verse"
    assert verses[1].verse == 2
    assert verses[1].text == "second verse"
    assert verses[2].verse == 3
    assert verses[2].text == "third verse"
