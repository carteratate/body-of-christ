import asyncio
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
from app.rag.api_keys import close_api_keys, init_api_keys, is_ready as hyde_is_ready
from app.rag.steps.embed import close_embed, init_embed, is_ready as embed_is_ready
from app.rag.steps.rerank_haiku import close_rerank, init_rerank
from app.rag.steps.rerank_cohere import close_cohere, init_cohere, is_ready as cohere_is_ready
from app.rag.steps.llm_rerank.openai_provider import close as close_luna, init as init_luna
from app.rag.steps.llm_rerank.openai_provider import PROVIDER as luna_provider
from app.rag.steps.explain import close_explain, init_explain
from app.rag.qdrant_client import (
    QDRANT_COLLECTION,
    close_qdrant,
    get_qdrant_client,
    init_qdrant,
)
from app.rag.compare.judge import close_judge, init_judge
from app.routes.bookmarks import router as bookmarks_router
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.labels import router as labels_router
from app.routes.me import router as me_router
from app.routes.preferences import router as preferences_router
from app.routes.search import router as search_router
from app.routes.sessions import router as sessions_router
from app.routes.sources import router as sources_router
from app.routes.evaluate import router as evaluate_router
from app.routes.compare import router as compare_router
from app.routes.compare_stats import router as compare_stats_router
from app.routes.guest_search import router as guest_search_router


logger = logging.getLogger(__name__)


def _search_readiness() -> dict[str, bool]:
    return {
        "database": get_pool() is not None,
        "embeddings": embed_is_ready(),
        "hyde": hyde_is_ready(),
        "qdrant": get_qdrant_client() is not None,
        "cohere": cohere_is_ready(),
        "terminal_reranker": luna_provider.is_ready(),
    }


async def _live_search_readiness() -> dict[str, bool]:
    """Run bounded, non-billable checks for dependencies that expose a safe ping.

    Model providers expose initialization state separately because validating their
    credentials would require a billable inference request. The response names this
    distinction explicitly instead of presenting configuration as live connectivity.
    """
    live = {"database": False, "qdrant": False}
    pool = get_pool()
    if pool is not None:
        try:
            await asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=3.0)
            live["database"] = True
        except Exception:
            logger.warning("search health: database live check failed")
    client = get_qdrant_client()
    if client is not None:
        try:
            await asyncio.wait_for(
                client.get_collection(QDRANT_COLLECTION),
                timeout=3.0,
            )
            live["qdrant"] = True
        except Exception:
            logger.warning("search health: qdrant live check failed")
    return live


async def _db_keepalive() -> None:
    """Ping the DB every 90s to keep the asyncpg connection pool warm."""
    while True:
        await asyncio.sleep(90)
        pool = get_pool()
        if pool is not None:
            try:
                await pool.fetchval("SELECT 1")
            except Exception as exc:
                logger.warning("db_keepalive: ping failed (%s)", exc.__class__.__name__)


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
    init_api_keys()
    init_rerank()
    init_cohere()
    init_luna()
    init_explain()
    init_judge()
    readiness = _search_readiness()
    missing = [name for name, ready in readiness.items() if not ready]
    if missing:
        message = f"Search dependencies not ready: {', '.join(missing)}"
        if settings.app_env == "production":
            raise RuntimeError(message)
        logger.warning(message)
    keepalive_task = asyncio.create_task(_db_keepalive())
    yield
    keepalive_task.cancel()
    await close_judge()
    await close_luna()
    await close_cohere()
    await close_rerank()
    await close_api_keys()
    await close_embed()
    await close_qdrant()
    await close_explain()
    await close_pool()
    await close_llm()


app = FastAPI(title="theocorpus-api", lifespan=lifespan)

class InternalSecretMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/health/db", "/health/search"):
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
app.include_router(labels_router, prefix="/v1")
app.include_router(preferences_router, prefix="/v1")
app.include_router(sources_router, prefix="/v1")
app.include_router(evaluate_router, prefix="/v1")
app.include_router(compare_router, prefix="/v1")
app.include_router(compare_stats_router, prefix="/v1")
app.include_router(guest_search_router, prefix="/v1")


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


@app.get("/health/search")
async def health_search() -> JSONResponse:
    initialized = _search_readiness()
    live = await _live_search_readiness()
    ok = all(initialized.values()) and all(live.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "ok": ok,
            "initialized": initialized,
            "live": live,
            "note": (
                "Model-provider credentials are configuration-checked only; validating "
                "them requires a billable inference request."
            ),
        },
    )
