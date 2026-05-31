"use client";

import React from "react";
import { trackErrorOccurred } from "@/lib/analytics";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, _info: React.ErrorInfo): void {
    trackErrorOccurred({ page: "unknown", errorType: error.message ?? "render_error" });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center gap-4 p-8">
          <p className="text-brand-primary text-base">Something went wrong. Reload the page.</p>
          <p className="text-brand-muted text-sm">{this.state.error?.message}</p>
          <button
            className="text-brand-bg bg-brand-accent font-semibold py-2 px-4 rounded hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
