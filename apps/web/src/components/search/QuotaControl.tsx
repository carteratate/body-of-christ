"use client";

const QUOTA_OPTIONS = [3, 4, 5] as const;

interface QuotaControlProps {
  value: number;
  onChange: (quota: number) => void;
}

export function QuotaControl({ value, onChange }: QuotaControlProps) {

  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Per source:
      </span>
      <div className="flex overflow-hidden rounded-md border border-brand-surface" role="group" aria-label="Results per source">
        {QUOTA_OPTIONS.map((q, i) => (
          <button
            key={q}
            onClick={() => onChange(q)}
            aria-pressed={value === q}
            className={[
              "px-3 py-1 text-xs transition-colors",
              i < QUOTA_OPTIONS.length - 1 ? "border-r border-brand-surface" : "",
              value === q
                ? "bg-brand-accent font-semibold text-brand-bg"
                : "bg-brand-surface text-brand-muted hover:text-brand-primary",
            ].join(" ")}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
