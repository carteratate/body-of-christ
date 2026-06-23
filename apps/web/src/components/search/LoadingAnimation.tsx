"use client";
import { useState, useRef, useEffect, useLayoutEffect } from "react";

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
  onReadyToShow: () => void;
  onFadeComplete: () => void;
}

export function LoadingAnimation({ collections, isQueryDone, onReadyToShow, onFadeComplete }: Props) {
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
  const waitingRef       = useRef(false);
  const pulseIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { isQueryDoneRef.current = isQueryDone; });

  // Resolve waiting pulse when query completes after animation finishes
  useEffect(() => {
    if (isQueryDone && waitingRef.current) {
      waitingRef.current = false;
      if (pulseIntervalRef.current) { clearInterval(pulseIntervalRef.current); pulseIntervalRef.current = null; }
      setFading(true);
      onReadyToShow();
      timers.current.push(setTimeout(() => onFadeComplete(), 1500));
    }
  }, [isQueryDone, onReadyToShow, onFadeComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      timers.current.forEach(clearTimeout);
      if (pulseIntervalRef.current) clearInterval(pulseIntervalRef.current);
    };
  }, []);

  function at(fn: () => void, ms: number) { timers.current.push(setTimeout(fn, ms)); }

  function startWaitingPulse() {
    waitingRef.current = true;
    let on = true;
    setBorderFlash(true);
    pulseIntervalRef.current = setInterval(() => { on = !on; setBorderFlash(on); }, 1500);
  }

  // Auto-start on mount — timing from animation_3s.tsx
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

    at(() => { setPhase(1); setSearchLineDone(true); }, 100);
    // Search line arrives at BoC at t=3100 — pulse 200ms early.
    at(() => setOpeningPulse(true),  2900);
    at(() => setSearchGone(true),    3200);
    at(() => { setOpeningPulse(false); setPhase(2); setSourcesReady(true); }, 5500);
    // BoC→source lines arrive at sources at t=6500 — glow 200ms early.
    // Outgoing source→chunk lines (phase 3) start 100ms after glow ends, matching original gap.
    at(() => setGlowColor(true),  6300);
    at(() => setGlowColor(false), 7300);
    at(() => setPhase(3), 7400);
    // Source→chunk lines arrive at chunks at t=8400 — flash ~600ms after arrival.
    at(() => setChunkFlash(true),   9000);
    at(() => setChunkFlash(false),  9500);
    at(() => setChunkFlash(true),   9900);
    at(() => setChunkFlash(false), 10400);
    // Chunk→source colored lines start 75ms after second flash ends.
    at(() => setPhase(5), 10475);
    // Chunk→source lines arrive at sources at t=11475 — glow 200ms early.
    // Outgoing source→BoC lines (phase 7) start 100ms after glow ends.
    at(() => setGlowColor(true),  11275);
    at(() => setGlowColor(false), 12275);
    at(() => setPhase(7), 12375);

    // Source→BoC lines arrive at BoC at t=13375 — pulse 200ms early.
    const bocPulseStart = 13175;
    act.forEach((key, i) => {
      const t = bocPulseStart + i * 800;
      at(() => setQPulse(PALETTE[key]?.hex ?? ACCENT), t);
      at(() => { setQPulse(null); setDismissedLines(prev => [...prev, key]); }, t + 200);
    });

    const goldT = bocPulseStart + act.length * 800;
    at(() => setQPulse(ACCENT), goldT);
    at(() => setQPulse(null),         goldT + 2650);
    at(() => setSourcesGone(true),    goldT + 800);
    at(() => setReturnLineDone(true), goldT + 2650);

    // Return line (1s CSS, starts goldT+2650) arrives at y=0 at goldT+3650.
    // Border flash blooms 50ms before arrival; bocGone fires 50ms after.
    at(() => setBorderFlash(true),  goldT + 3600);
    at(() => setBocGone(true),      goldT + 3700);

    // Results appear at goldT+4200 while border is fully bright.
    // The overlay then fades over 1.5s, dissolving border + background together.
    // onFadeComplete fires when fade is done so SearchPage unmounts the overlay.
    at(() => {
      setPhase(9);
      if (isQueryDoneRef.current) {
        setFading(true);
        onReadyToShow();
        at(() => onFadeComplete(), 1500);
      } else {
        startWaitingPulse();
      }
    }, goldT + 4200);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
              ? "stroke-dashoffset 3s linear, opacity 0.4s ease"
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
                transition: phase >= 2 ? "stroke-dashoffset 1s linear" : "none",
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
                transition: phase >= 3 ? "stroke-dashoffset 1s linear" : "none",
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
                  transition: phase >= 5 ? "stroke-dashoffset 1s linear" : "none",
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
                  ? "stroke-dashoffset 1s linear, opacity 0.3s ease-out"
                  : phase >= 7 ? "stroke-dashoffset 1s linear" : "none",
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
            transition: returnLineDone ? "stroke-dashoffset 1s linear" : "none",
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
