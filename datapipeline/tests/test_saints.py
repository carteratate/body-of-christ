import sys, os

# Set required env vars before importing ingest.saints, which imports load → config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.saints import filter_saint_links, parse_saint_article, chunk_text

SAMPLE_INDEX = """<html><body>
<a href="13794a.htm">Francis of Assisi, Saint</a>
<a href="02050a.htm">Thomas Aquinas, Saint</a>
<a href="01015a.htm">Blessed Margaret of Castello</a>
<a href="01016a.htm">Architecture</a>
<a href="07654a.htm">St. Augustine of Hippo</a>
<a href="09999a.htm">Canon Law</a>
<a href="00001a.htm">Venerable Bede</a>
</body></html>"""

BASE = "https://www.newadvent.org/cathen/"

SAMPLE_ARTICLE = """<html><body>
<h1>Francis of Assisi, Saint</h1>
<div id="bodycontents">
<p>Francis of Assisi was born in 1181 or 1182 to Pietro di Bernardone, a prosperous cloth merchant.</p>
<p>As a young man, Francis participated in Assisi's social life and looked forward to a career as a knight.</p>
<p>After being captured in a battle between Assisi and Perugia in 1202, Francis was held for ransom for about a year.</p>
<p>In 1205 Francis had the famous mystical experience in the ruined church of San Damiano near Assisi, in which Christ on the Crucifix spoke to him: "Francis, go and repair my Church."</p>
<p>Francis devoted himself to a life of poverty, preaching, and care for the poor and sick, especially lepers.</p>
<p>He founded the Order of Friars Minor, commonly called the Franciscans, in 1209.</p>
</div>
</body></html>"""

def test_filter_finds_saints():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    titles = [t for _, t in links]
    assert "Francis of Assisi, Saint" in titles
    assert "Thomas Aquinas, Saint" in titles
    assert "St. Augustine of Hippo" in titles
    assert "Blessed Margaret of Castello" in titles
    assert "Venerable Bede" in titles

def test_filter_excludes_non_saints():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    titles = [t for _, t in links]
    assert "Architecture" not in titles
    assert "Canon Law" not in titles

def test_filter_builds_absolute_urls():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    urls = [u for u, _ in links]
    assert all(u.startswith("https://") for u in urls)
    assert f"{BASE}13794a.htm" in urls

def test_parse_saint_article_extracts_text():
    text = parse_saint_article(SAMPLE_ARTICLE)
    assert "Francis of Assisi" in text
    assert "Pietro di Bernardone" in text
    assert len(text) > 100

def test_chunk_text_splits_on_words():
    long_text = " ".join([f"word{i}" for i in range(200)])
    chunks = chunk_text(long_text, max_words=50)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 50 for c in chunks)

def test_chunk_text_no_empty_chunks():
    text = "Hello world."
    chunks = chunk_text(text, max_words=50)
    assert len(chunks) == 1
    assert chunks[0] == "Hello world."
