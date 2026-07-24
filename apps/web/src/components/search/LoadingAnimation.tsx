"use client";
import { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";

// ── Helpers ───────────────────────────────────────────────────────────────

function hexToRgb(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}
function eucl(ax: number, ay: number, bx: number, by: number) {
  return Math.sqrt((bx - ax) ** 2 + (by - ay) ** 2);
}
function rim(fx: number, fy: number, tx: number, ty: number, r: number) {
  const d = eucl(fx, fy, tx, ty);
  if (d < 0.001) return { x: fx + r, y: fy };
  return { x: fx + (tx - fx) / d * r, y: fy + (ty - fy) / d * r };
}

// ── Palette ───────────────────────────────────────────────────────────────

const PALETTE: Record<string, { hex: string; label: string; short: string }> = {
  "bible":                    { hex: "#d4885a", label: "Bible",          short: "BI" },
  "catechism":                { hex: "#5b9bd4", label: "Catechism",      short: "CA" },
  "church-fathers":           { hex: "#b070d4", label: "Ch. Fathers",    short: "CF" },
  "encyclicals":              { hex: "#e8c040", label: "Encyclicals",    short: "EN" },
  "summa":                    { hex: "#55cc88", label: "Summa",          short: "ST" },
  "canon-law":                { hex: "#e84040", label: "Canon Law",      short: "CL" },
  "medieval":                 { hex: "#90a0a8", label: "Medieval",       short: "ME" },
  "councils":                 { hex: "#60d4c8", label: "Councils",       short: "CO" },
  "apostolic-exhortations":   { hex: "#4858c8", label: "Apost. Exhort.", short: "AE" },
  "papal-documents":          { hex: "#b86080", label: "Papal Docs",     short: "PD" },
};

const ACCENT = "#C4972A";
const N_CHUNKS: number = 15;

// Pick `count` distinct indices from [0, max) uniformly (partial Fisher–Yates).
// Returned sorted for stable rendering. `count` is clamped to [1, max].
function pickDistinct(count: number, max: number): number[] {
  const k = Math.max(1, Math.min(count, max));
  const pool = Array.from({ length: max }, (_, i) => i);
  for (let i = 0; i < k; i++) {
    const j = i + Math.floor(Math.random() * (max - i));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, k).sort((a, b) => a - b);
}

// ── Position helpers (parameterized — no global layout constants) ──────────

function getSourcePos(
  keys: string[],
  BOC_X: number, BOC_Y: number, SOURCE_RING: number,
) {
  const n = keys.length;
  return keys.map((key, i) => {
    const a = -Math.PI / 2 + (i / n) * 2 * Math.PI;
    return { key, x: BOC_X + SOURCE_RING * Math.cos(a), y: BOC_Y + SOURCE_RING * Math.sin(a) };
  });
}

function getChunkPos(
  sx: number, sy: number, key: string,
  BOC_X: number, BOC_Y: number, CHUNK_RING: number,
) {
  const base   = Math.atan2(sy - BOC_Y, sx - BOC_X);
  const spread = 1.75 * Math.PI;
  return Array.from({ length: N_CHUNKS }, (_, i) => {
    const t = N_CHUNKS === 1 ? 0 : i / (N_CHUNKS - 1) - 0.5;
    const a = base + t * spread;
    return { id: `${key}-${i}`, key, idx: i, x: sx + CHUNK_RING * Math.cos(a), y: sy + CHUNK_RING * Math.sin(a) };
  });
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props {
  collections: string[];
  quota: number;
  isQueryDone: boolean;
  retrievalStarted: boolean;
  onReadyToShow: () => void;
  onFadeComplete: () => void;
  // Footprint of the query bubble pinned at top-4/right-4 of this same container
  // (in that container's own pixel space). When present, the radial constellation's
  // size is capped so it never overlaps that corner — the two straight vertical
  // gold lines are unaffected and still reach the container's top/bottom edges.
  reservedTopRight?: { width: number; height: number } | null;
}

export function LoadingAnimation({ collections, quota, isQueryDone, retrievalStarted, onReadyToShow, onFadeComplete, reservedTopRight }: Props) {
  const active = collections.filter(k => k in PALETTE);

  // ── Container measurement ───────────────────────────────────────────────
  // useLayoutEffect fires before the first paint (client-only component),
  // so dims is correct by the time the browser paints.
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setDims({ w: width, h: height });
  }, []);

  // ── Adaptive layout ─────────────────────────────────────────────────────
  // All node sizes scale so the outermost chunk node fits within 85% of the
  // shorter half-dimension. This maximizes visible node size while guaranteeing
  // nothing clips regardless of viewport shape.
  const W = dims?.w ?? 800;
  const H = dims?.h ?? 600;
  const BOC_X = W / 2;
  const BOC_Y = H / 2;

  const OUTER_R_BASE = 140 + 32;
  let availR = Math.min(W / 2, H / 2) * 0.85;

  // Shrink the constellation's radius so it never reaches into the query bubble's
  // corner. The bubble sits at a fixed 16px inset from the top-right (top-4 right-4
  // in the same box this component measures), so its box is derivable from just its
  // width/height. Distance from the constellation's center to the nearest point of
  // that (padded) box gives the largest safe radius; the two straight vertical gold
  // lines don't use availR/k for their length and are unaffected by this.
  if (reservedTopRight && reservedTopRight.width > 0 && reservedTopRight.height > 0) {
    const INSET = 16;
    const PAD = 16;
    const rLeft   = W - INSET - reservedTopRight.width - PAD;
    const rTop    = INSET - PAD;
    const rRight  = W;
    const rBottom = INSET + reservedTopRight.height + PAD;
    const nearestX = Math.min(Math.max(BOC_X, rLeft), rRight);
    const nearestY = Math.min(Math.max(BOC_Y, rTop), rBottom);
    const dMin = eucl(BOC_X, BOC_Y, nearestX, nearestY);
    availR = Math.min(availR, Math.max(dMin, 60));
  }

  const k = availR / OUTER_R_BASE;

  const SOURCE_RING = 140 * k;
  const CHUNK_RING  = 32 * k;
  const BOC_R       = 32 * k;
  const SRC_R       = 16 * k;
  const CHK_R       = 5 * k;
  const fontSize    = Math.max(6, 7 * k);

  // Vertical lines span from center of SVG (= center of content area) to edges
  const SL_Y2  = BOC_Y + BOC_R;   // search line top (BoC south rim)
  const SL_LEN = H - SL_Y2;       // search line length
  const RL_Y1  = BOC_Y - BOC_R;   // return line start (BoC north rim)
  const RL_LEN = RL_Y1;            // return line length to y=0

  // ── Animation state ─────────────────────────────────────────────────────

  const [phase, setPhase]     = useState(0);
  const [winners, setWinners] = useState<Record<string, number[]>>({});

  const [searchLineDone, setSearchLineDone] = useState(false);
  const [searchGone, setSearchGone]         = useState(false);
  const [sourcesReady, setSourcesReady]     = useState(false);
  const [openingPulse, setOpeningPulse]     = useState(false);

  const [glowColor, setGlowColor]   = useState(false);
  const [chunkFlash, setChunkFlash] = useState(false);
  const [qPulse, setQPulse]         = useState<string | null>(null);

  const [sourcesGone, setSourcesGone]       = useState(false);
  const [dismissedLines, setDismissedLines] = useState<string[]>([]);
  const [returnLineDone, setReturnLineDone] = useState(false);
  const [bocGone, setBocGone]               = useState(false);
  const [borderFlash, setBorderFlash]       = useState(false);
  const [fading, setFading]                 = useState(false);

  const timers           = useRef<ReturnType<typeof setTimeout>[]>([]);
  const isQueryDoneRef   = useRef(isQueryDone);
  const retrievalStartedRef = useRef(retrievalStarted);
  const stretchPhaseRef = useRef<"gate1" | "gate2" | null>(null);
  const stretchIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { isQueryDoneRef.current = isQueryDone; });
  useEffect(() => { retrievalStartedRef.current = retrievalStarted; }, [retrievalStarted]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      timers.current.forEach(clearTimeout);
      if (stretchIntervalRef.current) clearInterval(stretchIntervalRef.current);
    };
  }, []);

  function at(fn: () => void, ms: number) { timers.current.push(setTimeout(fn, ms)); }

  // ── Sequence 2 (post-gate-1 → sequential flash → border) ─────────────────

  const startSequence2 = useCallback(() => {
    const act = active.length > 0 ? active : Object.keys(PALETTE).slice(0, 4);
    // 250ms fade-in + 250ms hold at full color = 500ms dwell, + 250ms fade-out
    // (see bocTrans below) = 750ms total, with zero rest — the next pulse's
    // onset fires the instant the previous fade finishes.
    const perSource = 750;

    // Source→BoC colored lines start (0.8s CSS, arrive at t=800)
    setPhase(7);

    // Sequential per-source flash — starts 100ms after lines arrive (let lines settle)
    // Line stays fully drawn through the flash; it only starts disappearing once
    // its BoC flash for that source has ended.
    act.forEach((key, i) => {
      const t = 1100 + i * perSource;
      at(() => setQPulse(PALETTE[key]?.hex ?? ACCENT), t);
      at(() => { setQPulse(null); setDismissedLines(prev => [...prev, key]); }, t + 500);
    });

    const seqEnd = 1100 + act.length * perSource;

    // After sequential: gold BoC pulse (0.5s fade-in + 800ms hold + 0.5s fade-out), sources gone, return line
    at(() => setQPulse(ACCENT), seqEnd);
    at(() => setSourcesGone(true), seqEnd + 800);
    at(() => { setQPulse(null); setReturnLineDone(true); }, seqEnd + 1300); // return line (0.8s CSS), arrives seqEnd+2100

    // Border flash 200ms before return line arrives (80% drawn)
    at(() => setBorderFlash(true), seqEnd + 1900);

    // BoC fades 50ms after return line arrives
    at(() => setBocGone(true), seqEnd + 2150);

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
    }, seqEnd + 2200);
  }, [active, onReadyToShow, onFadeComplete]);

  // ── Post-gate-1: chunks → winners back to sources → source glow → sequence 2 ───

  const startPostGate1 = useCallback(() => {
    setGlowColor(false);                                             // stop source pulse immediately
    at(() => setPhase(3), 100);                                      // source→chunk lines (0.6s CSS), arrive ~700
    at(() => setChunkFlash(true), 1100);                             // 400ms settle after chunks arrive, flash #1
    at(() => setChunkFlash(false), 1600);                            // flash #1: 500ms on (down from 600ms)
    at(() => setChunkFlash(true), 2100);                             // 500ms gap, flash #2 (down from 600ms)
    at(() => { setChunkFlash(false); setPhase(5); }, 2600);          // flash #2 done (500ms on), colored chunk→source lines start (0.6s CSS)
    at(() => setGlowColor(true), 3000);                              // 200ms before colored lines arrive at ~3200
    at(() => {
      setGlowColor(false);
      at(() => startSequence2(), 100);
    }, 4000);                                                        // 1000ms glow hold, matches Effect 1's source-glow
  }, [startSequence2]);

  // ── Effect 1: Sequence 1 (pre-gate, runs on mount) ────────────────────────

  useEffect(() => {
    const act = active.length > 0 ? active : Object.keys(PALETTE).slice(0, 4);

    const w: Record<string, number[]> = {};
    act.forEach(key => {
      // One winner per requested passage (quota): 3, 4, or 5 distinct bubbles.
      w[key] = pickDistinct(quota, N_CHUNKS);
    });
    setWinners(w);

    // Sequence 1: gold line → BoC → sources (GATE 1 STRETCH on sources) → chunks → winners → sources
    // All lines travel at 0.8s. BoC gold pulse: 0.75s fade-in + 1s hold. Source glow: 1000ms.
    at(() => { setPhase(1); setSearchLineDone(true); }, 100);       // gold line starts (0.8s CSS), arrives t=900
    at(() => setOpeningPulse(true), 700);                            // 200ms before gold arrives at 900
    at(() => setSearchGone(true), 1000);                             // line fades 100ms after arrival
    at(() => setOpeningPulse(false), 2450);                          // gold pulse off (0.75s fade-in + 1s hold = 1750ms dwell)
    at(() => { setPhase(2); setSourcesReady(true); }, 2850);        // BoC→source (0.8s CSS) starts 400ms after pulse-off, arrives t=3650
    at(() => setGlowColor(true), 3450);                              // 200ms before sources arrive at 3650
    at(() => setGlowColor(false), 4450);                             // source glow 1000ms
    // Enter Gate 1 stretch — source nodes pulse until HyDE + embed done
    at(() => {
      if (retrievalStartedRef.current) {
        startPostGate1();
      } else {
        stretchPhaseRef.current = "gate1";
        stretchIntervalRef.current = setInterval(() => {
          setGlowColor(prev => !prev);
        }, 1200);
      }
    }, 4650);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Effect 2: Gate 1 watcher (advances stretch 1 → sequence 2) ───────────

  useEffect(() => {
    if (retrievalStarted && stretchPhaseRef.current === "gate1") {
      stretchPhaseRef.current = null;
      if (stretchIntervalRef.current) {
        clearInterval(stretchIntervalRef.current);
        stretchIntervalRef.current = null;
      }
      setGlowColor(false);
      startPostGate1();
    }
  }, [retrievalStarted, startPostGate1]);

  // ── Effect 3: Gate 2 watcher (advances stretch 2 → resolve) ──────────────

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

  // ── Derived positions ────────────────────────────────────────────────────

  const act      = active.length > 0 ? active : Object.keys(PALETTE).slice(0, 4);
  const sources  = getSourcePos(act, BOC_X, BOC_Y, SOURCE_RING);
  const srcMap   = Object.fromEntries(sources.map(s => [s.key, s]));
  const allChunks = sources.flatMap(s => getChunkPos(s.x, s.y, s.key, BOC_X, BOC_Y, CHUNK_RING));

  // ── Render ────────────────────────────────────────────────────────────────
  // The container div is measured to compute the viewBox, so SVG units map
  // 1:1 to pixels (preserveAspectRatio="none" with matching viewBox is distortion-free).

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 z-10 bg-brand-bg"
      style={{
        opacity: fading ? 0 : 1,
        transition: fading ? "opacity 1.5s ease-out" : "none",
        pointerEvents: fading ? "none" : undefined,
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ position: "absolute", top: 0, left: 0, width: W, height: H }}
        preserveAspectRatio="none"
      >
        {/* ── Gold search→BoC line ─────────────────────────────────────────
            Starts at SVG bottom (= BottomBar top edge), draws upward over 3s,
            then fades when searchGone fires at 3.2s.                          */}
        <line
          x1={BOC_X} y1={H} x2={BOC_X} y2={SL_Y2}
          stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
          strokeDasharray={SL_LEN}
          opacity={searchLineDone && !searchGone ? 1 : 0}
          style={{
            strokeDashoffset: searchLineDone ? 0 : SL_LEN,
            transition: searchLineDone
              ? "stroke-dashoffset 0.8s linear, opacity 0.4s ease"
              : "none",
          }}
        />

        {/* ── BoC→source gold lines (phase 2) ──────────────────────────── */}
        {sources.map(s => {
          const a   = rim(BOC_X, BOC_Y, s.x, s.y, BOC_R);
          const b   = rim(s.x, s.y, BOC_X, BOC_Y, SRC_R);
          const len = eucl(a.x, a.y, b.x, b.y);
          return (
            <line key={`qs-${s.key}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
              strokeDasharray={len}
              opacity={phase >= 2 && phase < 5 && !sourcesGone ? 1 : 0}
              style={{
                strokeDashoffset: phase >= 2 ? 0 : len,
                transition: phase >= 2 ? "stroke-dashoffset 0.8s linear" : "none",
              }}
            />
          );
        })}

        {/* ── Source→chunk gold lines (phase 3) ──────────────────────────── */}
        {allChunks.map(c => {
          const s   = srcMap[c.key];
          const a   = rim(s.x, s.y, c.x, c.y, SRC_R);
          const b   = rim(c.x, c.y, s.x, s.y, CHK_R);
          const len = eucl(a.x, a.y, b.x, b.y);
          return (
            <line key={`sc-${c.id}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={ACCENT} strokeWidth={0.9} strokeLinecap="round"
              strokeDasharray={len}
              opacity={phase >= 3 && phase < 5 && !sourcesGone ? 1 : 0}
              style={{
                strokeDashoffset: phase >= 3 ? 0 : len,
                transition: phase >= 3 ? "stroke-dashoffset 0.6s linear" : "none",
              }}
            />
          );
        })}

        {/* ── Winner chunk→source colored lines (phase 5) ──────────────── */}
        {sources.flatMap(s => {
          const pal       = PALETTE[s.key];
          const wis       = winners[s.key] ?? [0];
          const srcChunks = allChunks.filter(c => c.key === s.key);
          return wis.map(wi => {
            const wc  = srcChunks[wi];
            if (!wc) return null;
            const a   = rim(wc.x, wc.y, s.x, s.y, CHK_R);
            const b   = rim(s.x, s.y, wc.x, wc.y, SRC_R);
            const len = eucl(a.x, a.y, b.x, b.y);
            return (
              <line key={`cs-${s.key}-${wi}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={pal.hex} strokeWidth={2} strokeLinecap="round"
                strokeDasharray={len}
                opacity={phase >= 5 && !sourcesGone ? 1 : 0}
                style={{
                  strokeDashoffset: phase >= 5 ? 0 : len,
                  transition: phase >= 5 ? "stroke-dashoffset 0.6s linear" : "none",
                }}
              />
            );
          });
        })}

        {/* ── Source→BoC colored lines (phase 7) ───────────────────────── */}
        {sources.map(s => {
          const pal = PALETTE[s.key];
          const a   = rim(s.x, s.y, BOC_X, BOC_Y, SRC_R);
          const b   = rim(BOC_X, BOC_Y, s.x, s.y, BOC_R);
          const len = eucl(a.x, a.y, b.x, b.y);
          return (
            <line key={`sq-${s.key}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={pal.hex} strokeWidth={2} strokeLinecap="round"
              strokeDasharray={len}
              opacity={phase >= 7 && !sourcesGone && !dismissedLines.includes(s.key) ? 1 : 0}
              style={{
                strokeDashoffset: phase >= 7 ? 0 : len,
                transition: dismissedLines.includes(s.key)
                  ? "stroke-dashoffset 0.8s linear, opacity 0.3s ease-out"
                  : phase >= 7 ? "stroke-dashoffset 0.8s linear" : "none",
              }}
            />
          );
        })}

        {/* ── Return line: BoC top → SVG top edge ──────────────────────── */}
        <line
          x1={BOC_X} y1={RL_Y1} x2={BOC_X} y2={0}
          stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
          strokeDasharray={RL_LEN}
          opacity={returnLineDone && !bocGone ? 1 : 0}
          style={{
            strokeDashoffset: returnLineDone ? 0 : RL_LEN,
            transition: returnLineDone ? "stroke-dashoffset 0.8s linear" : "none",
          }}
        />

        {/* ── Chunk circles ────────────────────────────────────────────── */}
        {allChunks.map(c => {
          const pal      = PALETTE[c.key];
          const rgb      = hexToRgb(pal.hex);
          const isWinner = (winners[c.key] ?? []).includes(c.idx);
          const gone     = (phase >= 5 && !isWinner) || sourcesGone;
          const flash    = chunkFlash && isWinner;
          return (
            <circle key={`chk-${c.id}`}
              cx={c.x} cy={c.y} r={CHK_R}
              fill={`rgba(${rgb},${flash ? 0.85 : 0.25})`}
              stroke={pal.hex} strokeWidth={flash ? 2.5 : 1}
              opacity={gone ? 0 : sourcesReady ? 1 : 0}
              style={{
                transition: "opacity 0.45s ease, fill 0.3s ease-in-out, stroke-width 0.3s ease-in-out",
                filter: flash ? `drop-shadow(0 0 5px ${pal.hex})` : undefined,
              }}
            />
          );
        })}

        {/* ── Source circles ───────────────────────────────────────────── */}
        {sources.map(s => {
          const pal    = PALETTE[s.key];
          const rgb    = hexToRgb(pal.hex);
          const sw     = glowColor ? 3.5 : 1.5;
          const filter = glowColor
            ? `drop-shadow(0 0 14px ${pal.hex})`
            : `drop-shadow(0 0 4px ${pal.hex}50)`;
          return (
            <g key={`src-${s.key}`}
              opacity={sourcesReady && !sourcesGone ? 1 : 0}
              style={{
                filter: sourcesReady && !sourcesGone ? filter : undefined,
                transition: `opacity ${sourcesGone ? "1.125s ease-in-out" : "0.8s ease-out"}, filter ${glowColor ? "0.8s ease-out" : "0.8s ease-in-out"}`,
              }}
            >
              <circle cx={s.x} cy={s.y} r={SRC_R}
                fill={`rgba(${rgb},0.2)`} stroke={pal.hex} strokeWidth={sw}
                style={{ transition: `stroke-width ${glowColor ? "0.8s ease-out" : "0.8s ease-in-out"}` }}
              />
              <text x={s.x} y={s.y} textAnchor="middle" dominantBaseline="central"
                fontSize={fontSize} fontWeight={700} fill={pal.hex}
                style={{ userSelect: "none" }}
              >
                {pal.short}
              </text>
            </g>
          );
        })}

        {/* ── TheoCorpus — center node: pulsing circle + static logo inside ─── */}
        {(() => {
          const pulsing  = qPulse !== null || openingPulse;
          const color    = qPulse ?? ACCENT;
          // Opening pulse: 0.75s fade-in, 0.75s fade-out. Final gold pulse
          // (qPulse===ACCENT): 0.5s fade-in, 0.5s fade-out. Colored per-source
          // pulses: 0.25s fade-in, 0.25s fade-out (see perSource/dwell above).
          // returnLineDone flips true in the same timer that ends the final
          // pulse, and sourcesReady is still false only during the opening
          // pulse — both used to tell the three fade-outs apart once qPulse
          // has already gone null (same shared state at that point otherwise).
          const bocTrans = openingPulse
            ? "0.75s ease-out"
            : qPulse === ACCENT ? "0.5s ease-out"
            : qPulse !== null ? "0.25s ease-in-out"
            : returnLineDone ? "0.5s ease-in-out"
            : !sourcesReady ? "0.75s ease-in-out"
            :                  "0.25s ease-in-out";
          // Two stacked drop-shadows — a tighter bright core plus a much wider
          // soft bloom — read as a large halo rather than a tight glow ring.
          const filter = pulsing ? `drop-shadow(0 0 22px ${color}) drop-shadow(0 0 48px ${color})` : undefined;

          // "TC" label is static — fixed color, no glow, no transitions —
          // independent of the circle's pulse state, sized proportionally to BOC_R.
          const logoFontSize = BOC_R * 0.55;

          return (
            <g suppressHydrationWarning opacity={phase >= 1 && !bocGone ? 1 : 0} style={{ transition: "opacity 0.4s ease" }}>
              <g suppressHydrationWarning style={{ filter, transition: `filter ${bocTrans}` }}>
                <circle suppressHydrationWarning
                  cx={BOC_X} cy={BOC_Y} r={BOC_R}
                  fill="var(--color-brand-bg)"
                  stroke={color} strokeWidth={pulsing ? 3 : 1.5}
                  style={{ transition: `stroke ${bocTrans}, stroke-width ${bocTrans}` }}
                />
              </g>
              <text suppressHydrationWarning
                x={BOC_X} y={BOC_Y}
                textAnchor="middle" dominantBaseline="central"
                fontSize={logoFontSize} fontWeight={700} fill={ACCENT}
                style={{ userSelect: "none" }}
              >
                TC
              </text>
            </g>
          );
        })()}
      </svg>

      {/* Gold border — 8px inset box-shadow exactly frames the content area */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          boxShadow: `inset 0 0 0 8px ${ACCENT}`,
          opacity: borderFlash ? 1 : 0,
          transition: `opacity ${borderFlash ? "0.5s ease-in" : "1.5s ease-out"}`,
        }}
      />
    </div>
  );
}
