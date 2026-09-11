import pytest

from app.config import settings
from app.rag.search_plan import SearchPlan, SearchPlanError, resolve_search_plan


@pytest.mark.parametrize("quota", [3, 4, 5])
def test_standard_quota_accepts_one_or_many_collections(quota: int):
    plan = resolve_search_plan(["bible", "catechism"], quota)

    assert plan.collections == ("bible", "catechism")
    assert plan.quota == quota
    assert plan.focused is False
    assert plan.terminal_candidate_budget == settings.llm_pool_global_cap
    assert plan.max_passages_per_document == 2


def test_focused_quota_normalizes_duplicate_collections():
    plan = resolve_search_plan(["bible", "bible"], 10)

    assert plan.collections == ("bible",)
    assert plan.quota == 10
    assert plan.focused is True
    assert plan.terminal_candidate_budget == 25
    assert plan.max_passages_per_document == 4


@pytest.mark.parametrize("quota", [0, 1, 2, 6, 7, 8, 9, 11])
def test_disallowed_quota_has_typed_error(quota: int):
    with pytest.raises(SearchPlanError) as exc_info:
        resolve_search_plan(["bible"], quota)

    assert exc_info.value.code == "invalid_quota"


@pytest.mark.parametrize(
    ("collections", "expected_code"),
    [
        ([], "focused_collection_count"),
        (["missing"], "focused_collection_count"),
        (["bible", "catechism"], "focused_collection_count"),
    ],
)
def test_focused_quota_requires_exactly_one_valid_collection(
    collections: list[str], expected_code: str,
):
    with pytest.raises(SearchPlanError) as exc_info:
        resolve_search_plan(collections, 10)

    assert exc_info.value.code == expected_code


def test_unknown_collections_are_ignored_when_a_valid_collection_remains():
    plan = resolve_search_plan(["missing", "bible", "missing"], 10)

    assert plan.collections == ("bible",)


def test_search_plan_cannot_be_constructed_with_focused_multi_collection_state():
    with pytest.raises(SearchPlanError) as exc_info:
        SearchPlan(collections=("bible", "catechism"), quota=10)

    assert exc_info.value.code == "focused_collection_count"
