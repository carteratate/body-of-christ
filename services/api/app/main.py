import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.db import close_pool, get_pool, init_pool
from app.llm import close_llm, init_llm
from app.rag.api_keys import close_api_keys, init_api_keys
from app.rag.cross_encoder import close_cross_encoder, init_cross_encoder
from app.rag.embed import close_embed, init_embed
from app.rag.explain import close_explain, init_explain
from app.rag.qdrant_client import close_qdrant, init_qdrant
from app.routes.bookmarks import router as bookmarks_router
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.feedback import router as feedback_router
from app.routes.me import router as me_router
from app.routes.preferences import router as preferences_router
from app.routes.search import router as search_router
from app.routes.sessions import router as sessions_router
from app.routes.sources import router as sources_router
from app.routes.evaluate import router as evaluate_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_pool()
    except Exception as exc:
        logger.warning("DB pool init failed (%s); starting without DB", exc.__class__.__name__)
    if not settings.internal_api_secret:
        logger.warning("INTERNAL_API_SECRET is not set — all requests will bypass the secret check")
    init_llm()
    init_embed()
    init_qdrant()
    init_cross_encoder()
    init_api_keys()
    init_explain()
    yield
    await close_api_keys()
    await close_cross_encoder()
    await close_embed()
    await close_qdrant()
    await close_explain()
    await close_pool()
    await close_llm()


app = FastAPI(title="body-of-christ-api", lifespan=lifespan)

class InternalSecretMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/health/db"):
            return await call_next(request)
        if not settings.internal_api_secret:
            return await call_next(request)
        if request.headers.get("x-internal-secret") != settings.internal_api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


app.add_middleware(InternalSecretMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me_router, prefix="/v1")
app.include_router(chat_router, prefix="/v1")
app.include_router(sessions_router, prefix="/v1")
app.include_router(search_router, prefix="/v1")
app.include_router(documents_router, prefix="/v1")
app.include_router(bookmarks_router, prefix="/v1")
app.include_router(feedback_router, prefix="/v1")
app.include_router(preferences_router, prefix="/v1")
app.include_router(sources_router, prefix="/v1")
app.include_router(evaluate_router, prefix="/v1")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/health/db")
async def health_db() -> dict:
    pool = get_pool()
    if pool is None:
        return {"ok": False, "error": "DatabaseUnavailable"}
    try:
        await pool.fetchval("SELECT 1")
        return {"ok": True}
    except Exception:
        return {"ok": False, "error": "DatabaseError"}
