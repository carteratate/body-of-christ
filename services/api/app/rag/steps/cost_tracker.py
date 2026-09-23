import logging

logger = logging.getLogger(__name__)

# Pricing is part of an evaluation's methodology, not just an implementation
# detail. Keep the effective date with the rates so persisted test artifacts can
# state which schedule produced their cost figures. Every rate below was re-checked
# against the provider's own pricing page on this date; bump it only after doing
# the same for all of them, not just the model being added.
PRICING_EFFECTIVE_DATE = "2026-09-23"

# Pricing: (input $/MTok, output $/MTok)
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    # Judge model. Verified against the Models API 2026-07-25: 1M context,
    # 128K max output. Thinking is ON by default on Opus 5, and thinking tokens
    # bill as output — so a judge run costs more than the input/output split alone
    # suggests unless thinking is explicitly disabled.
    "claude-opus-5": (5.00, 25.00),
    # Judge model from 2026-09-23. Forced tool_choice is a 400 on 5.5, so the judge
    # uses structured outputs (compare/judge.py).
    "claude-opus-5-5": (4.00, 20.00),
}
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "text-embedding-3-large": (0.13, 0.0),
    # Was (0.15, 0.60) from June to 2026-09-23 — gpt-4o-mini's rates — which
    # under-reported every explanation ~5.3x. Kept for the EXPLAIN_OPENAI_MODEL
    # rollback path.
    "gpt-5.4-mini": (0.75, 4.50),
    # Production HyDE / genre pick / listwise reranker. Reasoning tokens bill as
    # output (the reranker runs at "medium", so roughly 60% of its output is reasoning).
    "gpt-5.6-luna": (0.20, 1.20),
    # Explanations, and the gpt-6 evaluation arms. Short-context rates; >272K input
    # tokens bills 2x input / 1.5x output, which no pipeline call approaches.
    "gpt-6-luna": (0.10, 0.50),
}
# rerank-v4.0-pro: $2.50 per 1K search units. A search unit is one query plus up
# to 100 documents; any document over 500 tokens (including the query) is split
# into chunks that each count toward that 100. So a single call can bill several
# units — never assume one call is one unit.
_COHERE_PER_SEARCH_UNIT = 0.0025


def pricing_snapshot() -> dict:
    """Return the exact rates used for cost estimates in JSON-safe form."""
    models = {**_ANTHROPIC_PRICING, **_OPENAI_PRICING}
    return {
        "effective_date": PRICING_EFFECTIVE_DATE,
        "currency": "USD",
        "token_rates_per_million": {
            model: {"input": rates[0], "output": rates[1]}
            for model, rates in sorted(models.items())
        },
        "cohere_rerank_per_search_unit": _COHERE_PER_SEARCH_UNIT,
    }


class CostTracker:
    def __init__(self) -> None:
        self._breakdown: dict[str, float] = {}
        self._cost_eligible = True

    def record(self, step: str, model: str, input_tokens: int, output_tokens: int) -> None:
        pricing = {**_ANTHROPIC_PRICING, **_OPENAI_PRICING}
        if model not in pricing:
            # Silently pricing an unknown model at $0 makes a typo'd model id look
            # free, which is worse than a noisy log during a cost comparison.
            logger.warning(
                "cost_tracker: no pricing for model %r (step=%s) — cost unavailable",
                model, step,
            )
            self._cost_eligible = False
        in_price, out_price = pricing.get(model, (0.0, 0.0))
        cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
        self._breakdown[step] = self._breakdown.get(step, 0.0) + cost

    def record_cohere(self, step: str, search_units: int = 1) -> None:
        """Record Cohere rerank cost from the response's billed search units.

        `search_units` should come from `response.meta.billed_units.search_units`.
        It defaults to 1 for callers that predate per-collection fan-out; with
        several calls per query, defaulting would under-report, so pass the real
        value wherever it is available.
        """
        self._breakdown[step] = (
            self._breakdown.get(step, 0.0) + _COHERE_PER_SEARCH_UNIT * search_units
        )

    def total_cost(self) -> float:
        return sum(self._breakdown.values())

    def breakdown(self) -> dict[str, float]:
        return dict(self._breakdown)

    @property
    def cost_eligible(self) -> bool:
        """Whether every billed model had a trustworthy pricing rate."""
        return self._cost_eligible
