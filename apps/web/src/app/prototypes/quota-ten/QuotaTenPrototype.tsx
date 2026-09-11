"use client";

// Three outward pulse variants, switchable via ?variant=, with shape kept separate.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { COLLECTIONS } from "@/lib/collections";
import styles from "./prototype.module.css";

const VARIANTS = [
  { key: "a", name: "Single halo", note: "One clean gold halo expands from the fixed boundary and fades." },
  { key: "b", name: "Twin ripple", note: "Two fine gold rings follow each other outward in one compact pulse." },
  { key: "c", name: "Soft bloom", note: "A broad glow blooms from the boundary without drawing a second hard ring." },
] as const;

type VariantKey = (typeof VARIANTS)[number]["key"];
type ShapeKey = "joined" | "circle";

function normalizeVariant(value: string | null): VariantKey {
  return VARIANTS.some((item) => item.key === value) ? value as VariantKey : "a";
}

function normalizeShape(value: string | null): ShapeKey {
  return value === "circle" ? "circle" : "joined";
}

function relativeLuminance(hex: string) {
  const channels = hex.slice(1).match(/.{2}/g)?.map((value) => {
    const channel = Number.parseInt(value, 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }) ?? [0, 0, 0];
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

export function QuotaTenPrototype() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const variant = normalizeVariant(searchParams.get("variant"));
  const shape = normalizeShape(searchParams.get("shape"));
  const [activeKeys, setActiveKeys] = useState<string[]>(["bible"]);
  const [quota, setQuota] = useState(5);
  const [pulseKey, setPulseKey] = useState(0);

  const focused = activeKeys.length === 1;
  const selectedCollection = useMemo(
    () => COLLECTIONS.find((collection) => collection.key === activeKeys[0]) ?? COLLECTIONS[0],
    [activeKeys],
  );
  const selectedForeground = relativeLuminance(selectedCollection.hex) > 0.31
    ? "var(--color-brand-bg)"
    : "var(--color-brand-primary)";
  const current = VARIANTS.find((item) => item.key === variant) ?? VARIANTS[0];

  const replaceParams = useCallback((updates: Record<string, string>) => {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => params.set(key, value));
    router.replace(`?${params.toString()}`);
  }, [router, searchParams]);

  const chooseVariant = useCallback((next: VariantKey) => {
    replaceParams({ variant: next });
    setQuota(10);
    setPulseKey((key) => key + 1);
  }, [replaceParams]);

  const cycle = useCallback((direction: -1 | 1) => {
    const index = VARIANTS.findIndex((item) => item.key === variant);
    chooseVariant(VARIANTS[(index + direction + VARIANTS.length) % VARIANTS.length].key);
  }, [chooseVariant, variant]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, [contenteditable='true']")) return;
      if (event.key === "ArrowLeft") cycle(-1);
      if (event.key === "ArrowRight") cycle(1);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cycle]);

  function toggleCollection(key: string) {
    setActiveKeys((currentKeys) => {
      const next = currentKeys.includes(key)
        ? currentKeys.filter((item) => item !== key)
        : [...currentKeys, key];
      if (next.length !== 1 && quota === 10) setQuota(5);
      return next.length === 0 ? currentKeys : next;
    });
  }

  function selectQuota(next: number) {
    if (next === 10 && !focused) return;
    if (next === 10 && quota !== 10) setPulseKey((key) => key + 1);
    setQuota(next);
  }

  function replayPulse() {
    setQuota(10);
    setPulseKey((key) => key + 1);
  }

  const prototypeStyle = {
    "--collection-color": selectedCollection.color,
    "--selected-foreground": selectedForeground,
  } as React.CSSProperties;

  return (
    <main className={styles.page} style={prototypeStyle}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Interaction prototype</p>
          <h1>Focused quota pulse</h1>
        </div>
        <div className={styles.shapeToggle} role="group" aria-label="Quota 10 shape">
          <button aria-pressed={shape === "joined"} onClick={() => replaceParams({ shape: "joined" })}>Joined</button>
          <button aria-pressed={shape === "circle"} onClick={() => replaceParams({ shape: "circle" })}>Circle</button>
        </div>
      </header>

      <section className={styles.stage}>
        <div className={styles.copy}>
          <span>Pulse {current.key.toUpperCase()}</span>
          <h2>{current.name}</h2>
          <p>{current.note} The 4px boundary itself never moves.</p>
          <dl>
            <div><dt>Duration</dt><dd>750ms total</dd></div>
            <div><dt>Direction</dt><dd>Outward only</dd></div>
            <div><dt>Resting fill</dt><dd>40% selected source color</dd></div>
            <div><dt>Selected fill</dt><dd>90% selected source color</dd></div>
            <div><dt>Gold outline</dt><dd>Permanent 4px boundary</dd></div>
          </dl>
          <button className={styles.replayButton} onClick={replayPulse}>Replay pulse</button>
        </div>

        <div className={styles.demoCard}>
          <p>Switch variants or replay the pulse.</p>
          <div className={styles.largeDemo}>
            <QuotaControl focused={focused} quota={quota} pulseKey={pulseKey} variant={variant} shape={shape} onSelect={selectQuota} />
          </div>
          <div className={styles.demoHint}>
            <i style={{ background: selectedCollection.color }} />
            {selectedCollection.label} controls the special segment color
          </div>
        </div>
      </section>

      <section className={styles.bottomBar} aria-label="Search controls preview">
        <div className={styles.controls}>
          <div className={styles.collectionControl}>
            <span className={styles.label}>Sources</span>
            {COLLECTIONS.map((collection) => {
              const active = activeKeys.includes(collection.key);
              return (
                <button
                  key={collection.key}
                  aria-pressed={active}
                  onClick={() => toggleCollection(collection.key)}
                  style={active ? {
                    borderColor: collection.color,
                    background: `color-mix(in srgb, ${collection.color} 20%, transparent)`,
                    color: collection.color,
                  } : undefined}
                >
                  {collection.label}
                </button>
              );
            })}
          </div>
          <div className={styles.quotaBlock}>
            <span className={styles.label}>Per source</span>
            <QuotaControl focused={focused} quota={quota} pulseKey={pulseKey} variant={variant} shape={shape} onSelect={selectQuota} />
          </div>
        </div>
        <div className={styles.searchBar}>
          <span>Ask across the selected sources...</span>
          <button aria-label="Search">↑</button>
        </div>
      </section>

      <nav className={styles.switcher} aria-label="Pulse variants">
        <button onClick={() => cycle(-1)} aria-label="Previous pulse">←</button>
        <div><span>{current.key.toUpperCase()} of 3</span><strong>{current.name}</strong></div>
        <button onClick={() => cycle(1)} aria-label="Next pulse">→</button>
      </nav>
    </main>
  );
}

function QuotaControl({
  focused,
  quota,
  pulseKey,
  variant,
  shape,
  onSelect,
}: {
  focused: boolean;
  quota: number;
  pulseKey: number;
  variant: VariantKey;
  shape: ShapeKey;
  onSelect: (quota: number) => void;
}) {
  return (
    <div className={`${styles.quotaViewport} ${shape === "circle" ? styles.circleMode : styles.joinedMode}`}>
      <div className={`${styles.standardChoices} ${focused ? styles.shifted : ""}`}>
        {[3, 4, 5].map((value) => (
          <button key={value} aria-pressed={quota === value} onClick={() => onSelect(value)}>{value}</button>
        ))}
      </div>
      <button
        aria-label="10 passages per source"
        aria-pressed={quota === 10}
        aria-hidden={!focused}
        tabIndex={focused ? 0 : -1}
        className={`${styles.tenButton} ${focused ? styles.tenVisible : ""}`}
        onClick={() => onSelect(10)}
      >
        <span>10</span>
        {quota === 10 && (
          <span key={`${variant}-${pulseKey}`} className={styles.pulseLayer} data-pulse={variant} aria-hidden="true">
            <i />
            <i />
          </span>
        )}
      </button>
    </div>
  );
}
