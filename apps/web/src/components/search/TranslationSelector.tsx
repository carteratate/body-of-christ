"use client";

import { useEffect, useRef } from "react";

const TRANSLATIONS = [
  { value: "CPDV",         label: "CPDV (default)" },
  { value: "douay-rheims", label: "Douay-Rheims" },
];

interface TranslationSelectorProps {
  value: string;
  onChange: (translation: string) => void;
  onClose: () => void;
}

export function TranslationSelector({
  value,
  onChange,
  onClose,
}: TranslationSelectorProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute bottom-[calc(100%+6px)] left-0 z-20 min-w-[160px] overflow-hidden rounded-lg border border-brand-surface bg-brand-surface shadow-lg"
    >
      {TRANSLATIONS.map((t) => (
        <button
          key={t.value}
          onClick={() => {
            onChange(t.value);
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-brand-primary transition-colors hover:bg-brand-bg"
        >
          <span className={value === t.value ? "text-brand-accent" : "invisible"}>
            ✓
          </span>
          {t.label}
        </button>
      ))}
    </div>
  );
}
