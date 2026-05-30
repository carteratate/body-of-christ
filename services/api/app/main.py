import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.db import close_pool, get_pool, init_pool
from app.llm import close_llm, init_llm
from app.routes.me import router as me_router
from app.routes.chat import router as chat_router
from app.routes.sessions import router as sessions_router


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
    yield
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
