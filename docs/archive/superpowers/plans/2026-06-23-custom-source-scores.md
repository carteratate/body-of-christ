# Custom Source Scores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/discover` page where users type a question and see a bar chart of how relevant each of the 10 source collections is, powered by a single Claude Sonnet call with prompt caching.

**Architecture:** New `POST /v1/evaluate` backend endpoint calls Sonnet with a static cached system prompt describing all 10 collections, returns scored JSON. New Next.js page at `/discover` renders the scores as an animated horizontal bar chart with expandable explanations. Rate-limited to 10/day per user via `user_usage` columns.

**Tech Stack:** FastAPI + Pydantic (backend), Anthropic SDK with prompt caching (LLM), Next.js + React + Tailwind (frontend), Supabase Postgres (rate limiting migration)

## Global Constraints

- All endpoints under `/v1/`, require JWT auth via `get_current_user` dependency
- Frontend pages wrapped in `AppShell` for auth context
- Collection keys must match `VALID_COLLECTIONS` in `services/api/app/rag/constants.py`
- Collection colors from `apps/web/src/lib/collections.ts`
- Design system: Sacred Night dark theme, `brand-*` CSS custom properties
- No hardcoded hex values in components — use CSS variables
- API calls centralized in `apps/web/src/lib/api.ts`

---

### Task 1: Database migration — add evaluate rate limit columns

**Files:**
- Create: `supabase/migrations/0017_add_evaluate_rate_limit.sql`

**Interfaces:**
- Consumes: nothing
- Produces: `user_usage.evaluate_date` (date) and `user_usage.evaluate_count` (integer) columns, used by Task 2's rate limiter

- [ ] **Step 1: Write the migration**

```sql
-- Add per-user daily rate limit columns for the /v1/evaluate endpoint.
-- Nullable date: NULL means no evaluations yet today. Count defaults to 0.
alter table user_usage
  add column evaluate_date date default null,
  add column evaluate_count integer default 0;
```

Save to `supabase/migrations/0017_add_evaluate_rate_limit.sql`.

- [ ] **Step 2: Verify migration syntax**

Run: `cd services/api && python3 -c "print('Migration file created')"` and manually inspect the SQL is valid.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/0017_add_evaluate_rate_limit.sql
git commit -m "feat: add evaluate_date/evaluate_count columns to user_usage"
```

---

### Task 2: Backend — Pydantic models and evaluate endpoint

**Files:**
- Create: `services/api/app/models/evaluate.py`
- Create: `services/api/app/routes/evaluate.py`
- Modify: `services/api/app/main.py` (add router import and registration)
- Test: `services/api/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `get_current_user` from `app.deps.auth` (returns `AuthUser` with `.user_id: str`), `get_pool` from `app.db`, `settings.rerank_model` from `app.config`, reranker's Anthropic client from `app.rag.rerank._client`
- Produces: `POST /v1/evaluate` endpoint returning `EvaluateResponse(query: str, remaining: int, scores: list[CollectionScore])` where `CollectionScore(collection: str, score: float, explanation: str)`

- [ ] **Step 1: Write the Pydantic models**

Create `services/api/app/models/evaluate.py`:

```python
from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class CollectionScore(BaseModel):
    collection: str
    score: float
    explanation: str


class EvaluateResponse(BaseModel):
    query: str
    remaining: int
    scores: list[CollectionScore]
```

- [ ] **Step 2: Write the failing test for model validation**

Create `services/api/tests/test_evaluate.py`:

```python
"""Tests for the evaluate endpoint models and helpers."""
import pytest
from pydantic import ValidationError

from app.models.evaluate import EvaluateRequest


def test_evaluate_request_valid():
    req = EvaluateRequest(query="What is the Eucharist?")
    assert req.query == "What is the Eucharist?"


def test_evaluate_request_rejects_empty():
    with pytest.raises(ValidationError):
        EvaluateRequest(query="")


def test_evaluate_request_rejects_too_long():
    with pytest.raises(ValidationError):
        EvaluateRequest(query="x" * 501)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_evaluate.py -v`
Expected: 3 PASS

- [ ] **Step 4: Write the evaluate route with system prompt, LLM call, and rate limiting**

Create `services/api/app/routes/evaluate.py`:

```python
import datetime
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.evaluate import CollectionScore, EvaluateRequest, EvaluateResponse
from app.rag.rerank import _client as _rerank_client

logger = logging.getLogger(__name__)

router = APIRouter()

_DAILY_EVALUATE_LIMIT = 10

_EVALUATE_SYSTEM = (
    "You are evaluating which Catholic theological source collections are most "
    "likely to contain passages that directly answer a user's question. You have "
    "access to exactly 10 collections. Score each 0.0–1.0 and provide a 1–2 "
    "sentence explanation.\n\n"
    "IMPORTANT: You are scoring the LIKELIHOOD that each collection contains "
    "relevant passages, not generating those passages. Base your assessment on "
    "the content and scope described below.\n\n"
    "COLLECTION DESCRIPTIONS:\n\n"
    '1. "bible" — The complete 73-book Catholic biblical canon in the World '
    "English Bible — Catholic Edition (WEB-C) translation. Includes all 46 "
    "Old Testament books (protocanonical + 7 deuterocanonicals: Tobit, Judith, "
    "1 & 2 Maccabees, Wisdom, Sirach, Baruch) and 27 New Testament books. "
    "Chunked by pericope (named passage units for the 66 protocanonical books) "
    "or by chapter (deuterocanonicals). Coverage spans: Pentateuch law and "
    "narrative, historical books, wisdom literature (Job, Proverbs, "
    "Ecclesiastes, Song of Solomon, Wisdom, Sirach), Psalms, prophetic books "
    "(major and minor), the four Gospels, Acts, Pauline and general epistles, "
    "and Revelation.\n"
    "STRONGEST FOR: scriptural foundations of any doctrine, moral teaching "
    "rooted in Scripture, prayer/devotion from Psalms and wisdom, Jesus's "
    "direct teachings and parables, Pauline theology, Old Testament typology, "
    "prophetic and apocalyptic literature.\n\n"
    '2. "catechism" — The complete Catechism of the Catholic Church (CCC), '
    "paragraphs §1–§2865. Organized into four pillars: the Profession of Faith "
    "(Creed), the Celebration of the Christian Mystery (Sacraments), Life in "
    "Christ (Moral teaching and the Commandments), and Christian Prayer "
    "(including commentary on the Our Father). Each chunk is a page-level "
    "section containing numbered CCC paragraphs with cross-references to "
    "Scripture and the Church Fathers.\n"
    'STRONGEST FOR: "What does the Church teach about X?" questions, systematic '
    "doctrinal definitions, sacramental theology, moral theology organized by "
    "the Commandments, the theological virtues, and prayer.\n\n"
    '3. "summa" — The complete Summa Theologiae by St. Thomas Aquinas (1265–1274). '
    "Structured as: First Part (God, creation, angels, man), First Part of the "
    "Second Part (happiness, human acts, habits, virtues, vices, law, grace), "
    "Second Part of the Second Part (faith, hope, charity, prudence, justice, "
    "fortitude, temperance, specific moral questions), and Third Part "
    "(Incarnation, sacraments). Each article follows the dialectical structure: "
    'Objections, Sed Contra, Respondeo ("I answer that..."), and Replies to '
    "Objections. Cites Aristotle (\"the Philosopher\"), Augustine, and Scripture "
    "extensively.\n"
    "STRONGEST FOR: rigorous philosophical theology, virtue and vice analysis, "
    "natural law, the nature and attributes of God, the soul and intellect, "
    "sacramental theology grounded in metaphysics, questions that benefit from "
    "systematic dialectical reasoning using act/potency, form/matter, "
    "essence/existence distinctions.\n\n"
    '4. "encyclicals" — 131 papal encyclicals spanning 1740–2025, from Pope '
    "Benedict XIV through Pope Leo XIV. Major encyclicals include: Rerum "
    "Novarum (labor/social justice), Humanae Vitae (contraception/marriage), "
    "Fides et Ratio (faith and reason), Laudato Si' (environment/creation "
    "care), Veritatis Splendor (moral theology), Evangelium Vitae (sanctity "
    "of life), Deus Caritas Est (love), Redemptor Hominis (Christ the "
    "Redeemer), Mit Brennender Sorge (against Nazism), Divini Redemptoris "
    "(against communism), Mystici Corporis Christi (the Church as Body of "
    "Christ), Mediator Dei (sacred liturgy).\n"
    "STRONGEST FOR: Catholic social teaching, papal responses to modern moral "
    "questions, faith and reason, marriage and family, economic justice, "
    "dignity of human life, the Church's engagement with the modern world, "
    "liturgical theology.\n\n"
    '5. "councils" — Documents from all 20 ecumenical councils (Nicaea I in 325 '
    "through Vatican I in 1870) plus 16 Vatican II documents (4 constitutions: "
    "Dei Verbum, Lumen Gentium, Sacrosanctum Concilium, Gaudium et Spes; 9 "
    "decrees; 3 declarations including Nostra Aetate and Dignitatis Humanae). "
    "Earlier councils are canons and anathemas; Vatican II is pastoral prose.\n"
    "STRONGEST FOR: dogmatic definitions (Trinity, Christology, canon of "
    "Scripture), sacramental validity, Church governance, ecumenism, religious "
    "liberty, liturgical reform, the nature of the Church, responses to "
    "historical heresies (Arianism, Nestorianism, Pelagianism, Protestant "
    "Reformation doctrines).\n\n"
    '6. "church-fathers" — Works from the Ante-Nicene and Nicene/Post-Nicene '
    "Fathers series (CCEL editions). Includes major works by Augustine "
    "(Confessions, City of God, On the Holy Trinity), Athanasius (On the "
    "Incarnation), and other patristic authors from the ANF/NPNF volumes. "
    "Dense with Scripture quotation and theological interpretation.\n"
    "STRONGEST FOR: early Church interpretation of Scripture, patristic "
    "theology of the Trinity and Incarnation, development of doctrine in the "
    "first centuries, anti-heretical arguments, spiritual and devotional "
    "writings from the Fathers, Augustinian theology (grace, original sin, "
    "the two cities, the Trinity).\n\n"
    '7. "medieval" — Medieval theological and devotional texts from the CCEL '
    "collection. Includes authors such as Anselm (Proslogion, Cur Deus Homo, "
    "Monologion), Boethius (Consolation of Philosophy), Bernard of Clairvaux, "
    "and Thomas à Kempis (Imitation of Christ). Ranges from rigorous "
    "philosophical theology (ontological argument, divine attributes) to "
    "affective devotional writing (love of God, prayer, spiritual life).\n"
    "STRONGEST FOR: medieval philosophical theology, the ontological argument "
    "for God's existence, atonement theory, devotional spirituality, mystical "
    "theology, the relationship between faith and reason in the medieval "
    "period.\n\n"
    '8. "canon-law" — The complete 1983 Code of Canon Law (Codex Iuris '
    "Canonici), canons 1–1752, organized into 7 books: General Norms, The "
    "People of God, The Teaching Function, The Sanctifying Function, Temporal "
    "Goods, Sanctions, and Processes. One passage per canon. Prescriptive "
    "legal language defining rights, duties, and procedures.\n"
    "STRONGEST FOR: Church law and governance, sacramental requirements "
    "(marriage validity, baptism, ordination), rights and obligations of the "
    "faithful, ecclesiastical offices, penal law, tribunal procedures, "
    "religious life regulations.\n\n"
    '9. "apostolic-exhortations" — 30 post-synodal apostolic exhortations from '
    "1908–2025 (Pope Pius X through Pope Leo XIV). Includes Familiaris "
    "Consortio (family), Evangelii Gaudium (joy of the Gospel), Amoris "
    "Laetitia (love in the family), Christifideles Laici (lay faithful), "
    "Vita Consecrata (consecrated life), Pastores Dabo Vobis (priestly "
    "formation), Verbum Domini (the Word of God), Sacramentum Caritatis "
    "(the Eucharist), Gaudete et Exsultate (holiness), Laudate Deum "
    "(climate), C'est la confiance (St. Therese), Catechesi Tradendae "
    "(catechesis).\n"
    "STRONGEST FOR: pastoral guidance on Christian living, family and "
    "marriage, priestly and religious vocation, evangelization, lay "
    "spirituality, post-synodal teaching that synthesizes bishops' "
    "deliberations.\n\n"
    '10. "papal-documents" — 14 historical papal bulls and modern apostolic '
    "letters spanning 1302–2020. Includes Unam Sanctam (papal authority), "
    "Exsurge Domine (against Luther), Sublimis Deus (indigenous rights), "
    "Salvifici Doloris (suffering), Mulieris Dignitatem (dignity of women), "
    "Ordinatio Sacerdotalis (male-only ordination), Dies Domini (the Lord's "
    "Day), Rosarium Virginis Mariae (the Rosary), Patris Corde (St. Joseph).\n"
    "STRONGEST FOR: specific papal declarations on contested doctrinal "
    "points, historical Church pronouncements, devotional practices (Rosary, "
    "Sunday observance), suffering and redemption, dignity and vocation of "
    "women, papal authority.\n\n"
    "SCORING GUIDELINES — use the FULL 0.0–1.0 range:\n"
    "  0.9–1.0: This collection almost certainly contains passages that directly "
    "and substantively answer the question. Reserve for collections where the "
    "topic is a primary focus.\n"
    "  0.7–0.89: Strong relevance — the collection addresses this topic from a "
    "clearly useful angle, even if not its central focus.\n"
    "  0.4–0.69: Tangential — may touch on the theme but won't directly answer.\n"
    "  0.1–0.39: Unlikely to contain relevant material for this specific question.\n"
    "  0.0–0.09: No meaningful connection between this question and this collection.\n\n"
    "QUESTION TYPE AWARENESS — let the nature of the question guide scoring:\n"
    '  - Doctrinal ("What does the Church teach about..."): weight catechism, '
    "councils, summa higher.\n"
    '  - Scriptural ("What does the Bible say about..."): weight bible highest.\n'
    '  - Moral/Ethical ("Is it moral to...", "What is the Church\'s position on..."): '
    "weight summa, catechism, encyclicals.\n"
    '  - Historical ("When did the Church...", "How did early Christians..."): '
    "weight councils, church-fathers, medieval.\n"
    '  - Pastoral/Devotional ("How do I pray about...", "How should a Catholic..."): '
    "weight bible, apostolic-exhortations, catechism.\n"
    '  - Legal/Canonical ("Is it required to...", "What are the rules for..."): '
    "weight canon-law highest.\n"
    '  - Social Teaching ("What about poverty...", "economic justice..."): '
    "weight encyclicals, apostolic-exhortations, papal-documents.\n"
    '  - Philosophical ("Does God exist?", "What is the soul?", "faith and reason"): '
    "weight summa, medieval, church-fathers.\n\n"
    "Respond with ONLY a JSON array of all 10 collections, ordered by score "
    "descending. Each element: {\"collection\": \"<key>\", \"score\": <float>, "
    "\"explanation\": \"<1-2 sentences>\"}. No text before or after the array."
)


def _extract_scores(text: str) -> list[dict]:
    """Extract the JSON array from the LLM response, stripping markdown fences."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in evaluate response")
    return json.loads(match.group(0))


async def _check_evaluate_rate_limit(user_id: str) -> int:
    """Increment and check the daily evaluate counter.

    Returns the updated count. Raises HTTPException(429) if limit exceeded.
    """
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO user_usage (user_id, evaluate_date, evaluate_count)
            VALUES ($1, CURRENT_DATE, 1)
            ON CONFLICT (user_id) DO UPDATE SET
                evaluate_count = CASE
                    WHEN user_usage.evaluate_date = CURRENT_DATE
                    THEN user_usage.evaluate_count + 1
                    ELSE 1
                END,
                evaluate_date = CURRENT_DATE
            RETURNING evaluate_count
            """,
            user_id,
        )
    except Exception as exc:
        logger.error("evaluate rate_limit check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    count = row["evaluate_count"]
    if count > _DAILY_EVALUATE_LIMIT:
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = str(max(1, int((midnight - now).total_seconds())))
        raise HTTPException(
            status_code=429,
            detail="Daily evaluation limit reached",
            headers={"Retry-After": retry_after},
        )
    return count


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_collections(
    body: EvaluateRequest,
    user: AuthUser = Depends(get_current_user),
) -> EvaluateResponse:
    """Score how relevant each source collection is to the user's question."""
    count = await _check_evaluate_rate_limit(user.user_id)

    if _rerank_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        response = await _rerank_client.messages.create(
            model=settings.rerank_model,
            max_tokens=2000,
            system=[{
                "type": "text",
                "text": _EVALUATE_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": body.query}],
        )
        raw_text = response.content[0].text
        scored = _extract_scores(raw_text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("evaluate LLM call failed: %s", exc)
        raise HTTPException(status_code=500, detail="Evaluation failed. Please try again.") from exc

    scores = [
        CollectionScore(
            collection=str(item.get("collection", "")),
            score=max(0.0, min(1.0, float(item.get("score", 0.0)))),
            explanation=str(item.get("explanation", "")),
        )
        for item in scored
    ]
    scores.sort(key=lambda s: s.score, reverse=True)

    return EvaluateResponse(
        query=body.query,
        remaining=max(0, _DAILY_EVALUATE_LIMIT - count),
        scores=scores,
    )
```

- [ ] **Step 5: Write tests for _extract_scores and model validation**

Add to `services/api/tests/test_evaluate.py`:

```python
from app.routes.evaluate import _extract_scores


def test_extract_scores_from_clean_json():
    text = '[{"collection":"bible","score":0.9,"explanation":"test"}]'
    result = _extract_scores(text)
    assert len(result) == 1
    assert result[0]["collection"] == "bible"


def test_extract_scores_from_markdown_fenced():
    text = '```json\n[{"collection":"bible","score":0.9,"explanation":"test"}]\n```'
    result = _extract_scores(text)
    assert len(result) == 1


def test_extract_scores_raises_on_no_array():
    import pytest
    with pytest.raises(ValueError, match="No JSON array"):
        _extract_scores("No valid JSON here")
```

- [ ] **Step 6: Run tests**

Run: `cd services/api && python -m pytest tests/test_evaluate.py -v`
Expected: 6 PASS

- [ ] **Step 7: Register the router in main.py**

Add to `services/api/app/main.py`, after the sources_router import:

```python
from app.routes.evaluate import router as evaluate_router
```

And after `app.include_router(sources_router, prefix="/v1")`:

```python
app.include_router(evaluate_router, prefix="/v1")
```

- [ ] **Step 8: Commit**

```bash
git add services/api/app/models/evaluate.py services/api/app/routes/evaluate.py services/api/app/main.py services/api/tests/test_evaluate.py
git commit -m "feat: add POST /v1/evaluate endpoint with Sonnet scoring and rate limiting"
```

---

### Task 3: Frontend — API client and types

**Files:**
- Modify: `apps/web/src/lib/api.ts`

**Interfaces:**
- Consumes: `POST /v1/evaluate` endpoint from Task 2
- Produces: `CollectionScore` type, `EvaluateResponse` type, `evaluateCollections(token, query)` function, `EvaluateRateLimitError` class — all consumed by Task 4's `DiscoverPage`

- [ ] **Step 1: Add types and function to api.ts**

Append to the end of `apps/web/src/lib/api.ts`:

```typescript
// ── V2 Evaluate (Custom Source Scores) ────────────────────────────────────

export class EvaluateRateLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvaluateRateLimitError";
  }
}

export interface CollectionScore {
  collection: string;
  score: number;
  explanation: string;
}

export interface EvaluateResponse {
  query: string;
  remaining: number;
  scores: CollectionScore[];
}

export async function evaluateCollections(
  token: string,
  query: string,
): Promise<EvaluateResponse> {
  const res = await fetch(`${API_URL}/v1/evaluate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    if (res.status === 429) {
      throw new EvaluateRateLimitError("Daily evaluation limit reached");
    }
    const error = await res.json().catch(() => ({}));
    throw new Error(
      (error as { detail?: string }).detail ?? `API error ${res.status}`,
    );
  }
  return res.json() as Promise<EvaluateResponse>;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd apps/web && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat: add evaluateCollections API client for Custom Source Scores"
```

---

### Task 4: Frontend — DiscoverPage and RelevanceChart components

**Files:**
- Create: `apps/web/src/components/discover/DiscoverPage.tsx`
- Create: `apps/web/src/components/discover/RelevanceChart.tsx`
- Create: `apps/web/src/app/discover/page.tsx`

**Interfaces:**
- Consumes: `evaluateCollections`, `EvaluateRateLimitError`, `CollectionScore`, `EvaluateResponse` from `api.ts` (Task 3); `useAppContext()` from `AppShell`; `getCollectionMeta`, `COLLECTIONS` from `collections.ts`
- Produces: `/discover` route accessible in the browser

- [ ] **Step 1: Create RelevanceChart component**

Create `apps/web/src/components/discover/RelevanceChart.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { getCollectionMeta } from "@/lib/collections";
import type { CollectionScore } from "@/lib/api";

interface RelevanceChartProps {
  scores: CollectionScore[];
}

export function RelevanceChart({ scores }: RelevanceChartProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  function toggle(key: string) {
    setExpanded((prev) => (prev === key ? null : key));
  }

  return (
    <div className="space-y-2">
      {scores.map((s, i) => {
        const meta = getCollectionMeta(s.collection);
        const label = meta?.label ?? s.collection;
        const color = meta?.hex ?? "#C4972A";
        const isOpen = expanded === s.collection;

        return (
          <div key={s.collection}>
            <button
              onClick={() => toggle(s.collection)}
              className="w-full text-left group"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs text-brand-muted w-32 shrink-0 truncate">
                  {label}
                </span>
                <div className="flex-1 h-7 bg-brand-bg rounded overflow-hidden relative">
                  <div
                    className="h-full rounded transition-all duration-700 ease-out"
                    style={{
                      width: `${Math.max(2, s.score * 100)}%`,
                      backgroundColor: color,
                      opacity: 0.85,
                      transitionDelay: `${i * 80}ms`,
                    }}
                  />
                </div>
                <span className="text-xs text-brand-muted w-10 text-right tabular-nums">
                  {s.score.toFixed(2)}
                </span>
                {isOpen ? (
                  <ChevronUp size={14} className="text-brand-muted shrink-0" />
                ) : (
                  <ChevronDown size={14} className="text-brand-muted shrink-0" />
                )}
              </div>
            </button>
            {isOpen && (
              <div className="ml-[calc(8rem+0.75rem)] mr-14 mt-1 mb-2 text-xs text-brand-muted leading-relaxed">
                {s.explanation}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create DiscoverPage component**

Create `apps/web/src/components/discover/DiscoverPage.tsx`:

```tsx
"use client";

import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";
import { RelevanceChart } from "@/components/discover/RelevanceChart";
import {
  evaluateCollections,
  EvaluateRateLimitError,
  type CollectionScore,
} from "@/lib/api";

export function DiscoverPage() {
  const { token } = useAppContext();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [scores, setScores] = useState<CollectionScore[] | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    const q = query.trim();
    if (!q || !token || loading) return;

    setLoading(true);
    setError(null);
    setScores(null);
    setSubmittedQuery(q);

    try {
      const res = await evaluateCollections(token, q);
      setScores(res.scores);
      setRemaining(res.remaining);
      setQuery("");
    } catch (err) {
      if (err instanceof EvaluateRateLimitError) {
        setError("You've reached the daily limit of 10 evaluations. Try again tomorrow.");
        setRemaining(0);
      } else {
        setError(err instanceof Error ? err.message : "Evaluation failed");
      }
      setScores(null);
    } finally {
      setLoading(false);
    }
  }, [query, token, loading]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 pt-6 pb-4">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-lg font-semibold text-brand-primary mb-1 font-brand">
            Custom Source Scores
          </h1>
          <p className="text-sm text-brand-muted mb-6">
            Type a question to see which sources are most likely to have relevant answers.
          </p>

          {/* Input */}
          <div className="flex gap-2 mb-6">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. What does the Church teach about the Eucharist?"
              className="flex-1 bg-brand-surface border border-brand-bg rounded-lg px-3 py-2 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:border-brand-accent"
              disabled={loading}
              maxLength={500}
            />
            <button
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              className="bg-brand-accent text-brand-bg rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-40 font-brand"
            >
              {loading ? "Scoring..." : "Score"}
            </button>
          </div>

          {/* Remaining count */}
          {remaining !== null && (
            <p className="text-xs text-brand-muted mb-4">
              {remaining} evaluation{remaining !== 1 ? "s" : ""} remaining today
            </p>
          )}

          {/* Error */}
          {error && (
            <div className="text-sm text-red-400 mb-4">{error}</div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center gap-2 text-sm text-brand-muted py-8">
              <Search size={14} className="animate-pulse" />
              Evaluating sources...
            </div>
          )}

          {/* Results */}
          {scores && submittedQuery && (
            <div>
              <div className="flex justify-end mb-4">
                <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
                  {submittedQuery}
                </div>
              </div>
              <RelevanceChart scores={scores} />
            </div>
          )}

          {/* Empty state */}
          {!scores && !loading && !error && !submittedQuery && (
            <div className="text-center py-12 text-brand-muted text-sm">
              Enter a theological question above to discover which sources
              in the corpus are best equipped to answer it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create the route page**

Create `apps/web/src/app/discover/page.tsx`:

```tsx
import { AppShell } from "@/components/layout/AppShell";
import { DiscoverPage } from "@/components/discover/DiscoverPage";

export default function Discover() {
  return (
    <AppShell>
      <DiscoverPage />
    </AppShell>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd apps/web && npx tsc --noEmit --pretty 2>&1 | tail -10`
Expected: no new errors

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/discover/RelevanceChart.tsx apps/web/src/components/discover/DiscoverPage.tsx apps/web/src/app/discover/page.tsx
git commit -m "feat: add DiscoverPage with RelevanceChart for Custom Source Scores"
```

---

### Task 5: Sidebar nav link and visual verification

**Files:**
- Modify: `apps/web/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `/discover` route from Task 4
- Produces: sidebar navigation link to Custom Source Scores page

- [ ] **Step 1: Add the sidebar link**

In `apps/web/src/components/layout/Sidebar.tsx`, add the `BarChart3` import to the existing Lucide import:

```tsx
import { Library, Bookmark, Church, Settings, BarChart3 } from "lucide-react";
```

Then add this link between the "List of Sources" `<Link>` and the "Saved Passages" `<Link>` in the bottom nav section:

```tsx
        <Link
          href="/discover"
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/discover" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <BarChart3 size={12} /> Custom Source Scores
        </Link>
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd apps/web && npx tsc --noEmit --pretty 2>&1 | tail -5`
Expected: no new errors

- [ ] **Step 3: Start the dev server and verify in browser**

Run: `cd apps/web && npm run dev`

Verify:
1. Sidebar shows "Custom Source Scores" link with bar chart icon between "List of Sources" and "Saved Passages"
2. Clicking it navigates to `/discover`
3. Page shows title, description, and input field
4. Entering a question and clicking "Score" sends the request (will 500 without backend running — that's expected)
5. The empty state text appears before any query is submitted

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/layout/Sidebar.tsx
git commit -m "feat: add Custom Source Scores link to sidebar navigation"
```
