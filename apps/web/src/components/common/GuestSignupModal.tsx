"use client";

import ReactDOM from "react-dom";
import { useRouter } from "next/navigation";

interface GuestSignupModalProps {
  isOpen: boolean;
  onDismiss: () => void;
  reason?: "limit" | "library" | "saved" | "history" | "notes" | "feature";
}

const COPY = {
  limit: {
    title: "You’ve used your trial searches",
    body: "Create a free account to continue searching and access your two trial searches, saved passages, private notes, and the full TheoCorpus Library. Your account is completely free.",
  },
  library: {
    title: "Explore the full Library",
    body: "Create a free account to browse the complete TheoCorpus Library and keep your searches, saved passages, and private notes together. Your account is completely free.",
  },
  saved: {
    title: "Keep your saved passages",
    body: "This passage is saved for your trial. Create a free account to access all your saved passages, add private notes, and browse the full TheoCorpus Library.",
  },
  history: {
    title: "Keep your search history",
    body: "Create a free account to access your trial searches, return to the sources you found, and browse the full TheoCorpus Library.",
  },
  notes: {
    title: "Add private notes",
    body: "Create a free account to keep your saved passages, add private notes alongside them, and browse the full TheoCorpus Library.",
  },
  feature: {
    title: "Continue with TheoCorpus",
    body: "Create a free account to keep your searches, saved passages, and notes together and access the full TheoCorpus Library. Your account is completely free.",
  },
} as const;

export function GuestSignupModal({ isOpen, onDismiss, reason = "feature" }: GuestSignupModalProps) {
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
          {COPY[reason].title}
        </h2>
        <p className="text-brand-muted text-sm leading-relaxed mb-6">
          {COPY[reason].body}
        </p>
        <button
          onClick={() => router.push("/signup")}
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
