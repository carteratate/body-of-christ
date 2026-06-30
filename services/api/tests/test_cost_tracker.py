import pytest
from app.rag.steps.cost_tracker import CostTracker


def test_record_anthropic_accumulates_cost():
    t = CostTracker()
    # claude-haiku-4-5: $1.00/MTok in, $5.00/MTok out
    t.record("rerank", "claude-haiku-4-5", input_tokens=1000, output_tokens=500)
    breakdown = t.breakdown()
    assert "rerank" in breakdown
    assert abs(breakdown["rerank"] - (1000 * 1.00 / 1_000_000 + 500 * 5.00 / 1_000_000)) < 1e-9


def test_record_cohere_accumulates_cost():
    t = CostTracker()
    # Cohere Rerank v4.0 Pro: $2.50/1K searches = $0.0025 per API call
    t.record_cohere("rerank_cohere")
    breakdown = t.breakdown()
    assert abs(breakdown["rerank_cohere"] - 0.0025) < 1e-9


def test_total_cost_sums_breakdown():
    t = CostTracker()
    t.record("hyde", "claude-haiku-4-5", input_tokens=500, output_tokens=300)
    t.record_cohere("rerank")
    assert abs(t.total_cost() - sum(t.breakdown().values())) < 1e-9


def test_multiple_records_same_step_accumulate():
    t = CostTracker()
    t.record("hyde", "claude-haiku-4-5", input_tokens=100, output_tokens=100)
    t.record("hyde", "claude-haiku-4-5", input_tokens=100, output_tokens=100)
    assert len(t.breakdown()) == 1  # same step key
    assert t.breakdown()["hyde"] > 0
