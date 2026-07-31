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


def test_record_cohere_scales_with_billed_search_units():
    """10 per-collection calls must not report the same cost as one global call."""
    t = CostTracker()
    for _ in range(10):
        t.record_cohere("rerank_cohere", 1)
    assert t.breakdown()["rerank_cohere"] == pytest.approx(10 * 0.0025)


def test_record_cohere_multi_unit_call_bills_per_unit():
    t = CostTracker()
    t.record_cohere("rerank_cohere", 3)
    assert t.breakdown()["rerank_cohere"] == pytest.approx(3 * 0.0025)


def test_record_cohere_defaults_to_one_unit_for_legacy_callers():
    t = CostTracker()
    t.record_cohere("rerank_cohere")
    assert t.breakdown()["rerank_cohere"] == pytest.approx(0.0025)


def test_unknown_model_warns_rather_than_silently_costing_zero(caplog):
    t = CostTracker()
    with caplog.at_level("WARNING"):
        t.record("step", "gpt-nonexistent-9", input_tokens=1000, output_tokens=100)
    assert t.total_cost() == 0.0
    assert "no pricing for model" in caplog.text


def test_luna_is_priced():
    t = CostTracker()
    t.record("rerank", "gpt-5.6-luna", input_tokens=1_000_000, output_tokens=1_000_000)
    assert t.breakdown()["rerank"] == pytest.approx(1.00 + 6.00)
