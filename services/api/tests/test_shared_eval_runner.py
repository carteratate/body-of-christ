from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.rag.compare import shared_runner
from app.rag.pipelines.registry import PIPELINES


def _row(i: int) -> dict:
    return {
        "id": f"00000000-0000-0000-0000-{i:012d}",
        "content": f"chunk {i}",
        "reference": f"Ref {i}",
        "collection": "bible",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "Doc",
        "author": None,
        "anchor": None,
        "position": i,
        "annotation": None,
    }


@pytest.mark.asyncio
async def test_capture_runs_shared_remote_steps_once_and_derives_pipeline_depths():
    configs = [
        PIPELINES["hyde_haiku"],
        PIPELINES["hyde_cohere_haiku"],
        PIPELINES["hyde_cohere_luna"],
    ]
    ranked = [_row(i) for i in range(50)]
    with (
        patch("app.rag.compare.shared_runner.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.compare.shared_runner.hyde_s25.run",
              new=AsyncMock(return_value={"bible": [[0.2]]})),
        patch("app.rag.compare.shared_runner.retrieve_vector.run",
              new=AsyncMock(return_value={"bible": [ranked]})) as vector,
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(return_value={"bible": ranked})) as fts,
        patch("app.rag.compare.shared_runner.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
    ):
        artifacts = await shared_runner.capture("q", ["bible"], 4, configs)

    assert vector.await_count == 1
    assert fts.await_count == 1
    assert len(artifacts.candidate_pools["hyde_haiku"]["bible"]) == 12
    assert len(artifacts.candidate_pools["hyde_cohere_haiku"]["bible"]) == 50
    assert (
        [c.chunk_id for c in artifacts.candidate_pools["hyde_cohere_haiku"]["bible"]]
        == [c.chunk_id for c in artifacts.candidate_pools["hyde_cohere_luna"]["bible"]]
    )


def test_shared_artifact_round_trip_preserves_candidates():
    artifact = shared_runner.SharedArtifacts(
        query="q",
        collections=["bible"],
        quota=4,
        candidate_pools={},
        cost_breakdown={"embed": 0.1},
        total_cost=0.1,
        duration_s=1.2,
        degradations=[],
        degradation_events=[],
    )
    restored = shared_runner.SharedArtifacts.from_dict(artifact.to_dict())
    assert restored == artifact
