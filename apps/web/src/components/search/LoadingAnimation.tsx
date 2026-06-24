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
  "bible":                    { hex: "#d4885a", label: "Bible",          short: "Bib" },
  "catechism":                { hex: "#5b9bd4", label: "Catechism",      short: "CCC" },
  "church-fathers":           { hex: "#b070d4", label: "Ch. Fathers",    short: "CF"  },
  "encyclicals":              { hex: "#e8c040", label: "Encyclicals",    short: "Enc" },
  "summa":                    { hex: "#55cc88", label: "Summa",          short: "ST"  },
  "canon-law":                { hex: "#e84040", label: "Canon Law",      short: "CL"  },
  "medieval":                 { hex: "#90a0a8", label: "Medieval",       short: "Med" },
  "councils":                 { hex: "#60d4c8", label: "Councils",       short: "Cou" },
  "apostolic-exhortations":   { hex: "#4858c8", label: "Apost. Exhort.", short: "AE"  },
  "papal-documents":          { hex: "#b86080", label: "Papal Docs",     short: "PD"  },
};

const ACCENT = "#C4972A";
const N_CHUNKS: number = 15;

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
  isQueryDone: boolean;
  retrievalStarted: boolean;
  onReadyToShow: () => void;
  onFadeComplete: () => void;
}

export function LoadingAnimation({ collections, isQueryDone, retrievalStarted, onReadyToShow, onFadeComplete }: Props) {
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
  const availR       = Math.min(W / 2, H / 2) * 0.85;
  const k            = availR / OUTER_R_BASE;

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

  // ── Sequence 2 (post-gate-1) ──────────────────────────────────────────────

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

  // ── Effect 1: Sequence 1 (pre-gate, runs on mount) ────────────────────────

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

  // ── Effect 2: Gate 1 watcher (advances stretch 1 → sequence 2) ───────────

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
              ? "stroke-dashoffset 1.5s linear, opacity 0.4s ease"
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
                transition: phase >= 2 ? "stroke-dashoffset 0.6s linear" : "none",
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
                  ? "stroke-dashoffset 0.6s linear, opacity 0.3s ease-out"
                  : phase >= 7 ? "stroke-dashoffset 0.6s linear" : "none",
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
            transition: returnLineDone ? "stroke-dashoffset 0.6s linear" : "none",
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
          const sw     = glowColor ? 2.5 : 1.5;
          const filter = glowColor
            ? `drop-shadow(0 0 8px ${pal.hex})`
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

        {/* ── Body of Christ — center node ─────────────────────────────── */}
        {(() => {
          const pulsing  = qPulse !== null || openingPulse;
          const color    = qPulse ?? ACCENT;
          const bocTrans = openingPulse || qPulse === ACCENT
            ? "1.5s ease-out"
            : qPulse !== null ? "0.25s ease-in-out"
            :                   "1.0s ease-in-out";
          const filter = pulsing ? `drop-shadow(0 0 6px ${color})` : undefined;
          return (
            <g suppressHydrationWarning
              opacity={phase >= 1 && !bocGone ? 1 : 0}
              style={{ filter, transition: `opacity 0.4s ease, filter ${bocTrans}` }}
            >
              <circle suppressHydrationWarning
                cx={BOC_X} cy={BOC_Y} r={BOC_R}
                fill="var(--color-brand-bg)"
                stroke={color} strokeWidth={pulsing ? 3 : 1.5}
                style={{ transition: `stroke ${bocTrans}, stroke-width ${bocTrans}` }}
              />
              <text suppressHydrationWarning
                x={BOC_X} y={BOC_Y - fontSize * 0.9}
                textAnchor="middle" dominantBaseline="central"
                fontSize={fontSize} fontWeight={700} fill={color}
                style={{ userSelect: "none", transition: `fill ${bocTrans}` }}
              >
                Body of
              </text>
              <text suppressHydrationWarning
                x={BOC_X} y={BOC_Y + fontSize * 0.9}
                textAnchor="middle" dominantBaseline="central"
                fontSize={fontSize} fontWeight={700} fill={color}
                style={{ userSelect: "none", transition: `fill ${bocTrans}` }}
              >
                Christ
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
