# Gate-Based Loading Animation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-timer loading animation with a gate-based system that ties animation phases to actual backend SSE events, making animation duration responsive to query speed.

**Architecture:** The animation is split into two sequences separated by a "stretch point." Sequence 1 (query outward to sources→chunks→winners returning to sources) plays on mount and stretches with a source-glow pulse until Gate 1 (`searching` SSE event) opens. Sequence 2 (sources→BoC, sequential flash, return line, border pulse) plays after Gate 1 and stretches with a border pulse until Gate 2 (`done` SSE event) opens. The SVG elements and their CSS transitions remain identical — only the timing control changes.

**Tech Stack:** React (hooks, refs, useEffect), SVG + CSS transitions, SSE event props

## Global Constraints

- All SVG elements (circles, lines, text) and their state-driven visibility logic remain unchanged — only timing orchestration changes
- CSS transition durations are shortened: 3s→1.5s (gold line), 1s→0.6s (all other line transitions)
- Anticipatory pulse/glow timing preserves the original "80% drawn" pattern: for 0.6s lines, pulse starts 120ms before arrival (line 80% drawn); for the 1.5s gold line, pulse starts 200ms before arrival (87% drawn, close to original 93%)
- Chunk flash is a reaction (not anticipatory): double flash starting 300ms AFTER lines arrive, matching original pattern
- Sequential per-source flash uses a dynamic `perSource` duration: `min(300, floor(1500 / N))` ms, capping total at ~2s
- Minimum stretch dwell of 200ms — if a gate is already open when stretch is reached, pause 200ms before advancing (prevents visual jump)
- The `searchPhase` and `isQueryDone` signals already exist in `SearchPage` state — no backend changes required
- `LoadingAnimation` must still handle: error during animation (showAnimation → false unmounts it), abort/new search (unmount), and the edge case where both gates open before the animation reaches either stretch point

---

## File Map

| File | Change |
|---|---|
| `apps/web/src/components/search/LoadingAnimation.tsx` | Rewrite timing useEffect; speed up CSS transitions; add stretch pulse logic |
| `apps/web/src/components/search/SearchPage.tsx` | Pass `retrievalStarted` prop to LoadingAnimation |

---

## Task 1: Gate-based animation rewrite

**Files:**
- Modify: `apps/web/src/components/search/LoadingAnimation.tsx` (lines 66-244 — Props interface + timing useEffect + stretch logic)
- Modify: `apps/web/src/components/search/SearchPage.tsx` (line 419 — LoadingAnimation prop)
- Test: Browser visual testing (dev server)

**Interfaces:**
- Consumes: `searchPhase` state from `SearchPage` (already exists, currently passed to `SearchResults` as `phase`)
- Consumes: `isQueryDone` prop (already passed as `isQueryDone`)
- Produces: same visual animation with dynamic timing; same `onReadyToShow` / `onFadeComplete` callbacks

---

### Overview of new timing architecture

**Gate signals:**
- Gate 1 = `retrievalStarted` prop (true when SSE `status: "searching"` or `"ranking"` received)
- Gate 2 = `isQueryDone` prop (true when SSE `done` received) — already passed

**Phase sequence:**

```
SEQUENCE 1 (runs on mount, ~4.9s hard content):

  t=100     phase=1, searchLineDone=true        → gold line starts (1.5s CSS), arrives t=1600
  t=1400    openingPulse=true                   → 200ms before arrival (line 87% drawn)
  t=1700    searchGone=true                     → gold line fades (100ms after arrival)
  t=2100    openingPulse=false, phase=2,        → BoC→source lines start (0.6s CSS), arrive t=2700
            sourcesReady=true                     (400ms processing gap after line fades)
  t=2580    glowColor=true                      → 120ms before source arrival (line 80% drawn)
  t=2800    glowColor=false, phase=3            → source→chunk lines start (0.6s CSS), arrive t=3400
  t=3700    chunkFlash=true                     → 300ms AFTER arrival (reaction flash #1)
  t=3900    chunkFlash=false                    → off
  t=4000    chunkFlash=true                     → reaction flash #2
  t=4200    chunkFlash=false, phase=5           → winner→source colored lines (0.6s CSS), arrive t=4800
  t=4680    glowColor=true                      → 120ms before winner arrival (line 80% drawn)
  t=4900    glowColor=false → ENTER STRETCH 1

STRETCH 1 (source glow pulse — interval toggles glowColor every 1200ms):
  If gate1 already open → wait 200ms minimum then advance
  Else → pulse until gate1 opens

SEQUENCE 2 (runs when Gate 1 opens + stretch 1 resolved, times relative to start):

  t=0       phase=7                             → ALL source→BoC colored lines start (0.6s CSS), arrive t=600
  t=480     sequential flash begins             → 120ms before lines arrive (80% drawn)
            perSource = min(300, floor(1500/N))
  seqEnd = 480 + N * perSource
  t=seqEnd       qPulse(ACCENT)                → gold BoC pulse
  t=seqEnd+200   sourcesGone=true              → sources fade out
  t=seqEnd+400   qPulse=null, returnLineDone=true → return line starts (0.6s CSS), arrives seqEnd+1000
  t=seqEnd+880   borderFlash=true              → 120ms before return line arrives (80% drawn)
  t=seqEnd+1050  bocGone=true                  → BoC fades (50ms after return arrives)
  t=seqEnd+1100  → ENTER STRETCH 2

STRETCH 2 (border pulse — interval toggles borderFlash every 1500ms):
  If gate2 already open → wait 200ms minimum then advance
  Else → pulse until gate2 opens

RESOLVE:
  fading=true, onReadyToShow()
  t+1500: onFadeComplete()
```

**Timing budget by collection count:**
```
Sequence 2 hard content = 480 + N*perSource + 1100

  3 cols:  480 + 900  + 1100 = 2480ms
  5 cols:  480 + 1500 + 1100 = 3080ms
  10 cols: 480 + 1500 + 1100 = 3080ms (perSource capped at 150ms)
```

**Sequential flash timing:**
```typescript
const perSource = Math.min(300, Math.floor(1500 / act.length));
// 3 cols → 300ms each = 900ms total
// 5 cols → 300ms each = 1500ms total
// 10 cols → 150ms each = 1500ms total
```

---

- [ ] **Step 1: Add `retrievalStarted` prop to LoadingAnimation**

In `apps/web/src/components/search/LoadingAnimation.tsx`, update the Props interface:

```typescript
interface Props {
  collections: string[];
  isQueryDone: boolean;
  retrievalStarted: boolean;
  onReadyToShow: () => void;
  onFadeComplete: () => void;
}
```

Update the destructuring:

```typescript
export function LoadingAnimation({ collections, isQueryDone, retrievalStarted, onReadyToShow, onFadeComplete }: Props) {
```

- [ ] **Step 2: Pass `retrievalStarted` from SearchPage**

In `apps/web/src/components/search/SearchPage.tsx`, update the LoadingAnimation JSX (around line 419):

```typescript
<LoadingAnimation
  collections={activeCollections}
  isQueryDone={queryDone}
  retrievalStarted={searchPhase !== null || queryDone}
  onReadyToShow={handleAnimReadyToShow}
  onFadeComplete={handleAnimFadeComplete}
/>
```

Note: `searchPhase !== null || queryDone` handles the case where `searchPhase` resets to null in `onDone` before the component re-renders — `queryDone` acts as a latch.

- [ ] **Step 3: Add gate refs in LoadingAnimation**

After the existing `isQueryDoneRef` and `waitingRef` refs (~line 139), add:

```typescript
const retrievalStartedRef = useRef(retrievalStarted);
const stretchPhaseRef = useRef<"gate1" | "gate2" | null>(null);
const stretchIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
```

Add a sync effect for the retrieval ref:

```typescript
useEffect(() => { retrievalStartedRef.current = retrievalStarted; }, [retrievalStarted]);
```

- [ ] **Step 4: Replace the existing timing useEffect**

Delete the entire timer chain useEffect (lines 173-244 of the current file). Replace with three separate effects:

**Effect 1 — Sequence 1 (pre-gate, runs on mount):**

```typescript
useEffect(() => {
  const act = active.length > 0 ? active : Object.keys(PALETTE).slice(0, 4);

  const w: Record<string, number[]> = {};
  act.forEach(key => {
    const a = Math.floor(Math.random() * N_CHUNKS);
    let b = Math.floor(Math.random() * (N_CHUNKS - 1)); if (b >= a) b++;
    let c = Math.floor(Math.random() * (N_CHUNKS - 2));
    if (c >= Math.min(a, b)) c++;
    if (c >= Math.max(a, b)) c++;
    w[key] = [a, b, c];
  });
  setWinners(w);

  // Sequence 1: gold line → BoC → sources → chunks → winners → sources
  // Pulse timing: 200ms before arrival for gold line (87%), 120ms for 0.6s lines (80%)
  // Chunk flash: reaction pattern — 300ms AFTER arrival, double flash
  at(() => { setPhase(1); setSearchLineDone(true); }, 100);       // gold line starts (1.5s CSS)
  at(() => setOpeningPulse(true), 1400);                           // 200ms before gold arrives at 1600
  at(() => setSearchGone(true), 1700);                             // line fades 100ms after arrival
  at(() => { setOpeningPulse(false); setPhase(2); setSourcesReady(true); }, 2100); // BoC→source (0.6s CSS)
  at(() => setGlowColor(true), 2580);                              // 120ms before sources arrive at 2700
  at(() => { setGlowColor(false); setPhase(3); }, 2800);          // source→chunk lines (0.6s CSS)
  at(() => setChunkFlash(true), 3700);                             // 300ms after chunks arrive at 3400
  at(() => setChunkFlash(false), 3900);                            // flash #1 off
  at(() => setChunkFlash(true), 4000);                             // flash #2 on
  at(() => { setChunkFlash(false); setPhase(5); }, 4200);         // winner→source colored (0.6s CSS)
  at(() => setGlowColor(true), 4680);                              // 120ms before winners arrive at 4800
  at(() => {
    setGlowColor(false);
    // Enter stretch 1 — sources pulse until Gate 1 opens
    if (retrievalStartedRef.current) {
      // Gate 1 already open — brief pause then advance
      at(() => startSequence2(), 200);
    } else {
      stretchPhaseRef.current = "gate1";
      stretchIntervalRef.current = setInterval(() => {
        setGlowColor(prev => !prev);
      }, 1200);
    }
  }, 4900);

// eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

**Effect 2 — Gate 1 watcher (advances stretch 1 → sequence 2):**

```typescript
useEffect(() => {
  if (retrievalStarted && stretchPhaseRef.current === "gate1") {
    stretchPhaseRef.current = null;
    if (stretchIntervalRef.current) {
      clearInterval(stretchIntervalRef.current);
      stretchIntervalRef.current = null;
    }
    setGlowColor(false);
    // Brief pause before advancing (prevents visual jump)
    at(() => startSequence2(), 200);
  }
}, [retrievalStarted]);
```

**The `startSequence2` function** (defined inside the component, above the effects):

```typescript
const startSequence2 = useCallback(() => {
  const act = active.length > 0 ? active : Object.keys(PALETTE).slice(0, 4);
  const perSource = Math.min(300, Math.floor(1500 / act.length));

  // Source→BoC colored lines start (0.6s CSS, arrive at t=600)
  setPhase(7);

  // Sequential per-source flash — starts 120ms before lines arrive (80% drawn)
  act.forEach((key, i) => {
    const t = 480 + i * perSource;
    at(() => setQPulse(PALETTE[key]?.hex ?? ACCENT), t);
    at(() => { setQPulse(null); setDismissedLines(prev => [...prev, key]); }, t + Math.min(200, perSource - 50));
  });

  const seqEnd = 480 + act.length * perSource;

  // After sequential: gold pulse, sources gone, return line
  at(() => setQPulse(ACCENT), seqEnd);
  at(() => setSourcesGone(true), seqEnd + 200);
  at(() => { setQPulse(null); setReturnLineDone(true); }, seqEnd + 400); // return line (0.6s CSS), arrives seqEnd+1000

  // Border flash 120ms before return line arrives (80% drawn)
  at(() => setBorderFlash(true), seqEnd + 880);

  // BoC fades 50ms after return line arrives
  at(() => setBocGone(true), seqEnd + 1050);

  // Enter stretch 2
  at(() => {
    if (isQueryDoneRef.current) {
      // Gate 2 already open — resolve immediately
      at(() => {
        setFading(true);
        onReadyToShow();
        at(() => onFadeComplete(), 1500);
      }, 200);
    } else {
      stretchPhaseRef.current = "gate2";
      let on = true;
      stretchIntervalRef.current = setInterval(() => {
        on = !on;
        setBorderFlash(on);
      }, 1500);
    }
  }, seqEnd + 1100);
}, [active, onReadyToShow, onFadeComplete]);
```

**Effect 3 — Gate 2 watcher (advances stretch 2 → resolve):**

Replace the existing `isQueryDone` watcher (the one that checks `waitingRef`). The new version:

```typescript
useEffect(() => {
  if (isQueryDone && stretchPhaseRef.current === "gate2") {
    stretchPhaseRef.current = null;
    if (stretchIntervalRef.current) {
      clearInterval(stretchIntervalRef.current);
      stretchIntervalRef.current = null;
    }
    setBorderFlash(true); // ensure border is on for final flash
    at(() => {
      setFading(true);
      onReadyToShow();
      at(() => onFadeComplete(), 1500);
    }, 200);
  }
}, [isQueryDone, onReadyToShow, onFadeComplete]);
```

- [ ] **Step 5: Remove stale state and refs**

Remove these state/refs that are no longer needed (the old waiting mechanism):
- `waitingRef` — replaced by `stretchPhaseRef`
- `pulseIntervalRef` — replaced by `stretchIntervalRef`
- The old `startWaitingPulse` function — replaced by stretch logic in sequence 2

Remove the old isQueryDone effect that checked `waitingRef` (around lines 145-153 of the original).

- [ ] **Step 6: Speed up CSS transition durations in the SVG**

Update inline style `transition` values throughout the JSX:

| Element | Old transition | New transition |
|---|---|---|
| Gold search line (`strokeDashoffset`) | `3s linear` | `1.5s linear` |
| BoC→source lines (`strokeDashoffset`) | `1s linear` | `0.6s linear` |
| Source→chunk lines (`strokeDashoffset`) | `1s linear` | `0.6s linear` |
| Winner chunk→source lines (`strokeDashoffset`) | `1s linear` | `0.6s linear` |
| Source→BoC colored lines (`strokeDashoffset`) | `1s linear` | `0.6s linear` |
| Return line (`strokeDashoffset`) | `1s linear` | `0.6s linear` |

These are all inline styles in the SVG `<line>` elements. Search for `"stroke-dashoffset 3s"` and `"stroke-dashoffset 1s"` and replace with the faster values.

- [ ] **Step 7: Remove dead code**

Delete:
- The `startWaitingPulse` function
- `waitingRef`
- `pulseIntervalRef`
- The old `useEffect` that watched `isQueryDone && waitingRef.current`

Ensure the cleanup effect still clears `stretchIntervalRef`:
```typescript
useEffect(() => {
  return () => {
    timers.current.forEach(clearTimeout);
    if (stretchIntervalRef.current) clearInterval(stretchIntervalRef.current);
  };
}, []);
```

- [ ] **Step 8: Verify TypeScript compiles**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 9: Test in browser — normal query (5 collections)**

```bash
cd apps/web && npm run dev
```

Open browser to localhost:3000/search. Submit a query with ~5 collections. Verify:
- Gold line draws in ~1.5s (faster than before)
- BoC pulses as gold line is ~87% drawn (~200ms before arrival)
- Source nodes glow as BoC→source lines are ~80% drawn (~120ms before arrival)
- Chunks flash AFTER source→chunk lines fully arrive (300ms delay, double flash)
- Source nodes glow again as winner→source lines are ~80% drawn
- Full outward+return trip plays in ~4.9s
- Sources pulse/glow for 0-1.6s (depending on HyDE speed)
- When retrieval starts: sources→BoC lines, sequential flash (300ms/source), return line, border flash
- Border pulses until results arrive
- Fade reveals results

- [ ] **Step 10: Test in browser — fast query (1-2 collections)**

Submit a query with only 1-2 collections selected. HyDE finishes in ~2-3s.
- Gate 1 opens at ~2-3s, animation reaches stretch at ~4.9s
- Animation plays naturally to stretch, then immediately advances (gate already open)
- Verify no visual glitch or jump — the 200ms minimum dwell prevents a snap

- [ ] **Step 11: Test in browser — slow query (10 collections, complex query)**

Submit a complex theological query with all 10 collections. HyDE takes ~6.5s.
- Source glow should pulse for ~1.6s before Gate 1 opens
- Sequential flash should be fast (150ms per source × 10 = 1.5s)
- Border flash appears as return line is 80% drawn (120ms before arrival)
- Border may pulse briefly or not at all (reranking takes 4-6s, close to sequence 2 hard content of ~3s)

- [ ] **Step 12: Test edge case — error during animation**

Trigger an error (e.g., disconnect network during search). Verify:
- Animation is unmounted cleanly (no lingering intervals)
- Error state shows correctly

- [ ] **Step 13: Commit**

```bash
git add apps/web/src/components/search/LoadingAnimation.tsx apps/web/src/components/search/SearchPage.tsx
git commit -m "feat: gate-based loading animation tied to SSE events — dynamic timing"
```

---

## Self-Review

**Spec coverage:**
- ✅ Gate 1 = `retrievalStarted` (SSE "searching" received) — after HyDE+embed
- ✅ Gate 2 = `isQueryDone` (SSE "done" received) — after reranking
- ✅ Pre-gate content: gold line + BoC→sources→chunks→winners→sources = ~4.9s
- ✅ Stretch 1: source glow pulse until Gate 1
- ✅ Post-gate content: sources→BoC + sequential flash + return line + border = ~2.5-3.1s (varies by collection count)
- ✅ Stretch 2: border pulse until Gate 2
- ✅ All CSS transitions sped up (3s→1.5s, 1s→0.6s)
- ✅ Anticipatory pulse preserves 80% drawn pattern (120ms before arrival for 0.6s lines)
- ✅ Gold line pulse at 87% drawn (200ms before arrival) — close to original 93%
- ✅ Chunk flash is reaction pattern: double flash starting 300ms AFTER arrival
- ✅ Sequential flash capped: `min(300, floor(1500/N))` ms per source
- ✅ Border flash at 80% of return line drawn (120ms before arrival)
- ✅ Edge case: gate already open when stretch reached → 200ms min dwell then advance
- ✅ Edge case: both gates open before stretch → advance through both immediately
- ✅ No backend changes required
- ✅ Same SVG elements, same visual story, just dynamic timing

**Placeholder scan:** None found — all code blocks are complete.

**Type consistency:**
- `retrievalStarted: boolean` in Props matches `searchPhase !== null || queryDone` in SearchPage ✓
- `stretchPhaseRef.current` typed as `"gate1" | "gate2" | null` ✓
- `startSequence2` is a `useCallback` — deps include `active`, `onReadyToShow`, `onFadeComplete` ✓
- `setGlowColor(prev => !prev)` — `glowColor` is `boolean` state ✓
