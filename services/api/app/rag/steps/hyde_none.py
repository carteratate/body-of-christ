"""S4 HyDE strategy: no hypothetical passages generated."""
from app.rag.steps.cost_tracker import CostTracker


async def run(
    query: str,
    collections: list[str],
    cost_tracker: CostTracker,
) -> dict[str, list[list[float]]]:
    return {}
