import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.product_feedback import ProductFeedbackCreate, ProductFeedbackResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_ROUTES = {
    "/search", "/history", "/sources", "/bookmarks", "/discover",
    "/about", "/settings", "/feedback", "/reader",
}
_RATE_LIMIT = 5
_RATE_WINDOW_MINUTES = 10


def _optional_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field}: must be a UUID") from exc


def _normalize_route(route: str | None) -> str | None:
    if route is None:
        return None
    normalized = route.rstrip("/") or "/"
    if normalized.startswith("/reader/"):
        return "/reader"
    if normalized not in _ALLOWED_ROUTES:
        raise HTTPException(status_code=422, detail="Invalid route")
    return normalized


def _browser_family(user_agent: str) -> str:
    value = user_agent.lower()
    if "edg/" in value:
        return "edge"
    if "firefox/" in value:
        return "firefox"
    if "chrome/" in value or "crios/" in value:
        return "chrome"
    if "safari/" in value:
        return "safari"
    return "other"


@router.post("/product-feedback", response_model=ProductFeedbackResponse, status_code=201)
async def submit_product_feedback(
    body: ProductFeedbackCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ProductFeedbackResponse:
    """Persist a privacy-bounded product report for the authenticated user."""
    user_id = _optional_uuid(user.user_id, "user_id")
    search_id = _optional_uuid(body.search_id, "search_id")
    chunk_id = _optional_uuid(body.chunk_id, "chunk_id")
    document_id = _optional_uuid(body.document_id, "document_id")
    route = _normalize_route(body.route)
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Transaction-scoped lock makes the rate limit atomic across
                # Railway workers and replicas sharing the same database.
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"product-feedback:{user_id}")
                recent = await conn.fetchval(
                    """
                    SELECT count(*) FROM product_feedback
                    WHERE user_id = $1
                      AND created_at >= now() - ($2 * interval '1 minute')
                    """,
                    user_id, _RATE_WINDOW_MINUTES,
                )
                if int(recent or 0) >= _RATE_LIMIT:
                    raise HTTPException(
                        status_code=429,
                        detail="Too many feedback reports. Try again in a few minutes.",
                        headers={"Retry-After": str(_RATE_WINDOW_MINUTES * 60)},
                    )

                if search_id is not None:
                    owned = await conn.fetchval(
                        "SELECT 1 FROM searches WHERE id = $1 AND user_id = $2",
                        search_id, user_id,
                    )
                    if owned is None:
                        raise HTTPException(status_code=404, detail="Feedback context not found")
                if chunk_id is not None and search_id is not None:
                    related = await conn.fetchval(
                        "SELECT 1 FROM retrievals WHERE search_id = $1 AND chunk_id = $2",
                        search_id, chunk_id,
                    )
                    if related is None:
                        raise HTTPException(status_code=404, detail="Feedback context not found")
                if chunk_id is not None:
                    chunk_document = await conn.fetchval(
                        "SELECT document_id FROM chunks WHERE id = $1", chunk_id,
                    )
                    if chunk_document is None:
                        raise HTTPException(status_code=404, detail="Feedback context not found")
                    if document_id is not None and chunk_document != document_id:
                        raise HTTPException(status_code=404, detail="Feedback context not found")
                    document_id = chunk_document
                elif document_id is not None:
                    exists = await conn.fetchval("SELECT 1 FROM documents WHERE id = $1", document_id)
                    if exists is None:
                        raise HTTPException(status_code=404, detail="Feedback context not found")

                row = await conn.fetchrow(
                    """
                    INSERT INTO product_feedback (
                        user_id, category, message, contact_allowed, route,
                        viewport_width, viewport_height, browser_family,
                        search_id, chunk_id, document_id, error_code
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id
                    """,
                    user_id, body.category, body.message.strip(), body.contact_allowed,
                    route, body.viewport_width, body.viewport_height,
                    _browser_family(
                        request.headers.get("x-theocorpus-user-agent")
                        or request.headers.get("user-agent", "")
                    ),
                    search_id, chunk_id, document_id, body.error_code,
                )
    except HTTPException:
        raise
    except Exception as exc:
        # Never log the free-text report or raw user agent.
        logger.error("product feedback insert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return ProductFeedbackResponse(feedback_id=str(row["id"]))
