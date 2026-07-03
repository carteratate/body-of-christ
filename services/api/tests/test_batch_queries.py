from compare_batch.queries import QUERIES, QuerySpec

VALID_CATEGORIES = {"doctrinal", "ethical", "pastoral", "scriptural", "historical"}


def test_query_count():
    assert len(QUERIES) == 50


def test_all_queries_have_required_fields():
    for q in QUERIES:
        assert isinstance(q, QuerySpec)
        assert q.query and isinstance(q.query, str)
        assert q.category in VALID_CATEGORIES
        assert isinstance(q.expected_collections, list)
        assert len(q.expected_collections) >= 1


def test_no_duplicate_queries():
    texts = [q.query for q in QUERIES]
    assert len(texts) == len(set(texts))


def test_category_distribution():
    from collections import Counter
    counts = Counter(q.category for q in QUERIES)
    for cat in VALID_CATEGORIES:
        assert counts[cat] >= 5, f"Category {cat!r} has only {counts[cat]} queries"
