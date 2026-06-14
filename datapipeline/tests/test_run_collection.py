from run_collection import BUILDERS


def test_builders_registered():
    assert set(BUILDERS) >= {"bible", "catechism", "church-fathers", "summa"}
    assert callable(BUILDERS["church-fathers"])
