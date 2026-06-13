"use client";

import { useEffect, useRef } from "react";
import { Check } from "lucide-react";

const TRANSLATIONS = [
  { value: "WEB-C", label: "World English Bible, Catholic Edition" },
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
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onCloseRef.current();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, []); // stable — registers once

  return (
    <div
      ref={ref}
      className="absolute bottom-[calc(100%+6px)] left-0 z-20 min-w-[160px] overflow-hidden rounded-lg border border-brand-bg bg-brand-surface shadow-lg"
    >
      {TRANSLATIONS.map((t) => (
        <button
          key={t.value}
          aria-pressed={value === t.value}
          onClick={() => {
            onChange(t.value);
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-brand-primary transition-colors hover:bg-brand-bg"
        >
          <Check
            size={12}
            className={value === t.value ? "text-brand-accent" : "invisible"}
          />
          {t.label}
        </button>
      ))}
    </div>
  );
}
