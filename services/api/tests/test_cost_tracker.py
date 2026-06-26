import pytest
from app.rag.steps.cost_tracker import CostTracker


def test_record_anthropic_accumulates_cost():
    t = CostTracker()
    # claude-haiku-4-5: $0.80/MTok in, $4.00/MTok out
    t.record("rerank", "claude-haiku-4-5", input_tokens=1000, output_tokens=500)
    breakdown = t.breakdown()
    assert "rerank" in breakdown
    assert abs(breakdown["rerank"] - (1000 * 0.80 / 1_000_000 + 500 * 4.00 / 1_000_000)) < 1e-9


def test_record_cohere_accumulates_cost():
    t = CostTracker()
    # Cohere Rerank v3: $0.001 per search unit (document)
    t.record_cohere("rerank_cohere", search_units=12)
    breakdown = t.breakdown()
    assert abs(breakdown["rerank_cohere"] - 12 * 0.001) < 1e-9


def test_total_cost_sums_breakdown():
    t = CostTracker()
    t.record("hyde", "claude-haiku-4-5", input_tokens=500, output_tokens=300)
    t.record_cohere("rerank", search_units=8)
    assert abs(t.total_cost() - sum(t.breakdown().values())) < 1e-9


def test_multiple_records_same_step_accumulate():
    t = CostTracker()
    t.record("hyde", "claude-haiku-4-5", input_tokens=100, output_tokens=100)
    t.record("hyde", "claude-haiku-4-5", input_tokens=100, output_tokens=100)
    assert len(t.breakdown()) == 1  # same step key
    assert t.breakdown()["hyde"] > 0
