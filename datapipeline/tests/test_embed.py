import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from embed import make_batches, vec_to_pg

def test_make_batches_splits_correctly():
    items = list(range(250))
    batches = list(make_batches(items, 100))
    assert len(batches) == 3
    assert len(batches[0]) == 100
    assert len(batches[1]) == 100
    assert len(batches[2]) == 50

def test_make_batches_single_item():
    batches = list(make_batches([42], 100))
    assert len(batches) == 1
    assert batches[0] == [42]

def test_make_batches_empty():
    batches = list(make_batches([], 100))
    assert batches == []

def test_vec_to_pg_formats_correctly():
    vec = [0.1, -0.2, 0.3]
    result = vec_to_pg(vec)
    assert result == "[0.1,-0.2,0.3]"

def test_vec_to_pg_handles_integers():
    vec = [1, 0, -1]
    result = vec_to_pg(vec)
    assert result.startswith("[")
    assert result.endswith("]")
