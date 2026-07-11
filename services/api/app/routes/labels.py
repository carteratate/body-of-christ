import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.labels import RetrievalLabelCreate, RetrievalLabelResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/labels", response_model=RetrievalLabelResponse, status_code=201)
async def submit_label(
    body: RetrievalLabelCreate,
    user: AuthUser = Depends(get_current_user),
) -> RetrievalLabelResponse:
    """Record a thumbs-up/down relevance label for a chunk in a search result."""
    try:
        chunk_uuid = uuid.UUID(body.chunk_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid chunk_id: must be a UUID")

    try:
        search_uuid = uuid.UUID(body.search_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid search_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            search_exists = await conn.fetchval(
                "SELECT id FROM searches WHERE id = $1 AND user_id = $2",
                search_uuid, uuid.UUID(user.user_id),
            )
            if search_exists is None:
                raise HTTPException(status_code=404, detail="Search not found")

            # Rank is training data, so derive it from the persisted retrieval
            # rather than accepting a client-provided value. This also proves
            # that the chunk was actually returned by this search.
            rank = await conn.fetchval(
                """
                SELECT rank
                FROM retrievals
                WHERE search_id = $1 AND chunk_id = $2
                """,
                search_uuid,
                chunk_uuid,
            )
            if rank is None:
                raise HTTPException(status_code=404, detail="Retrieval not found")

            row = await conn.fetchrow(
                """
                INSERT INTO retrieval_labels (user_id, chunk_id, search_id, label, rank)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT ON CONSTRAINT retrieval_labels_user_chunk_search_unique
                DO UPDATE SET label = EXCLUDED.label, rank = EXCLUDED.rank
                RETURNING id
                """,
                user.user_id,
                chunk_uuid,
                search_uuid,
                body.label,
                rank,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("submit_label upsert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return RetrievalLabelResponse(label_id=str(row["id"]))
