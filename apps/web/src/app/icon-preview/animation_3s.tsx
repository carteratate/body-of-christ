"use client";
// Loading screen animation draft — delete after finalizing
import { useState, useRef, useEffect } from "react";

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Data ──────────────────────────────────────────────────────────────────────

const PALETTE = [
  { key: "bible",       label: "Bible",       short: "Bib", hex: "#d4885a" },
  { key: "catechism",   label: "Catechism",   short: "CCC", hex: "#5b9bd4" },
  { key: "summa",       label: "Summa",       short: "ST",  hex: "#55cc88" },
  { key: "encyclicals", label: "Encyclicals", short: "Enc", hex: "#e8c040" },
  { key: "ch-fathers",  label: "Ch. Fathers", short: "CF",  hex: "#b070d4" },
  { key: "canon-law",   label: "Canon Law",   short: "CL",  hex: "#e84040" },
];
const palMap = Object.fromEntries(PALETTE.map(p => [p.key, p]));
const ACCENT = "#C4972A";

// ── Canvas / layout constants ─────────────────────────────────────────────────

const W = 660;
const H = 520;

// Body of Christ — center node
const BOC_X = W / 2;   // 330
const BOC_Y = 240;
const BOC_R = 42;

// Source / chunk rings
const SRC_R       = 21;
const CHK_R       = 7;
const SOURCE_RING = 140;
const CHUNK_RING  = 62;
const N_CHUNKS: number = 10;

// Search bar — rendered at bottom, fades on submit
const SB_W      = 296;
const SB_H      = 44;
const SB_CY     = H - 64;                       // vertical center = 456
const SB_X      = BOC_X - SB_W / 2;             // left edge = 182
const SB_BTN_CX = SB_X + SB_W - SB_H / 2;      // send button center x
const SB_BTN_CY = SB_CY;
const SB_BTN_R  = 17;

// Search→BoC gold line (vertical, along BOC_X)
const SL_Y1  = SB_CY - SB_H / 2;               // top of search bar = 434
const SL_Y2  = BOC_Y + BOC_R;                   // bottom rim of BoC = 282
const SL_LEN = SL_Y1 - SL_Y2;                  // 152 px

// Query bubble — speech bubble at top right
// Wide enough that the return line at x=BOC_X=330 passes through it (z-order "underneath")
const QB_W  = 330;
const QB_H  = 32;
const QB_YT = 8;                                 // top edge
const QB_X  = W - QB_W - 12;                    // left edge = 318 (line at 330 passes through)
const QB_YB = QB_YT + QB_H;                     // bottom edge = 40

// Return line — BoC top rim straight to top of canvas (y=0)
const RL_Y1  = BOC_Y - BOC_R;                   // top rim of BoC = 198
const RL_Y2  = 0;                               // very top of canvas
const RL_LEN = RL_Y1 - RL_Y2;                  // 198 px

// Result cards — appear after border flash
const CARD_H = 22;
const CARD_Y = QB_YT + QB_H + 8;               // y = 44

// ── Position helpers ──────────────────────────────────────────────────────────

function getSourcePos(keys: string[]) {
  const n = keys.length;
  return keys.map((key, i) => {
    const a = -Math.PI / 2 + (i / n) * 2 * Math.PI;
    return { key, x: BOC_X + SOURCE_RING * Math.cos(a), y: BOC_Y + SOURCE_RING * Math.sin(a) };
  });
}

function getChunkPos(sx: number, sy: number, key: string) {
  const base   = Math.atan2(sy - BOC_Y, sx - BOC_X);
  const spread = 0.85 * Math.PI;
  return Array.from({ length: N_CHUNKS }, (_, i) => {
    const t = N_CHUNKS === 1 ? 0 : i / (N_CHUNKS - 1) - 0.5;
    const a = base + t * spread;
    return { id: `${key}-${i}`, key, idx: i, x: sx + CHUNK_RING * Math.cos(a), y: sy + CHUNK_RING * Math.sin(a) };
  });
}

// ── Animation phases ──────────────────────────────────────────────────────────
// 0  idle
// 1  search→BoC line drawing; BoC fades in
// 2  BoC→source gold lines drawing             (STEP 3)
// 3  source→chunk gold lines drawing           (STEP 5)
// 5  non-winners fade; chunk→source colored    (STEP 7)
// 7  source→BoC colored lines drawing          (STEP 9)
// 9  complete
//
// Separate booleans control all other steps.

// ── Component ─────────────────────────────────────────────────────────────────

export default function LoadingPreview() {
  const [active, setActive]   = useState(["bible", "catechism", "ch-fathers", "canon-law"]);
  const [phase, setPhase]     = useState(0);
  const [winners, setWinners] = useState<Record<string, number[]>>({});

  // Pre-animation
  const [searchLineDone, setSearchLineDone] = useState(false); // search→BoC drawn
  const [searchGone, setSearchGone]         = useState(false); // bar faded out
  const [sourcesReady, setSourcesReady]     = useState(false); // sources + chunks visible
  const [openingPulse, setOpeningPulse]     = useState(false); // BoC opening gold pulse

  // Mid-animation
  const [glowColor, setGlowColor]     = useState(false);           // source color pulse (steps 4 + 8)
  const [chunkFlash, setChunkFlash]   = useState(false);           // winner chunk flash (step 6)
  const [qPulse, setQPulse]           = useState<string | null>(null); // BoC color/gold pulses
  const [goldFading, setGoldFading]   = useState(false);           // true for 450ms after gold pulse ends → 0.4s ease-out fall

  // Post-animation
  const [sourcesGone, setSourcesGone]       = useState(false); // all nodes vanish (step 12)
  const [returnLineDone, setReturnLineDone] = useState(false); // BoC→top line drawn
  const [bocGone, setBocGone]               = useState(false); // BoC + return line vanish at flash start
  const [borderFlash, setBorderFlash]       = useState(false);
  const [resultsIn, setResultsIn]           = useState(false);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);

  function clearAll() { timers.current.forEach(clearTimeout); timers.current = []; }
  function at(fn: () => void, ms: number) { timers.current.push(setTimeout(fn, ms)); }

  function reset() {
    clearAll();
    setPhase(0); setWinners({});
    setSearchLineDone(false); setSearchGone(false); setSourcesReady(false); setOpeningPulse(false);
    setGlowColor(false); setChunkFlash(false); setQPulse(null); setGoldFading(false);
    setSourcesGone(false); setReturnLineDone(false); setBocGone(false); setBorderFlash(false); setResultsIn(false);
  }

  function toggleSource(key: string) {
    if (phase > 0 && phase < 9) return;
    setActive(p => p.includes(key) ? (p.length > 1 ? p.filter(k => k !== key) : p) : [...p, key]);
    reset();
  }

  function startAnimation() {
    clearAll();
    setPhase(0);
    setSearchLineDone(false); setSearchGone(false); setSourcesReady(false); setOpeningPulse(false);
    setGlowColor(false); setChunkFlash(false); setQPulse(null); setGoldFading(false);
    setSourcesGone(false); setReturnLineDone(false); setBocGone(false); setBorderFlash(false); setResultsIn(false);

    const w: Record<string, number[]> = {};
    active.forEach(k => {
      const a = Math.floor(Math.random() * N_CHUNKS);
      let b = Math.floor(Math.random() * (N_CHUNKS - 1));
      if (b >= a) b++;
      w[k] = [a, b];
    });
    setWinners(w);

    // ── STEP 1: search→BoC gold line draws; BoC fades in (3s) ────────
    at(() => { setPhase(1); setSearchLineDone(true); }, 100);

    // ── STEP 2: BoC pulse fires 700ms before line completes ───────────
    at(() => setOpeningPulse(true),  2400);  // line math-arrives at 3100ms
    at(() => setSearchGone(true),    3200);
    at(() => setOpeningPulse(false), 5500);  // 2600ms on — 1.5s ease-out rise, hold, 1.0s fall

    // ── STEP 3: sources start fading in as opening pulse ends ─────────
    at(() => { setPhase(2); setSourcesReady(true); }, 5500);

    // ── STEP 4: source pulse fires 500ms before BoC→source lines arrive
    // Lines: start 5500 + 3000ms → math-arrive 8500
    at(() => setGlowColor(true),  8000);
    at(() => setGlowColor(false), 9000);  // 1000ms single pulse (0.8s ease-out transition)

    // ── STEP 5: source→chunk gold lines draw (3s) ────────────────────
    at(() => setPhase(3), 9100);

    // ── STEP 6: winner chunk pulses (children keep their 75ms buffer) ──
    // Lines: start 9100 + 3000ms → math-arrive 12100
    at(() => setChunkFlash(true),  12175);
    at(() => setChunkFlash(false), 12675);
    at(() => setChunkFlash(true),  13075);
    at(() => setChunkFlash(false), 13575);

    // ── STEP 7: others fade; colored line chunk→source draws (3s) ────
    at(() => setPhase(5), 13650);

    // ── STEP 8: source pulse fires 500ms before chunk→source lines arrive ─
    // Lines: start 13650 + 3000ms → math-arrive 16650
    at(() => setGlowColor(true),  16150);
    at(() => setGlowColor(false), 17150);  // 1000ms single pulse

    // ── STEP 9: source→BoC colored lines draw (3s) ───────────────────
    at(() => setPhase(7), 17250);

    // ── STEP 10: BoC cycles through each source's color ──────────────
    // Lines: start 17250 + 3000ms → math-arrive 20250; fire 300ms early
    const bocPulseStart = 19950;
    active.forEach((key, i) => {
      const t = bocPulseStart + i * 800;
      at(() => setQPulse(palMap[key].hex), t);
      at(() => setQPulse(null),            t + 200);
    });

    // ── STEP 11: second gold pulse — same as first: 2650ms on, 1.5s ease-out rise,
    //    1.0s ease-in-out fall (natural resting bocTrans once qPulse→null)
    const goldT = bocPulseStart + active.length * 800;
    at(() => setQPulse(ACCENT), goldT);
    at(() => setQPulse(null),   goldT + 2650);

    // ── STEP 12: sources fade as soon as second gold's 1.5s ease-out completes;
    //    return line draws once gold pulse finishes
    at(() => setSourcesGone(true),    goldT + 800);
    at(() => setReturnLineDone(true), goldT + 2650);

    // ── STEP 13: flash fires the instant the return line reaches y=0 ──
    // Return line starts goldT+2650, travels 3s → arrives goldT+5650
    at(() => { setBocGone(true); setBorderFlash(true); }, goldT + 5650);
    at(() => setBorderFlash(false), goldT + 6650);  // 1000ms flash

    // ── STEP 14: results appear as border flash begins fading ─────────
    at(() => setResultsIn(true), goldT + 6650);

    at(() => setPhase(9), goldT + 7150);
  }

  // ── Derived ──────────────────────────────────────────────────────────────

  const sources   = getSourcePos(active);
  const sourceMap = Object.fromEntries(sources.map(s => [s.key, s]));
  const allChunks = sources.flatMap(s => getChunkPos(s.x, s.y, s.key));
  const running   = phase > 0 && phase < 9;

  const n        = active.length;
  const cardW    = Math.floor((600 - (n - 1) * 8) / n);
  const cardX0   = (W - (n * cardW + (n - 1) * 8)) / 2;

  const status =
    phase === 9     ? "Complete" :
    returnLineDone  ? "Delivering results…" :
    phase >= 7      ? "Returning results…" :
    phase >= 5      ? "Selecting best matches…" :
    phase >= 3      ? "Scanning passages…" :
    phase >= 2      ? "Searching sources…" :
    sourcesReady    ? "Connected…" :
    phase >= 1      ? "Routing query…" :
                      "Ready";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ background: "#06080D", minHeight: "100vh", padding: "2rem", color: "#EAE6DC", fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: "1.3rem", fontWeight: 700, marginBottom: "0.4rem" }}>Loading Screen — Animation Draft</h1>
      <p style={{ color: "#7A8099", fontSize: "0.82rem", marginBottom: "1.2rem" }}>Toggle sources, then click the send button to start.</p>

      {/* Source toggles (meta-controls outside SVG) */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "1.4rem" }}>
        {PALETTE.map(col => {
          const isOn = active.includes(col.key);
          const rgb  = hexToRgb(col.hex);
          return (
            <button key={col.key} onClick={() => toggleSource(col.key)} style={{
              padding: "3px 11px", borderRadius: "99px", fontSize: "11px",
              border:     `1px solid rgba(${rgb},${isOn ? 0.75 : 0.2})`,
              background: isOn ? `rgba(${rgb},0.22)` : `rgba(${rgb},0.05)`,
              color:      isOn ? col.hex : `rgba(${rgb},0.4)`,
              cursor: running ? "default" : "pointer", transition: "all 0.2s",
            }}>
              {col.label}
            </button>
          );
        })}
      </div>

      {/* Canvas */}
      <div style={{ display: "inline-block", background: "#0D1828", borderRadius: "14px", border: "1px solid rgba(255,255,255,0.07)" }}>
        <svg width={W} height={H}>

          {/* ── SEARCH→BoC gold line ────────────────────────────────── */}
          <line
            x1={BOC_X} y1={SL_Y1} x2={BOC_X} y2={SL_Y2}
            stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
            strokeDasharray={SL_LEN}
            strokeDashoffset={searchLineDone ? 0 : SL_LEN}
            opacity={searchLineDone && !searchGone ? 1 : 0}
            style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.4s ease" }}
          />

          {/* ── BoC→source gold lines (phase 2 / STEP 3) ───────────── */}
          {sources.map(s => {
            const a   = rim(BOC_X, BOC_Y, s.x, s.y, BOC_R);
            const b   = rim(s.x, s.y, BOC_X, BOC_Y, SRC_R);
            const len = eucl(a.x, a.y, b.x, b.y);
            return (
              <line key={`qs-${s.key}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
                strokeDasharray={len}
                strokeDashoffset={phase >= 2 ? 0 : len}
                opacity={phase >= 2 && phase < 5 && !sourcesGone ? 1 : 0}
                style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.5s ease" }}
              />
            );
          })}

          {/* ── source→chunk gold lines (phase 3 / STEP 5) ─────────── */}
          {allChunks.map(c => {
            const s   = sourceMap[c.key];
            const a   = rim(s.x, s.y, c.x, c.y, SRC_R);
            const b   = rim(c.x, c.y, s.x, s.y, CHK_R);
            const len = eucl(a.x, a.y, b.x, b.y);
            return (
              <line key={`sc-${c.id}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={ACCENT} strokeWidth={0.9} strokeLinecap="round"
                strokeDasharray={len}
                strokeDashoffset={phase >= 3 ? 0 : len}
                opacity={phase >= 3 && phase < 5 && !sourcesGone ? 1 : 0}
                style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.5s ease" }}
              />
            );
          })}

          {/* ── winner chunk→source colored lines (phase 5 / STEP 7) ── */}
          {sources.flatMap(s => {
            const pal      = palMap[s.key];
            const wis      = winners[s.key] ?? [0];
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
                  strokeDashoffset={phase >= 5 ? 0 : len}
                  opacity={phase >= 5 && !sourcesGone ? 1 : 0}
                  style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.4s ease" }}
                />
              );
            });
          })}

          {/* ── source→BoC colored lines (phase 7 / STEP 9) ────────── */}
          {sources.map(s => {
            const pal = palMap[s.key];
            const a   = rim(s.x, s.y, BOC_X, BOC_Y, SRC_R);
            const b   = rim(BOC_X, BOC_Y, s.x, s.y, BOC_R);
            const len = eucl(a.x, a.y, b.x, b.y);
            return (
              <line key={`sq-${s.key}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={pal.hex} strokeWidth={2} strokeLinecap="round"
                strokeDasharray={len}
                strokeDashoffset={phase >= 7 ? 0 : len}
                opacity={phase >= 7 && !sourcesGone ? 1 : 0}
                style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.4s ease" }}
              />
            );
          })}

          {/* ── Return line: BoC→query bubble (STEP 12) ─────────────── */}
          <line
            x1={BOC_X} y1={RL_Y1} x2={BOC_X} y2={RL_Y2}
            stroke={ACCENT} strokeWidth={1.5} strokeLinecap="round"
            strokeDasharray={RL_LEN}
            strokeDashoffset={returnLineDone ? 0 : RL_LEN}
            opacity={returnLineDone && !bocGone ? 1 : 0}
            style={{ transition: "stroke-dashoffset 3s ease-in-out, opacity 0.3s ease" }}
          />

          {/* ── Chunk circles ────────────────────────────────────────── */}
          {allChunks.map(c => {
            const pal      = palMap[c.key];
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
                  filter: flash ? `drop-shadow(0 0 6px ${pal.hex})` : undefined,
                }}
              />
            );
          })}

          {/* ── Source circles ───────────────────────────────────────── */}
          {sources.map(s => {
            const pal    = palMap[s.key];
            const rgb    = hexToRgb(pal.hex);
            const sw     = glowColor ? 2.5 : 1.5;
            const filter = glowColor
              ? `drop-shadow(0 0 8px ${pal.hex})`
              : `drop-shadow(0 0 5px ${pal.hex}50)`;
            return (
              <g key={`src-${s.key}`}
                opacity={sourcesReady && !sourcesGone ? 1 : 0}
                style={{ filter: sourcesReady && !sourcesGone ? filter : undefined, transition: `opacity ${sourcesGone ? "2.25s ease-in-out" : "3.25s ease-in-out"}, filter ${glowColor ? "0.8s ease-out" : "0.8s ease-in-out"}` }}
              >
                <circle cx={s.x} cy={s.y} r={SRC_R}
                  fill={`rgba(${rgb},0.2)`}
                  stroke={pal.hex} strokeWidth={sw}
                  style={{ transition: `stroke-width ${glowColor ? "0.8s ease-out" : "0.8s ease-in-out"}` }}
                />
                <text x={s.x} y={s.y} textAnchor="middle" dominantBaseline="central"
                  fontSize={9} fontWeight={700} fill={pal.hex}
                  style={{ userSelect: "none" }}
                >
                  {pal.short}
                </text>
              </g>
            );
          })}

          {/* ── Body of Christ — center node ─────────────────────────── */}
          {(() => {
            const pulsing = qPulse !== null || openingPulse;
            const color   = qPulse ?? ACCENT;
            const done    = phase >= 9 && !pulsing;
            const bocTrans = openingPulse || qPulse === ACCENT
              ? "1.5s ease-out"
              : qPulse !== null ? "0.25s ease-in-out"
              :                   "1.0s ease-in-out";
            const filter  = pulsing
              ? `drop-shadow(0 0 4px ${color})`
              : done ? `drop-shadow(0 0 8px ${ACCENT}90)` : undefined;
            return (
              <g suppressHydrationWarning opacity={phase >= 1 && !bocGone ? 1 : 0}
                style={{ filter, transition: `opacity 0.4s ease, filter ${bocTrans}` }}>
                <circle suppressHydrationWarning cx={BOC_X} cy={BOC_Y} r={BOC_R}
                  fill="#0A1220"
                  stroke={color} strokeWidth={pulsing ? 3.5 : 2}
                  style={{ transition: `stroke ${bocTrans}, stroke-width ${bocTrans}` }}
                />
                <text suppressHydrationWarning x={BOC_X} y={BOC_Y - 7}
                  textAnchor="middle" dominantBaseline="central"
                  fontSize={9} fontWeight={700} fill={color}
                  style={{ userSelect: "none", transition: `fill ${bocTrans}` }}
                >
                  Body of
                </text>
                <text suppressHydrationWarning x={BOC_X} y={BOC_Y + 7}
                  textAnchor="middle" dominantBaseline="central"
                  fontSize={9} fontWeight={700} fill={color}
                  style={{ userSelect: "none", transition: `fill ${bocTrans}` }}
                >
                  Christ
                </text>
              </g>
            );
          })()}

          {/* ── Query speech bubble — top right, line passes under it ── */}
          <g opacity={searchGone ? 1 : 0} style={{ transition: "opacity 0.5s ease" }}>
            {/* Bubble body */}
            <rect x={QB_X} y={QB_YT} width={QB_W} height={QB_H} rx={QB_H / 2}
              fill="#1c2d45" stroke="rgba(196,151,42,0.5)" strokeWidth={1}
            />
            {/* Tail — small notch at bottom-left pointing toward search bar */}
            <polygon
              points={`${QB_X + 18},${QB_YB} ${QB_X + 32},${QB_YB} ${QB_X + 12},${QB_YB + 10}`}
              fill="#1c2d45"
            />
            <text x={QB_X + 20} y={QB_YT + QB_H / 2 + 1}
              dominantBaseline="central" fontSize={10} fill="#EAE6DC"
              style={{ userSelect: "none" }}
            >
              What is the nature of grace?
            </text>
          </g>

          {/* ── Result cards (STEP 14) ────────────────────────────────── */}
          {active.map((key, i) => {
            const pal = palMap[key];
            const rgb = hexToRgb(pal.hex);
            const cx  = cardX0 + i * (cardW + 8);
            return (
              <g key={`card-${key}`}
                opacity={resultsIn ? 1 : 0}
                style={{ transition: `opacity 0.4s ease ${i * 80}ms` }}
              >
                <rect x={cx} y={CARD_Y} width={cardW} height={CARD_H} rx={5}
                  fill={`rgba(${rgb},0.12)`} stroke={`rgba(${rgb},0.45)`} strokeWidth={1}
                />
                <rect x={cx} y={CARD_Y} width={4} height={CARD_H} rx={2} fill={pal.hex} />
                <text x={cx + 10} y={CARD_Y + CARD_H / 2 + 1}
                  dominantBaseline="central"
                  fontSize={8.5} fontWeight={600} fill={pal.hex}
                  style={{ userSelect: "none" }}
                >
                  {pal.label}
                </text>
              </g>
            );
          })}

          {/* ── Search bar (fades out on submit) ─────────────────────── */}
          <g
            opacity={searchGone ? 0 : 1}
            style={{ transition: "opacity 0.5s ease", pointerEvents: searchGone ? "none" : "auto" }}
          >
            <rect x={SB_X} y={SB_CY - SB_H / 2} width={SB_W} height={SB_H} rx={SB_H / 2}
              fill="#172232" stroke="rgba(196,151,42,0.4)" strokeWidth={1.5}
            />
            <text x={SB_X + 20} y={SB_CY + 1} dominantBaseline="central"
              fontSize={12} fill="#7A8099" style={{ userSelect: "none" }}
            >
              Search the corpus…
            </text>
            <circle cx={SB_BTN_CX} cy={SB_BTN_CY} r={SB_BTN_R}
              fill={running ? "rgba(196,151,42,0.4)" : ACCENT}
              style={{ cursor: running ? "default" : "pointer", transition: "fill 0.2s" }}
              onClick={running ? undefined : startAnimation}
            />
            <text x={SB_BTN_CX} y={SB_BTN_CY + 1} textAnchor="middle" dominantBaseline="central"
              fontSize={14} fontWeight={700}
              fill={running ? "#7A8099" : "#0D1828"}
              style={{ userSelect: "none", pointerEvents: "none" }}
            >
              ↑
            </text>
          </g>

          {/* ── Border flash rect (on top of everything) ─────────────── */}
          <rect x={2} y={2} width={W - 4} height={H - 4}
            fill="none" stroke={ACCENT} strokeWidth={5}
            opacity={borderFlash ? 1 : 0}
            style={{ transition: `opacity ${borderFlash ? "0.5s ease-in" : "1.5s ease-out"}`, pointerEvents: "none" }}
          />

        </svg>
      </div>

      {/* External controls */}
      <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "14px" }}>
        {(phase === 0 || phase === 9) && (
          <button onClick={startAnimation} style={{
            background: ACCENT, color: "#0D1828", border: "none",
            borderRadius: "6px", padding: "7px 20px", fontSize: "12px",
            fontWeight: 700, cursor: "pointer",
          }}>
            {phase === 9 ? "Replay" : "Start"}
          </button>
        )}
        <span style={{ fontSize: "11px", color: "#7A8099", minWidth: "180px" }}>{status}</span>
      </div>
    </div>
  );
}
