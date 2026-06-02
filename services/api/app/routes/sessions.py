import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionSummary(BaseModel):
    id: str
    title: str | None
    updated_at: str


class SessionsResponse(BaseModel):
    sessions: list[SessionSummary]


class MessageItem(BaseModel):
    role: str
    content: str


class SessionMessagesResponse(BaseModel):
    messages: list[MessageItem]


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(
    user: AuthUser = Depends(get_current_user),
) -> SessionsResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select id, title, updated_at
                from chat_sessions
                where user_id = $1
                order by updated_at desc
                limit 50
                """,
                user.user_id,
            )
    except Exception as exc:
        logger.error("list_sessions query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SessionsResponse(
        sessions=[
            SessionSummary(
                id=str(r["id"]),
                title=r["title"],
                updated_at=r["updated_at"].isoformat(),
            )
            for r in rows
        ]
    )


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> SessionMessagesResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "select 1 from chat_sessions where id = $1 and user_id = $2",
                session_id,
                user.user_id,
            )
            if not exists:
                raise HTTPException(status_code=404, detail="Session not found")

            rows = await conn.fetch(
                """
                select role, content
                from chat_messages
                where session_id = $1
                order by created_at asc
                """,
                session_id,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_session_messages query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SessionMessagesResponse(
        messages=[MessageItem(role=r["role"], content=r["content"]) for r in rows]
    )
