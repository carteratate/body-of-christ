"use client";

import ReactDOM from "react-dom";
import { useRouter } from "next/navigation";

interface GuestSignupModalProps {
  isOpen: boolean;
  onDismiss: () => void;
}

export function GuestSignupModal({ isOpen, onDismiss }: GuestSignupModalProps) {
  const router = useRouter();

  if (!isOpen) return null;

  const content = (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="guest-modal-title"
        className="bg-brand-surface text-brand-primary rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl"
      >
        <h2 id="guest-modal-title" className="text-lg font-semibold mb-3">
          Like what you see?
        </h2>
        <p className="text-brand-muted text-sm leading-relaxed mb-6">
          Create a free account to keep exploring — 30 searches a day, all 10
          collections, and the ability to save passages you want to return to.
        </p>
        <button
          onClick={() => router.push("/login")}
          className="w-full bg-brand-accent text-brand-bg font-semibold py-2 px-4 rounded hover:opacity-90 transition-opacity mb-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          Create free account
        </button>
        <button
          onClick={onDismiss}
          className="w-full text-brand-muted text-sm py-2 hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent rounded"
        >
          Maybe later
        </button>
      </div>
    </div>
  );

  return ReactDOM.createPortal(content, document.body);
}
