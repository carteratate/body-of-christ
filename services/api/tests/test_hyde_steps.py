import pytest
from unittest.mock import AsyncMock, patch
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps import hyde_none


@pytest.mark.asyncio
async def test_hyde_none_returns_empty_dict():
    tracker = CostTracker()
    result = await hyde_none.run("what is prayer?", ["bible", "catechism"], tracker)
    assert result == {}
    assert tracker.total_cost() == 0.0


@pytest.mark.asyncio
async def test_hyde_none_makes_no_llm_calls():
    tracker = CostTracker()
    with patch("anthropic.AsyncAnthropic") as mock_client:
        result = await hyde_none.run("test", ["bible"], tracker)
    mock_client.assert_not_called()
    assert result == {}
