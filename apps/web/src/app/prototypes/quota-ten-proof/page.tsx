"use client";

import { useState } from "react";

import { QuotaControl } from "@/components/search/QuotaControl";

function ThemeProof({ theme }: { theme: "dark" | "light" }) {
  const [quota, setQuota] = useState(10);

  return (
    <section
      data-theme={theme}
      className="rounded-xl border border-brand-surface bg-brand-bg p-6 text-brand-primary"
      aria-label={`${theme} theme quota control proof`}
    >
      <p className="mb-5 text-sm font-semibold capitalize">{theme} theme · Bible only</p>
      <QuotaControl value={quota} onChange={setQuota} focusedCollection="bible" />
    </section>
  );
}

export default function QuotaTenProofPage() {
  return (
    <main className="min-h-screen bg-brand-bg p-6">
      <div className="mx-auto grid max-w-3xl gap-5">
        <h1 className="text-lg font-semibold text-brand-primary">Focused quota control visual proof</h1>
        <ThemeProof theme="dark" />
        <ThemeProof theme="light" />
        <div>
          <p className="mb-3 text-sm text-brand-primary">200% CSS zoom · 320 CSS-pixel component width</p>
          <div className="w-[320px]" style={{ zoom: 2 }}>
            <ThemeProof theme="light" />
          </div>
        </div>
      </div>
    </main>
  );
}
