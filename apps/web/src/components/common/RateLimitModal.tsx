"use client";

import { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { trackRateLimitHit } from "@/lib/analytics";

interface RateLimitModalProps {
  limitType: "per_minute" | "daily";
  retryAfter: number | null;
  onDismiss: () => void;
}

export function RateLimitModal({ limitType, retryAfter, onDismiss }: RateLimitModalProps) {
  const [countdown, setCountdown] = useState(() => retryAfter ?? 60);

  useEffect(() => {
    trackRateLimitHit({ limitType });
  }, [limitType]);

  useEffect(() => {
    if (limitType !== "per_minute") return;
    const id = setInterval(() => {
      setCountdown((prev) => (prev > 1 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(id);
  }, [limitType]);

  const content = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onDismiss}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rate-limit-modal-title"
        className="bg-brand-surface text-brand-primary rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="rate-limit-modal-title" className="text-lg font-semibold mb-3">Search Limit Reached</h2>

        {limitType === "per_minute" ? (
          <p className="text-brand-muted text-sm mb-5">
            You&apos;ve reached your per-minute search limit (5 searches/minute).
            {countdown > 0
              ? ` Your limit resets in ${countdown} second${countdown !== 1 ? "s" : ""}.`
              : " Your limit is resetting shortly."}
          </p>
        ) : (
          <p className="text-brand-muted text-sm mb-5">
            Your daily limit of 30 searches has been reached. Resets at midnight.
          </p>
        )}

        <button
          className="w-full bg-brand-accent text-brand-bg font-semibold py-2 px-4 rounded hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          onClick={onDismiss}
        >
          OK
        </button>
      </div>
    </div>
  );

  return ReactDOM.createPortal(content, document.body);
}
