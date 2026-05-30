import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.feedback import FeedbackCreate, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    body: FeedbackCreate,
    user: AuthUser = Depends(get_current_user),
) -> FeedbackResponse:
    """Submit or update thumbs-up/down feedback for a chunk."""
    try:
        chunk_uuid = uuid.UUID(body.chunk_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid chunk_id: must be a UUID")

    search_uuid = None
    if body.search_id is not None:
        try:
            search_uuid = uuid.UUID(body.search_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid search_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            chunk_exists = await conn.fetchval("SELECT id FROM chunks WHERE id = $1", chunk_uuid)
            if chunk_exists is None:
                raise HTTPException(status_code=404, detail="Chunk not found")

            if search_uuid:
                search_exists = await conn.fetchval(
                    "SELECT id FROM searches WHERE id = $1 AND user_id = $2",
                    search_uuid, uuid.UUID(user.user_id),
                )
                if search_exists is None:
                    raise HTTPException(status_code=404, detail="Search not found")

            row = await conn.fetchrow(
                """
                INSERT INTO chunk_feedback (user_id, chunk_id, feedback, search_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT ON CONSTRAINT chunk_feedback_user_chunk_unique
                DO UPDATE SET feedback = EXCLUDED.feedback, search_id = EXCLUDED.search_id
                RETURNING id
                """,
                user.user_id,
                chunk_uuid,
                body.feedback,
                search_uuid,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("submit_feedback upsert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return FeedbackResponse(feedback_id=str(row["id"]))
