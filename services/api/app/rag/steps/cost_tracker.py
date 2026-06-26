# Pricing: (input $/MTok, output $/MTok)
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "text-embedding-3-large": (0.13, 0.0),
    "gpt-5.4-mini": (0.15, 0.60),
}
_COHERE_PER_UNIT = 0.001  # per search unit (document)


class CostTracker:
    def __init__(self) -> None:
        self._breakdown: dict[str, float] = {}

    def record(self, step: str, model: str, input_tokens: int, output_tokens: int) -> None:
        pricing = {**_ANTHROPIC_PRICING, **_OPENAI_PRICING}
        in_price, out_price = pricing.get(model, (0.0, 0.0))
        cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
        self._breakdown[step] = self._breakdown.get(step, 0.0) + cost

    def record_cohere(self, step: str, search_units: int) -> None:
        cost = search_units * _COHERE_PER_UNIT
        self._breakdown[step] = self._breakdown.get(step, 0.0) + cost

    def total_cost(self) -> float:
        return sum(self._breakdown.values())

    def breakdown(self) -> dict[str, float]:
        return dict(self._breakdown)
