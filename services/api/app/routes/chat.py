import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.deps.rate_limit import check_rate_limit
from app.llm import complete, generate_title, stream_complete
from app.models.auth import AuthUser

router = APIRouter()

_SYSTEM_PROMPT = (
    "You are a knowledgeable Catholic theology assistant. "
    "Help users explore scripture, doctrine, Church teaching, and the writings of Church Fathers and theologians with clarity and fidelity to the Magisterium. "
    "Be precise, cite relevant sources when appropriate, and acknowledge uncertainty when it exists. "
    "Do not fabricate quotes or misattribute ideas."
)


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatFilters(BaseModel):
    collections: list[str] = []


class ChatRequest(BaseModel):
    session_id: Optional[UUID] = None
    message: str = Field(min_length=1, max_length=4000)
    filters: ChatFilters = Field(default_factory=ChatFilters)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    answer: str
    sources: list = []
    title: str | None = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=500, detail="Database not available")

    async with pool.acquire() as conn:
        if body.session_id is None:
            row = await conn.fetchrow(
                "insert into chat_sessions (user_id, title) values ($1, NULL) returning id",
                user.user_id,
            )
            session_id = row["id"]
        else:
            row = await conn.fetchrow(
                "select id from chat_sessions where id = $1 and user_id = $2",
                body.session_id,
                user.user_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Session not found")
            session_id = body.session_id

        await conn.execute(
            "insert into chat_messages (session_id, user_id, role, content) "
            "values ($1, $2, 'user', $3)",
            session_id,
            user.user_id,
            body.message,
        )

        rows = await conn.fetch(
            """
            select role, content from (
                select role, content, created_at
                from chat_messages
                where session_id = $1
                order by created_at desc
                limit $2
            ) sub
            order by created_at asc
            """,
            session_id,
            settings.chat_history_window,
        )

    is_new_session = body.session_id is None
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    try:
        answer = await complete(messages=messages, system=_SYSTEM_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="LLM unavailable") from exc

    async with pool.acquire() as conn:
        msg_row = await conn.fetchrow(
            "insert into chat_messages (session_id, user_id, role, content) "
            "values ($1, $2, 'assistant', $3) returning id",
            session_id,
            user.user_id,
            answer,
        )
        await conn.execute(
            "update chat_sessions set updated_at = now() where id = $1",
            session_id,
        )

    title: str | None = None
    if is_new_session:
        try:
            title = await generate_title(body.message)
            async with pool.acquire() as conn:
                await conn.execute(
                    "update chat_sessions set title = $1 where id = $2",
                    title,
                    session_id,
                )
        except Exception:
            title = None

    return ChatResponse(
        session_id=str(session_id),
        message_id=str(msg_row["id"]),
        answer=answer,
        sources=[],
        title=title,
    )


# ── Streaming endpoint ─────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> StreamingResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=500, detail="Database not available")

    async with pool.acquire() as conn:
        if body.session_id is None:
            row = await conn.fetchrow(
                "insert into chat_sessions (user_id, title) values ($1, NULL) returning id",
                user.user_id,
            )
            session_id = row["id"]
        else:
            row = await conn.fetchrow(
                "select id from chat_sessions where id = $1 and user_id = $2",
                body.session_id,
                user.user_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Session not found")
            session_id = body.session_id

        await conn.execute(
            "insert into chat_messages (session_id, user_id, role, content) "
            "values ($1, $2, 'user', $3)",
            session_id,
            user.user_id,
            body.message,
        )

        rows = await conn.fetch(
            """
            select role, content from (
                select role, content, created_at
                from chat_messages
                where session_id = $1
                order by created_at desc
                limit $2
            ) sub
            order by created_at asc
            """,
            session_id,
            settings.chat_history_window,
        )

    is_new_session = body.session_id is None
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    async def generate():
        chunks: list[str] = []
        try:
            async for text in stream_complete(messages=messages, system=_SYSTEM_PROMPT):
                chunks.append(text)
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'LLM unavailable'})}\n\n"
            return

        full_answer = "".join(chunks)

        async with pool.acquire() as conn:
            msg_row = await conn.fetchrow(
                "insert into chat_messages (session_id, user_id, role, content) "
                "values ($1, $2, 'assistant', $3) returning id",
                session_id,
                user.user_id,
                full_answer,
            )
            await conn.execute(
                "update chat_sessions set updated_at = now() where id = $1",
                session_id,
            )

        title: str | None = None
        if is_new_session:
            try:
                title = await generate_title(body.message)
                async with pool.acquire() as conn:
                    await conn.execute(
                        "update chat_sessions set title = $1 where id = $2",
                        title,
                        session_id,
                    )
            except Exception:
                title = None

        yield f"data: {json.dumps({'type': 'done', 'session_id': str(session_id), 'message_id': str(msg_row['id']), 'sources': [], 'title': title})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
