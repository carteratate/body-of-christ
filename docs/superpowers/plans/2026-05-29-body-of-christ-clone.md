# Body of Christ Clone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clone philo-corpus into `/home/carter/repos/body-of-christ` — a Catholic theology chat app with the same V1 architecture (authenticated streaming chat, session history, rate limiting) but adapted branding, system prompt, and filter contract. The project is named `body-of-christ` everywhere: repo, packages, and user-facing UI.

**Architecture:** Monorepo with `apps/web` (Next.js on Vercel), `services/api` (FastAPI on Railway), and `supabase/migrations`. The API contract changes `filters.philosophies` → `filters.collections`. AWS CI/CD and docs are removed entirely. No worker service.

**Tech Stack:** Next.js 16 + TypeScript + Tailwind v4, FastAPI + asyncpg + Pydantic, Supabase Auth + Postgres, Anthropic SDK, Railway (Docker), Vercel.

---

## Naming conventions

| Context | Name |
|---|---|
| Repo directory | `/home/carter/repos/body-of-christ` |
| Python package / pyproject name | `body-of-christ-api` |
| npm package name | `body-of-christ-web` |
| FastAPI app title | `body-of-christ-api` |
| User-facing UI display name | `Body of Christ` (shown in sidebar, headings, labels) |

---

## File Map

### Files copied VERBATIM from philo-corpus (no edits):
- `apps/web/eslint.config.mjs`
- `apps/web/next-env.d.ts`
- `apps/web/next.config.ts`
- `apps/web/postcss.config.mjs`
- `apps/web/tsconfig.json`
- `apps/web/vercel.json`
- `apps/web/public/` (all SVGs)
- `apps/web/src/app/v1/[...path]/route.ts`
- `apps/web/src/app/page.tsx`
- `apps/web/src/lib/supabase/client.ts`
- `apps/web/src/lib/supabase/server.ts`
- `apps/web/src/middleware.ts`
- `apps/web/AGENTS.md`
- `services/api/.dockerignore`
- `services/api/Dockerfile`
- `services/api/app/__init__.py`
- `services/api/app/auth/__init__.py`
- `services/api/app/auth/jwks.py`
- `services/api/app/auth/verify.py`
- `services/api/app/config.py`
- `services/api/app/db.py`
- `services/api/app/deps/__init__.py`
- `services/api/app/deps/auth.py`
- `services/api/app/deps/rate_limit.py`
- `services/api/app/llm.py`
- `services/api/app/models/__init__.py`
- `services/api/app/models/auth.py`
- `services/api/app/routes/__init__.py`
- `services/api/app/routes/me.py`
- `services/api/app/routes/sessions.py`
- `supabase/migrations/0001_chat_schema.sql`
- `supabase/migrations/0002_chat_indexes.sql`
- `supabase/migrations/0003_user_usage.sql`

### Files adapted (content specified in tasks below):
- `apps/web/package.json` — name → `body-of-christ-web`
- `apps/web/src/app/globals.css` — new "Sacred Night" theme
- `apps/web/src/app/layout.tsx` — title + description
- `apps/web/src/app/chat/page.tsx` — title
- `apps/web/src/app/login/page.tsx` — UI name + tagline
- `apps/web/src/components/auth/LoginForm.tsx` — theme colors
- `apps/web/src/components/chat/ChatShell.tsx` — UI name, filters, placeholder
- `apps/web/src/lib/api.ts` — filters interface
- `services/api/pyproject.toml` — name → `body-of-christ-api`
- `services/api/app/main.py` — app title
- `services/api/app/routes/chat.py` — system prompt + ChatFilters
- `.gitignore` — new
- `.env.example` — updated
- `CLAUDE.md` — new content
- `railway.toml` — new file

### Files NOT copied:
- `.github/workflows/deploy-api.yml`
- `docs/aws-iam-policy.json`
- `docs/aws-setup.md`
- `services/worker/` (empty placeholder — skip)

---

## Task 1: Create Repo Scaffold

**Files:** `/home/carter/repos/body-of-christ/` and all subdirectories.

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p /home/carter/repos/body-of-christ/apps/web/src/app/chat
mkdir -p /home/carter/repos/body-of-christ/apps/web/src/app/login
mkdir -p "/home/carter/repos/body-of-christ/apps/web/src/app/v1/[...path]"
mkdir -p /home/carter/repos/body-of-christ/apps/web/src/components/auth
mkdir -p /home/carter/repos/body-of-christ/apps/web/src/components/chat
mkdir -p /home/carter/repos/body-of-christ/apps/web/src/lib/supabase
mkdir -p /home/carter/repos/body-of-christ/apps/web/public
mkdir -p /home/carter/repos/body-of-christ/services/api/app/auth
mkdir -p /home/carter/repos/body-of-christ/services/api/app/deps
mkdir -p /home/carter/repos/body-of-christ/services/api/app/models
mkdir -p /home/carter/repos/body-of-christ/services/api/app/routes
mkdir -p /home/carter/repos/body-of-christ/supabase/migrations
mkdir -p /home/carter/repos/body-of-christ/docs/superpowers/plans
```

- [ ] **Step 2: Initialize git**

```bash
cd /home/carter/repos/body-of-christ && git init
```

Expected: `Initialized empty Git repository in /home/carter/repos/body-of-christ/.git/`

- [ ] **Step 3: Write .gitignore**

Create `/home/carter/repos/body-of-christ/.gitignore`:

```gitignore
# Node
node_modules/
.next/
*.tsbuildinfo

# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Env
.env
.env.local
services/api/.env

# OS
.DS_Store
```

- [ ] **Step 4: Commit scaffold**

```bash
cd /home/carter/repos/body-of-christ
git add .gitignore
git commit -m "chore: initialize body-of-christ repo"
```

---

## Task 2: Copy Verbatim Files

- [ ] **Step 1: Copy verbatim frontend files**

```bash
SRC=/home/carter/repos/philo-corpus
DST=/home/carter/repos/body-of-christ

cp $SRC/apps/web/eslint.config.mjs          $DST/apps/web/
cp $SRC/apps/web/next-env.d.ts              $DST/apps/web/
cp $SRC/apps/web/next.config.ts             $DST/apps/web/
cp $SRC/apps/web/postcss.config.mjs         $DST/apps/web/
cp $SRC/apps/web/tsconfig.json              $DST/apps/web/
cp $SRC/apps/web/vercel.json                $DST/apps/web/
cp $SRC/apps/web/package-lock.json          $DST/apps/web/
cp $SRC/apps/web/AGENTS.md                  $DST/apps/web/
cp $SRC/apps/web/public/file.svg            $DST/apps/web/public/
cp $SRC/apps/web/public/globe.svg           $DST/apps/web/public/
cp $SRC/apps/web/public/next.svg            $DST/apps/web/public/
cp $SRC/apps/web/public/vercel.svg          $DST/apps/web/public/
cp $SRC/apps/web/public/window.svg          $DST/apps/web/public/
cp "$SRC/apps/web/src/app/v1/[...path]/route.ts" "$DST/apps/web/src/app/v1/[...path]/route.ts"
cp $SRC/apps/web/src/app/page.tsx           $DST/apps/web/src/app/page.tsx
cp $SRC/apps/web/src/lib/supabase/client.ts $DST/apps/web/src/lib/supabase/client.ts
cp $SRC/apps/web/src/lib/supabase/server.ts $DST/apps/web/src/lib/supabase/server.ts
cp $SRC/apps/web/src/middleware.ts          $DST/apps/web/src/middleware.ts
```

- [ ] **Step 2: Copy verbatim backend files**

```bash
SRC=/home/carter/repos/philo-corpus
DST=/home/carter/repos/body-of-christ

cp $SRC/services/api/.dockerignore           $DST/services/api/
cp $SRC/services/api/Dockerfile              $DST/services/api/
cp $SRC/services/api/app/__init__.py         $DST/services/api/app/
cp $SRC/services/api/app/auth/__init__.py    $DST/services/api/app/auth/
cp $SRC/services/api/app/auth/jwks.py        $DST/services/api/app/auth/
cp $SRC/services/api/app/auth/verify.py      $DST/services/api/app/auth/
cp $SRC/services/api/app/config.py           $DST/services/api/app/
cp $SRC/services/api/app/db.py               $DST/services/api/app/
cp $SRC/services/api/app/deps/__init__.py    $DST/services/api/app/deps/
cp $SRC/services/api/app/deps/auth.py        $DST/services/api/app/deps/
cp $SRC/services/api/app/deps/rate_limit.py  $DST/services/api/app/deps/
cp $SRC/services/api/app/llm.py              $DST/services/api/app/
cp $SRC/services/api/app/models/__init__.py  $DST/services/api/app/models/
cp $SRC/services/api/app/models/auth.py      $DST/services/api/app/models/
cp $SRC/services/api/app/routes/__init__.py  $DST/services/api/app/routes/
cp $SRC/services/api/app/routes/me.py        $DST/services/api/app/routes/
cp $SRC/services/api/app/routes/sessions.py  $DST/services/api/app/routes/
```

- [ ] **Step 3: Copy migrations verbatim**

```bash
SRC=/home/carter/repos/philo-corpus
DST=/home/carter/repos/body-of-christ

cp $SRC/supabase/migrations/0001_chat_schema.sql $DST/supabase/migrations/
cp $SRC/supabase/migrations/0002_chat_indexes.sql $DST/supabase/migrations/
cp $SRC/supabase/migrations/0003_user_usage.sql   $DST/supabase/migrations/
```

- [ ] **Step 4: Commit copied files**

```bash
cd /home/carter/repos/body-of-christ
git add apps/ services/ supabase/
git commit -m "chore: copy verbatim files from philo-corpus"
```

---

## Task 3: Adapt Backend

**Files:**
- Create: `services/api/pyproject.toml`
- Create: `services/api/app/main.py`
- Create: `services/api/app/routes/chat.py`

- [ ] **Step 1: Write services/api/pyproject.toml**

Create `/home/carter/repos/body-of-christ/services/api/pyproject.toml`:

```toml
[project]
name = "body-of-christ-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic-settings>=2.2.0",
    "asyncpg>=0.29.0",
    "httpx>=0.27.0",
    "PyJWT[cryptography]>=2.8.0",
    "cryptography>=42.0.0",
    "anthropic>=0.40.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 2: Write services/api/app/main.py**

Create `/home/carter/repos/body-of-christ/services/api/app/main.py`:

```python
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
```

- [ ] **Step 3: Write services/api/app/routes/chat.py**

Changes from philo-corpus: `ChatFilters.philosophies` → `ChatFilters.collections`, system prompt updated to Catholic theology.

Create `/home/carter/repos/body-of-christ/services/api/app/routes/chat.py`:

```python
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
```

- [ ] **Step 4: Commit backend**

```bash
cd /home/carter/repos/body-of-christ
git add services/
git commit -m "feat: adapt backend for body-of-christ (collections filter, theology prompt)"
```

---

## Task 4: Adapt Frontend

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/src/app/globals.css`
- Create: `apps/web/src/app/layout.tsx`
- Create: `apps/web/src/app/chat/page.tsx`
- Create: `apps/web/src/app/login/page.tsx`
- Create: `apps/web/src/components/auth/LoginForm.tsx`
- Create: `apps/web/src/components/chat/ChatShell.tsx`
- Create: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Write apps/web/package.json**

Create `/home/carter/repos/body-of-christ/apps/web/package.json`:

```json
{
  "name": "body-of-christ-web",
  "version": "0.1.0",
  "private": true,
  "engines": {
    "node": ">=20"
  },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint"
  },
  "dependencies": {
    "@supabase/auth-ui-react": "^0.4.7",
    "@supabase/auth-ui-shared": "^0.1.8",
    "@supabase/ssr": "^0.10.0",
    "@supabase/supabase-js": "^2.101.1",
    "next": "16.2.2",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "react-markdown": "^10.1.0",
    "remark-gfm": "^4.0.1"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.2",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

- [ ] **Step 2: Write apps/web/src/app/globals.css**

"Sacred Night" theme — deep navy + Byzantine gold. Replaces philo-corpus "Midnight Scholar" slate/gold.

Create `/home/carter/repos/body-of-christ/apps/web/src/app/globals.css`:

```css
@import "tailwindcss";

@theme {
  /* Sacred Night — dark mode (default) */
  --color-brand-bg:      #090E1A;
  --color-brand-surface: #111829;
  --color-brand-accent:  #C4972A;
  --color-brand-primary: #EAE6DC;
  --color-brand-muted:   #7A8099;

  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

html {
  color-scheme: dark;
  height: 100%;
}

body {
  height: 100%;
  background-color: #090E1A;
  color: #EAE6DC;
}
```

- [ ] **Step 3: Write apps/web/src/app/layout.tsx**

Create `/home/carter/repos/body-of-christ/apps/web/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Body of Christ",
  description: "Explore Catholic theology through conversation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
```

- [ ] **Step 4: Write apps/web/src/app/chat/page.tsx**

Create `/home/carter/repos/body-of-christ/apps/web/src/app/chat/page.tsx`:

```tsx
import { ChatShell } from "@/components/chat/ChatShell";

export const metadata = { title: "Body of Christ" };

export default function ChatPage() {
  return <ChatShell />;
}
```

- [ ] **Step 5: Write apps/web/src/app/login/page.tsx**

Create `/home/carter/repos/body-of-christ/apps/web/src/app/login/page.tsx`:

```tsx
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata = { title: "Sign in — Body of Christ" };

export default function LoginPage() {
  return (
    <div className="flex min-h-full items-center justify-center bg-brand-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-brand-accent">
            Body of Christ
          </h1>
          <p className="mt-2 text-sm text-brand-muted">
            Explore Catholic theology through conversation
          </p>
        </div>

        <div className="rounded-xl border border-brand-surface bg-brand-surface p-6">
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Write apps/web/src/components/auth/LoginForm.tsx**

Colors updated to match Sacred Night theme (gold `#C4972A` instead of philo-corpus `#C9A84C`).

Create `/home/carter/repos/body-of-christ/apps/web/src/components/auth/LoginForm.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { createClient } from "@/lib/supabase/client";

export function LoginForm() {
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        router.replace("/chat");
      }
    });
    return () => subscription.unsubscribe();
  }, [router, supabase]);

  return (
    <Auth
      supabaseClient={supabase}
      appearance={{
        theme: ThemeSupa,
        variables: {
          default: {
            colors: {
              brand:                        "#C4972A",
              brandAccent:                  "#b38824",
              inputBackground:              "#111829",
              inputText:                    "#EAE6DC",
              inputPlaceholder:             "#7A8099",
              inputBorder:                  "#1C2A40",
              inputBorderFocus:             "#C4972A",
              inputBorderHover:             "#263650",
              defaultButtonBackground:      "#111829",
              defaultButtonBackgroundHover: "#172236",
              defaultButtonBorder:          "#1C2A40",
              defaultButtonText:            "#EAE6DC",
              dividerBackground:            "#1C2A40",
              anchorTextColor:              "#C4972A",
              anchorTextHoverColor:         "#b38824",
              messageText:                  "#EAE6DC",
              messageTextDanger:            "#f87171",
            },
            radii: {
              borderRadiusButton: "6px",
              inputBorderRadius:  "6px",
            },
            fonts: {
              bodyFontFamily:   "inherit",
              buttonFontFamily: "inherit",
            },
          },
        },
      }}
      providers={[]}
    />
  );
}
```

- [ ] **Step 7: Write apps/web/src/lib/api.ts**

Only change from philo-corpus: `philosophies` → `collections` in `ChatRequest`.

Create `/home/carter/repos/body-of-christ/apps/web/src/lib/api.ts`:

```typescript
const API_URL = "";

export interface SessionSummary {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatRequest {
  session_id?: string;
  message: string;
  filters: { collections: string[] };
}

export interface ChatResponse {
  session_id: string;
  message_id: string;
  answer: string;
  sources: unknown[];
  title: string | null;
}

export async function sendMessage(
  token: string,
  payload: ChatRequest,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error((error as { detail?: string }).detail ?? `API error ${res.status}`);
  }

  return res.json();
}

export async function streamMessage(
  token: string,
  payload: ChatRequest,
  onToken: (text: string) => void,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v1/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error((error as { detail?: string }).detail ?? `API error ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = JSON.parse(line.slice(6)) as
        | { type: "text"; text: string }
        | { type: "done"; session_id: string; message_id: string; sources: unknown[]; title: string | null }
        | { type: "error"; detail: string };

      if (data.type === "text") {
        onToken(data.text);
      } else if (data.type === "done") {
        return { session_id: data.session_id, message_id: data.message_id, answer: "", sources: data.sources, title: data.title };
      } else if (data.type === "error") {
        throw new Error(data.detail ?? "Streaming error");
      }
    }
  }

  throw new Error("Stream ended without completion");
}

export async function getSessions(token: string): Promise<SessionSummary[]> {
  const res = await fetch(`${API_URL}/v1/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  return (data as { sessions: SessionSummary[] }).sessions;
}

export async function getSessionMessages(
  token: string,
  sessionId: string,
): Promise<ChatMessage[]> {
  const res = await fetch(`${API_URL}/v1/sessions/${sessionId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  return (data as { messages: ChatMessage[] }).messages;
}
```

- [ ] **Step 8: Write apps/web/src/components/chat/ChatShell.tsx**

Changes from philo-corpus: display name `"Philo"` → `"Body of Christ"` everywhere visible, `philosophies: []` → `collections: []`, placeholder text updated.

Create `/home/carter/repos/body-of-christ/apps/web/src/components/chat/ChatShell.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createClient } from "@/lib/supabase/client";
import {
  streamMessage,
  getSessions,
  getSessionMessages,
  type ChatMessage,
  type SessionSummary,
} from "@/lib/api";

export function ChatShell() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);
  const isProgrammaticScroll = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingTokens = useRef("");
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      setToken(data.session?.access_token ?? null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_, session) => {
      setToken(session?.access_token ?? null);
      if (!session) router.replace("/login");
    });

    return () => subscription.unsubscribe();
  }, [router]);

  useEffect(() => {
    if (!token) return;
    getSessions(token).then(setSessions).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!pinnedToBottom.current) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    isProgrammaticScroll.current = true;
    if (loading) {
      el.scrollTop = el.scrollHeight;
    } else {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    requestAnimationFrame(() => { isProgrammaticScroll.current = false; });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !token || loading) return;

    setInput("");
    setError(null);
    pinnedToBottom.current = true;
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setLoading(true);

    try {
      const isNewSession = !sessionId;
      const res = await streamMessage(
        token,
        {
          session_id: sessionId ?? undefined,
          message: text,
          filters: { collections: [] },
        },
        (tokenText) => {
          pendingTokens.current += tokenText;
          if (rafRef.current === null) {
            rafRef.current = window.setTimeout(() => {
              const batch = pendingTokens.current;
              pendingTokens.current = "";
              rafRef.current = null;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + batch };
                return updated;
              });
            }, 80);
          }
        },
      );
      setSessionId(res.session_id);
      if (isNewSession) {
        setSessions((prev) => [
          { id: res.session_id, title: res.title ?? null, updated_at: new Date().toISOString() },
          ...prev,
        ]);
      }
    } catch (err) {
      if (rafRef.current !== null) {
        clearTimeout(rafRef.current);
        rafRef.current = null;
      }
      pendingTokens.current = "";
      setMessages((prev) => prev.slice(0, -1));
      const message = err instanceof Error ? err.message : "Something went wrong.";
      if (message.includes("401")) {
        const supabase = createClient();
        await supabase.auth.signOut();
        return;
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleLoadSession(id: string) {
    if (id === sessionId || loading) return;
    try {
      const msgs = await getSessionMessages(token!, id);
      setSessionId(id);
      setMessages(msgs);
      setError(null);
      setInput("");
    } catch {
      // silently ignore — session list is still intact
    }
  }

  function handleNewChat() {
    setSessionId(null);
    setMessages([]);
    setError(null);
    textareaRef.current?.focus();
  }

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
  }

  return (
    <div className="flex h-full bg-brand-bg text-brand-primary">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col border-r border-brand-surface bg-brand-surface">
        <div className="flex-shrink-0 px-4 pt-4 pb-2">
          <div className="text-xl font-semibold tracking-tight text-brand-accent">Body of Christ</div>
        </div>

        <div className="flex-shrink-0 px-4 pb-2">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-brand-muted transition-colors hover:bg-brand-bg hover:text-brand-primary"
          >
            <span className="text-lg leading-none">+</span>
            New conversation
          </button>
        </div>

        {sessions.length > 0 && (
          <div className="flex-shrink-0 px-4 pb-1">
            <p className="px-3 text-xs font-medium uppercase tracking-wider text-brand-muted">
              Conversations
            </p>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="flex flex-col gap-0.5">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => handleLoadSession(session.id)}
                disabled={loading}
                className={`w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  session.id === sessionId
                    ? "bg-brand-bg text-brand-primary"
                    : "text-brand-muted hover:bg-brand-bg hover:text-brand-primary"
                }`}
              >
                {session.title ?? "New Conversation"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-shrink-0 border-t border-brand-bg px-4 py-3">
          <button
            onClick={handleSignOut}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-brand-muted transition-colors hover:bg-brand-bg hover:text-brand-primary"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto px-6 py-6"
          onScroll={() => {
            if (isProgrammaticScroll.current) return;
            const el = scrollContainerRef.current;
            if (!el) return;
            pinnedToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
          }}
        >
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <p className="text-3xl font-semibold text-brand-accent">Body of Christ</p>
              <p className="max-w-sm text-brand-muted">
                Ask about scripture, doctrine, or Catholic tradition.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-2xl flex-col gap-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex flex-col gap-1 ${
                    msg.role === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <span className="text-xs text-brand-muted">
                    {msg.role === "user" ? "You" : "Body of Christ"}
                  </span>
                  <div
                    className={`max-w-prose rounded-xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-brand-accent/15 text-brand-primary whitespace-pre-wrap"
                        : "bg-brand-surface text-brand-primary prose-brand"
                    }`}
                  >
                    {msg.role === "user" ? (
                      msg.content
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ children }) => <h1 className="text-base font-semibold text-brand-primary mt-4 mb-2 first:mt-0">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-base font-semibold text-brand-primary mt-4 mb-2 first:mt-0">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-sm font-semibold text-brand-primary mt-3 mb-1 first:mt-0">{children}</h3>,
                          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                          ul: ({ children }) => <ul className="mb-3 space-y-1 list-disc pl-5 last:mb-0">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-3 space-y-1 list-decimal pl-5 last:mb-0">{children}</ol>,
                          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                          strong: ({ children }) => <strong className="font-semibold text-brand-primary">{children}</strong>,
                          em: ({ children }) => <em className="italic text-brand-muted">{children}</em>,
                          code: ({ children }) => <code className="rounded bg-brand-bg px-1 py-0.5 font-mono text-xs text-brand-accent">{children}</code>,
                          blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-accent pl-3 text-brand-muted italic my-3">{children}</blockquote>,
                          hr: () => <hr className="border-brand-surface my-4" />,
                          a: ({ href, children }) => {
                            const safe = href && !href.trimStart().toLowerCase().startsWith("javascript:") ? href : "#";
                            return <a href={safe} target="_blank" rel="noopener noreferrer" className="text-brand-accent underline">{children}</a>;
                          },
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    )}
                  </div>
                </div>
              ))}

              {loading && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex flex-col items-start gap-1">
                  <span className="text-xs text-brand-muted">Body of Christ</span>
                  <div className="rounded-xl bg-brand-surface px-4 py-3">
                    <span className="inline-flex gap-1">
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "0ms" }}>·</span>
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "150ms" }}>·</span>
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "300ms" }}>·</span>
                    </span>
                  </div>
                </div>
              )}

              {error && (
                <p className="text-center text-sm text-red-400">{error}</p>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-brand-surface bg-brand-bg px-6 py-4">
          <div className="mx-auto flex max-w-2xl items-end gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about scripture, doctrine, or tradition…"
              rows={1}
              className="flex-1 resize-none rounded-xl border border-brand-surface bg-brand-surface px-4 py-3 text-sm text-brand-primary placeholder-brand-muted outline-none transition-colors focus:border-brand-accent"
              style={{ maxHeight: "160px", overflowY: "auto" }}
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading || !token}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-accent text-brand-bg transition-opacity disabled:opacity-30"
              aria-label="Send"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-4 w-4"
              >
                <path d="M3.105 2.288a.75.75 0 0 0-.826.95l1.668 5.828a.75.75 0 0 0 .588.54l6.94 1.152a.75.75 0 0 1 0 1.483l-6.94 1.153a.75.75 0 0 0-.588.539l-1.668 5.828a.75.75 0 0 0 .826.95 28.896 28.896 0 0 0 15.293-7.154.75.75 0 0 0 0-1.115A28.897 28.897 0 0 0 3.105 2.288Z" />
              </svg>
            </button>
          </div>
          <p className="mx-auto mt-2 max-w-2xl text-center text-xs text-brand-muted">
            Press Enter to send · Shift+Enter for new line
          </p>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 9: Commit frontend**

```bash
cd /home/carter/repos/body-of-christ
git add apps/
git commit -m "feat: adapt frontend for Body of Christ (Sacred Night theme, collections filter)"
```

---

## Task 5: Root Config Files

**Files:**
- Create: `CLAUDE.md`
- Create: `.env.example`
- Create: `railway.toml`

- [ ] **Step 1: Write CLAUDE.md**

Create `/home/carter/repos/body-of-christ/CLAUDE.md`:

```markdown
# CLAUDE.md — Project Rules & Invariants

This repository (body-of-christ) implements a Catholic theology RAG chat application.
The user-facing product name is **Body of Christ**.
All changes MUST respect the following architectural, security, and design constraints.

---

## 1. Fixed Architecture (DO NOT CHANGE)

- Monorepo with separate deploy targets:
  - apps/web      → Next.js (TypeScript), deployed on Vercel
  - services/api  → Python FastAPI, deployed on Railway (Docker)
  - supabase/migrations → SQL migrations only

- Supabase is used for Postgres + pgvector (V2) + Auth.
- The frontend NEVER talks directly to the database.
- ALL client data access goes through FastAPI.

---

## 2. Authentication & Authorization (CRITICAL)

- Auth via Supabase Auth; frontend sends JWT as `Authorization: Bearer <token>`.
- Backend MUST verify Supabase JWT (signature, expiration, issuer) and extract `user_id` from `sub`.
- RLS MUST be enabled on all user-owned tables.
- Supabase service role key MUST NEVER appear in frontend code.

---

## 3. API Design (STABILITY REQUIRED)

All endpoints under `/v1/...`.

### POST /v1/chat (NON-NEGOTIABLE CONTRACT)

Request:
- session_id: string | null
- message: string
- filters: { collections: string[] }
- top_k?: number
- min_score?: number

Response:
- session_id: string
- message_id: string
- answer: string
- sources: []   // empty in V1, populated in V2+

This contract MUST NOT change across versions.

---

## 4. Data Model

### V1 Tables
- chat_sessions (id, user_id, title, created_at, updated_at)
- chat_messages (id, session_id, user_id, role, content, created_at)
- user_usage (user_id, rate_window_start, rate_count, quota_date, quota_count)

### V2 Tables (planned)
- documents (id, collection, title, metadata)
- chunks (id, document_id, content, position)
- embeddings (chunk_id, embedding pgvector)
- retrievals (message_id ↔ chunk_id ↔ score)

### Planned collections (V2 filter values)
- "bible" — book/chapter/verse hierarchy, translation metadata
- "catechism" — numbered CCC paragraphs, part/section/chapter structure
- "encyclicals" — pope, year, topic tags
- "church-fathers" — author, work, century, tradition

SQL migrations ONLY. Schema changes must be additive. RLS on all user-owned tables.

---

## 5. RAG Rules (V2+)

Explicit pipeline: embed query → vector search with collection filters → apply thresholds → return excerpts → LLM explains relevance.
No LangGraph or agent frameworks.

---

## 6. Deployment

- Backend: Docker → Railway. Same image runs locally and in prod.
- Frontend: Vercel.
- Config via environment variables only.
- Required health endpoints: GET /health, GET /health/db

---

## 7. Coding Standards

- Backend: FastAPI + Pydantic, structured logging, no secrets logged.
- Frontend: TypeScript, API calls centralized in `src/lib/api.ts`, no DB SDK in frontend.

---

## 8. Non-Goals

- No direct DB queries from frontend
- No serverless backend (Lambda, Supabase Edge Functions)
- No Kubernetes, no agent frameworks, no premature microservices

---

## 9. Design System — Sacred Night (dark mode, default)

| Token | Value | Usage |
|---|---|---|
| Background | `#090E1A` | Page background |
| Surface | `#111829` | Cards, sidebar, bubbles |
| Accent | `#C4972A` | CTAs, links, active states |
| Text primary | `#EAE6DC` | Body text, headings |
| Text muted | `#7A8099` | Timestamps, placeholders |

Use CSS custom properties via Tailwind `brand` namespace. No hardcoded hex values in components.
```

- [ ] **Step 2: Write .env.example**

Create `/home/carter/repos/body-of-christ/.env.example`:

```bash
# Copy to services/api/.env and fill in values

# Comma-separated allowed frontend origins
CORS_ORIGINS=["http://localhost:3000"]

# Database — use the Supabase pooler URL (Session mode, port 5432 or 6543)
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres

# Supabase auth
SUPABASE_PROJECT_URL=https://<project-ref>.supabase.co
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWKS_TTL_SECONDS=600

# LLM
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_TITLE_MODEL=claude-haiku-4-5
LLM_MAX_TOKENS=1024
CHAT_HISTORY_WINDOW=20

# Shared secret between Railway and Vercel — blocks direct API access
# Generate with: openssl rand -hex 32
INTERNAL_API_SECRET=

# Rate limiting
RATE_LIMIT_PER_MINUTE=10
DAILY_MESSAGE_QUOTA=50
```

- [ ] **Step 3: Write railway.toml**

Create `/home/carter/repos/body-of-christ/railway.toml`:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "services/api/Dockerfile"

[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

Note: In Railway dashboard, set the service **Root Directory** to `services/api` so Docker build context is the api directory.

- [ ] **Step 4: Copy this plan into the new repo**

```bash
cp /home/carter/repos/philo-corpus/docs/superpowers/plans/2026-05-29-superscroll-clone.md \
   /home/carter/repos/body-of-christ/docs/superpowers/plans/
```

- [ ] **Step 5: Commit root config**

```bash
cd /home/carter/repos/body-of-christ
git add CLAUDE.md .env.example railway.toml docs/
git commit -m "chore: add CLAUDE.md, env example, railway config"
```

---

## Task 6: Install Dependencies and Verify

- [ ] **Step 1: Install frontend dependencies**

```bash
cd /home/carter/repos/body-of-christ/apps/web && npm install
```

Expected: installs node_modules, no errors.

- [ ] **Step 2: Type-check frontend**

```bash
cd /home/carter/repos/body-of-christ/apps/web && npx tsc --noEmit
```

Expected: exits with code 0, no type errors.

- [ ] **Step 3: Build frontend**

```bash
cd /home/carter/repos/body-of-christ/apps/web && npm run build
```

Expected: Next.js build completes successfully. Fix any errors before continuing.

- [ ] **Step 4: Set up backend venv and install**

```bash
cd /home/carter/repos/body-of-christ/services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Expected: all packages install cleanly.

- [ ] **Step 5: Verify backend imports**

```bash
cd /home/carter/repos/body-of-christ/services/api
source .venv/bin/activate
python -c "from app.main import app; print('OK')"
```

Expected: prints `OK` with no import errors.

- [ ] **Step 6: Commit lockfile**

```bash
cd /home/carter/repos/body-of-christ
git add apps/web/package-lock.json
git commit -m "chore: lock frontend dependencies after install"
```

---

## What You Need to Do (User Checklist)

After implementation completes:

1. **Create a new Supabase project** — separate from philo-corpus
2. **Run migrations** in Supabase SQL editor — paste the 3 files in `supabase/migrations/` in order (0001, 0002, 0003)
3. **Create `apps/web/.env.local`**:
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://<new-project-ref>.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key from Supabase dashboard>
   API_URL=http://localhost:8000
   INTERNAL_API_SECRET=<generate: openssl rand -hex 32>
   ```
4. **Create `services/api/.env`** from `.env.example` — fill in DATABASE_URL, SUPABASE_PROJECT_URL, ANTHROPIC_API_KEY, INTERNAL_API_SECRET (same value as step 3)
5. **Push to GitHub** and connect Railway to `services/api/` — set env vars from step 4 in Railway dashboard
6. **Connect Vercel** to `apps/web/` — set `API_URL=<railway-url>` and `INTERNAL_API_SECRET` in Vercel env vars
