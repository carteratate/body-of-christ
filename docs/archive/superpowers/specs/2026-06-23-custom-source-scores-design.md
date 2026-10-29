# Custom Source Scores — Design Spec

Feature that takes a user's question and predicts how useful each of the 10 source collections will be at answering it, displayed as a color-coded bar chart with expandable explanations.

## 1. Overview

- **Name:** Custom Source Scores
- **Route:** `/discover`
- **Purpose:** Before searching, users can type a question and see which collections are most likely to contain relevant answers, visualized as a horizontal bar graph.
- **Method:** Single Claude Sonnet call with a detailed, cached system prompt describing the actual corpus contents. Returns a 0.0–1.0 score and 1–2 sentence explanation per collection.
- **Auth:** Required (JWT). Wrapped in AppShell.
- **Rate limit:** 10 evaluations per user per day.

## 2. Backend

### 2.1 Endpoint

`POST /v1/evaluate`

Request body (Pydantic-validated):
```json
{
  "query": "What does the Church teach about the Eucharist?"
}
```

Constraints:
- `query`: non-empty string, max 500 characters

Response (200):
```json
{
  "query": "What does the Church teach about the Eucharist?",
  "remaining": 7,
  "scores": [
    {
      "collection": "catechism",
      "score": 0.95,
      "explanation": "The CCC dedicates an entire section (§1322–1419) to the Eucharist as sacrament, sacrifice, and Real Presence."
    },
    {
      "collection": "councils",
      "score": 0.90,
      "explanation": "The Council of Trent's Session XIII directly defines the doctrine of Real Presence and transubstantiation."
    }
  ]
}
```

The `scores` array is sorted by score descending. All 10 collections are always included.

Error responses:
- 401: Missing or invalid JWT
- 422: Validation error (empty query, exceeds 500 chars)
- 429: Daily limit reached. Body: `{"detail": "Daily evaluation limit reached"}`, `Retry-After` header.
- 500: LLM call failure (returns generic error)

### 2.2 Implementation

New file: `services/api/app/routes/evaluate.py`

Flow:
1. Verify JWT, extract `user_id`
2. Check rate limit: query `user_usage` for `evaluate_count` / `evaluate_date`. If `evaluate_date` != today, reset count to 0. If count >= 10, return 429.
3. Call Claude Sonnet with the static system prompt + user query as the user message
4. Parse JSON array from response
5. Increment `evaluate_count` in `user_usage`
6. Return response

The Anthropic client is shared with the reranker (already initialized at app startup via `init_rerank()`). Use `settings.rerank_model` (claude-sonnet-4-6) for the evaluate call.

### 2.3 System Prompt

Static prompt (~1500–2000 tokens) describing all 10 collections with corpus-specific detail. Cached via Anthropic prompt caching (cache_control on the system message block) so subsequent calls within the 5-minute TTL pay reduced input cost and get faster TTFT.

```
You are evaluating which Catholic theological source collections are most
likely to contain passages that directly answer a user's question. You have
access to exactly 10 collections. Score each 0.0–1.0 and provide a 1–2
sentence explanation.

IMPORTANT: You are scoring the LIKELIHOOD that each collection contains
relevant passages, not generating those passages. Base your assessment on
the content and scope described below.

COLLECTION DESCRIPTIONS:

1. "bible" — The complete 73-book Catholic biblical canon in the World
   English Bible — Catholic Edition (WEB-C) translation. Includes all 46
   Old Testament books (protocanonical + 7 deuterocanonicals: Tobit, Judith,
   1 & 2 Maccabees, Wisdom, Sirach, Baruch) and 27 New Testament books.
   Chunked by pericope (named passage units for the 66 protocanonical books)
   or by chapter (deuterocanonicals). Coverage spans: Pentateuch law and
   narrative, historical books, wisdom literature (Job, Proverbs,
   Ecclesiastes, Song of Solomon, Wisdom, Sirach), Psalms, prophetic books
   (major and minor), the four Gospels, Acts, Pauline and general epistles,
   and Revelation.
   STRONGEST FOR: scriptural foundations of any doctrine, moral teaching
   rooted in Scripture, prayer/devotion from Psalms and wisdom, Jesus's
   direct teachings and parables, Pauline theology, Old Testament typology,
   prophetic and apocalyptic literature.

2. "catechism" — The complete Catechism of the Catholic Church (CCC),
   paragraphs §1–§2865. Organized into four pillars: the Profession of Faith
   (Creed), the Celebration of the Christian Mystery (Sacraments), Life in
   Christ (Moral teaching and the Commandments), and Christian Prayer
   (including commentary on the Our Father). Each chunk is a page-level
   section containing numbered CCC paragraphs with cross-references to
   Scripture and the Church Fathers.
   STRONGEST FOR: "What does the Church teach about X?" questions, systematic
   doctrinal definitions, sacramental theology, moral theology organized by
   the Commandments, the theological virtues, and prayer.

3. "summa" — The complete Summa Theologiae by St. Thomas Aquinas (1265–1274).
   Structured as: First Part (God, creation, angels, man), First Part of the
   Second Part (happiness, human acts, habits, virtues, vices, law, grace),
   Second Part of the Second Part (faith, hope, charity, prudence, justice,
   fortitude, temperance, specific moral questions), and Third Part
   (Incarnation, sacraments). Each article follows the dialectical structure:
   Objections, Sed Contra, Respondeo ("I answer that..."), and Replies to
   Objections. Cites Aristotle ("the Philosopher"), Augustine, and Scripture
   extensively.
   STRONGEST FOR: rigorous philosophical theology, virtue and vice analysis,
   natural law, the nature and attributes of God, the soul and intellect,
   sacramental theology grounded in metaphysics, questions that benefit from
   systematic dialectical reasoning using act/potency, form/matter,
   essence/existence distinctions.

4. "encyclicals" — 131 papal encyclicals spanning 1740–2025, from Pope
   Benedict XIV through Pope Leo XIV. Major encyclicals include: Rerum
   Novarum (labor/social justice), Humanae Vitae (contraception/marriage),
   Fides et Ratio (faith and reason), Laudato Si' (environment/creation
   care), Veritatis Splendor (moral theology), Evangelium Vitae (sanctity
   of life), Deus Caritas Est (love), Redemptor Hominis (Christ the
   Redeemer), Mit Brennender Sorge (against Nazism), Divini Redemptoris
   (against communism), Mystici Corporis Christi (the Church as Body of
   Christ), Mediator Dei (sacred liturgy).
   STRONGEST FOR: Catholic social teaching, papal responses to modern moral
   questions, faith and reason, marriage and family, economic justice,
   dignity of human life, the Church's engagement with the modern world,
   liturgical theology.

5. "councils" — Documents from all 20 ecumenical councils (Nicaea I in 325
   through Vatican I in 1870) plus 16 Vatican II documents (4 constitutions:
   Dei Verbum, Lumen Gentium, Sacrosanctum Concilium, Gaudium et Spes; 9
   decrees; 3 declarations including Nostra Aetate and Dignitatis Humanae).
   Earlier councils are canons and anathemas; Vatican II is pastoral prose.
   STRONGEST FOR: dogmatic definitions (Trinity, Christology, canon of
   Scripture), sacramental validity, Church governance, ecumenism, religious
   liberty, liturgical reform, the nature of the Church, responses to
   historical heresies (Arianism, Nestorianism, Pelagianism, Protestant
   Reformation doctrines).

6. "church-fathers" — Works from the Ante-Nicene and Nicene/Post-Nicene
   Fathers series (CCEL editions). Includes major works by Augustine
   (Confessions, City of God, On the Holy Trinity), Athanasius (On the
   Incarnation), and other patristic authors from the ANF/NPNF volumes.
   Dense with Scripture quotation and theological interpretation.
   STRONGEST FOR: early Church interpretation of Scripture, patristic
   theology of the Trinity and Incarnation, development of doctrine in the
   first centuries, anti-heretical arguments, spiritual and devotional
   writings from the Fathers, Augustinian theology (grace, original sin,
   the two cities, the Trinity).

7. "medieval" — Medieval theological and devotional texts from the CCEL
   collection. Includes authors such as Anselm (Proslogion, Cur Deus Homo,
   Monologion), Boethius (Consolation of Philosophy), Bernard of Clairvaux,
   and Thomas a Kempis (Imitation of Christ). Ranges from rigorous
   philosophical theology (ontological argument, divine attributes) to
   affective devotional writing (love of God, prayer, spiritual life).
   STRONGEST FOR: medieval philosophical theology, the ontological argument
   for God's existence, atonement theory, devotional spirituality, mystical
   theology, the relationship between faith and reason in the medieval
   period.

8. "canon-law" — The complete 1983 Code of Canon Law (Codex Iuris
   Canonici), canons 1–1752, organized into 7 books: General Norms, The
   People of God, The Teaching Function, The Sanctifying Function, Temporal
   Goods, Sanctions, and Processes. One passage per canon. Prescriptive
   legal language defining rights, duties, and procedures.
   STRONGEST FOR: Church law and governance, sacramental requirements
   (marriage validity, baptism, ordination), rights and obligations of the
   faithful, ecclesiastical offices, penal law, tribunal procedures,
   religious life regulations.

9. "apostolic-exhortations" — 30 post-synodal apostolic exhortations from
   1908–2025 (Pope Pius X through Pope Leo XIV). Includes Familiaris
   Consortio (family), Evangelii Gaudium (joy of the Gospel), Amoris
   Laetitia (love in the family), Christifideles Laici (lay faithful),
   Vita Consecrata (consecrated life), Pastores Dabo Vobis (priestly
   formation), Verbum Domini (the Word of God), Sacramentum Caritatis
   (the Eucharist), Gaudete et Exsultate (holiness), Laudate Deum
   (climate), C'est la confiance (St. Therese), Catechesi Tradendae
   (catechesis).
   STRONGEST FOR: pastoral guidance on Christian living, family and
   marriage, priestly and religious vocation, evangelization, lay
   spirituality, post-synodal teaching that synthesizes bishops'
   deliberations.

10. "papal-documents" — 14 historical papal bulls and modern apostolic
    letters spanning 1302–2020. Includes Unam Sanctam (papal authority),
    Exsurge Domine (against Luther), Sublimis Deus (indigenous rights),
    Salvifici Doloris (suffering), Mulieris Dignitatem (dignity of women),
    Ordinatio Sacerdotalis (male-only ordination), Dies Domini (the Lord's
    Day), Rosarium Virginis Mariae (the Rosary), Patris Corde (St. Joseph).
    STRONGEST FOR: specific papal declarations on contested doctrinal
    points, historical Church pronouncements, devotional practices (Rosary,
    Sunday observance), suffering and redemption, dignity and vocation of
    women, papal authority.

SCORING GUIDELINES — use the FULL 0.0–1.0 range:
  0.9–1.0: This collection almost certainly contains passages that directly
           and substantively answer the question. Reserve for collections
           where the topic is a primary focus.
  0.7–0.89: Strong relevance — the collection addresses this topic from a
            clearly useful angle, even if not its central focus.
  0.4–0.69: Tangential — may touch on the theme but won't directly answer.
  0.1–0.39: Unlikely to contain relevant material for this specific question.
  0.0–0.09: No meaningful connection between this question and this collection.

QUESTION TYPE AWARENESS — let the nature of the question guide scoring:
  - Doctrinal ("What does the Church teach about..."): weight catechism,
    councils, summa higher.
  - Scriptural ("What does the Bible say about..."): weight bible highest.
  - Moral/Ethical ("Is it moral to...", "What is the Church's position on..."):
    weight summa, catechism, encyclicals.
  - Historical ("When did the Church...", "How did early Christians..."):
    weight councils, church-fathers, medieval.
  - Pastoral/Devotional ("How do I pray about...", "How should a Catholic..."):
    weight bible, apostolic-exhortations, catechism.
  - Legal/Canonical ("Is it required to...", "What are the rules for..."):
    weight canon-law highest.
  - Social Teaching ("What about poverty...", "economic justice..."):
    weight encyclicals, apostolic-exhortations, papal-documents.
  - Philosophical ("Does God exist?", "What is the soul?", "faith and reason"):
    weight summa, medieval, church-fathers.

Respond with ONLY a JSON array of all 10 collections, ordered by score
descending. Each element: {"collection": "<key>", "score": <float>,
"explanation": "<1-2 sentences>"}. No text before or after the array.
```

### 2.4 Rate Limiting

New columns on `user_usage` table:
- `evaluate_date date DEFAULT NULL`
- `evaluate_count integer DEFAULT 0`

Rate check query (same UPSERT pattern as existing search rate limiter):
```sql
INSERT INTO user_usage (user_id, evaluate_date, evaluate_count)
VALUES ($1, CURRENT_DATE, 1)
ON CONFLICT (user_id)
DO UPDATE SET
  evaluate_count = CASE
    WHEN user_usage.evaluate_date = CURRENT_DATE
    THEN user_usage.evaluate_count + 1
    ELSE 1
  END,
  evaluate_date = CURRENT_DATE
RETURNING evaluate_count
```

If returned `evaluate_count` > 10, return 429. The count was already incremented to 11, so on the next request the check fires before any LLM call. The off-by-one (11 stored, 10 allowed) is harmless — the gate is `> 10` on the post-increment value.

### 2.5 Migration

New migration file adds the two columns:
```sql
ALTER TABLE user_usage ADD COLUMN evaluate_date date DEFAULT NULL;
ALTER TABLE user_usage ADD COLUMN evaluate_count integer DEFAULT 0;
```

## 3. Frontend

### 3.1 Route & Page

- Route: `/discover`
- Page file: `apps/web/src/app/discover/page.tsx`
- Wrapped in `AppShell` (auth required, provides `token` and `preferences`)

### 3.2 Components

Location: `apps/web/src/components/discover/`

**DiscoverPage.tsx** — main page component:
- Text input + submit button (styled consistently with SearchBar)
- State: `query`, `loading`, `scores`, `error`, `expandedCollection`, `remainingEvaluations`
- On submit: calls `evaluateCollections()` from `api.ts`
- Empty state before first query: brief explanation of the tool
- Rate limit state: shows remaining evaluations count, modal on 429

**RelevanceChart.tsx** — the bar visualization:
- Props: `scores: CollectionScore[]`, `expandedCollection: string | null`, `onToggleExpand: (key: string) => void`
- Horizontal bar chart, one row per collection
- Each row: collection label (left), animated bar (fills left-to-right), numeric score (right)
- Bar color uses the collection's existing CSS variable from `collections.ts`
- Sorted by score descending
- Click/tap a bar row to expand the explanation text below it
- Bars animate in with staggered CSS transitions on mount

### 3.3 API Client

New function in `apps/web/src/lib/api.ts`:

```typescript
export interface CollectionScore {
  collection: string;
  score: number;
  explanation: string;
}

export interface EvaluateResponse {
  query: string;
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
      throw new RateLimitError("Daily evaluation limit reached");
    }
    const error = await res.json().catch(() => ({}));
    throw new Error((error as { detail?: string }).detail ?? `API error ${res.status}`);
  }
  return res.json() as Promise<EvaluateResponse>;
}
```

A custom `RateLimitError` class (or a flag on the error) lets the component distinguish 429 from other errors.

### 3.4 Sidebar Navigation

Add to `Sidebar.tsx` bottom nav, between "List of Sources" and "Saved Passages":

```tsx
<Link href="/discover" ...>
  <BarChart3 size={12} /> Custom Source Scores
</Link>
```

Icon: `BarChart3` from Lucide (horizontal bar chart icon — matches the feature's visualization).

### 3.5 Remaining Evaluations Display

Small muted text below the input showing "N evaluations remaining today" — decrements on each successful call. Sourced from `10 - evaluate_count` returned alongside the response (or tracked client-side after a 429).

## 4. Security

- JWT required on `POST /v1/evaluate` — same `verify_token` dependency as all `/v1/` routes
- `user_id` extracted from JWT `sub` claim; used for rate limiting
- User query is passed as a user message to the Anthropic API, never interpolated into the system prompt string
- Input validation via Pydantic: `query` must be non-empty, max 500 characters
- Rate limit: 10 evaluations per user per day, enforced server-side via `user_usage` table
- No user data is stored beyond the rate limit counter (evaluations are not persisted to a history table)
- System prompt is static — no user-controlled content in the cached prompt block

## 5. Files to Create / Modify

### New files:
- `services/api/app/routes/evaluate.py` — endpoint + rate limiting
- `supabase/migrations/NNNN_add_evaluate_rate_limit.sql` — migration
- `apps/web/src/app/discover/page.tsx` — route page
- `apps/web/src/components/discover/DiscoverPage.tsx` — main component
- `apps/web/src/components/discover/RelevanceChart.tsx` — bar chart

### Modified files:
- `services/api/app/main.py` — register the evaluate router
- `apps/web/src/lib/api.ts` — add `evaluateCollections()`, `CollectionScore`, `EvaluateResponse`, `RateLimitError`
- `apps/web/src/components/layout/Sidebar.tsx` — add "Custom Source Scores" nav link
