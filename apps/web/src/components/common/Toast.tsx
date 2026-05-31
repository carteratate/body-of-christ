"use client";

import { useCallback, useEffect, useState } from "react";

interface ToastProps {
  message: string;
  type?: "success" | "error";
  onDismiss: () => void;
}

export function Toast({ message, type = "success", onDismiss }: ToastProps) {
  useEffect(() => {
    const id = setTimeout(onDismiss, 3000);
    return () => clearTimeout(id);
  }, [onDismiss]);

  const textColor = type === "error" ? "text-brand-danger" : "text-brand-accent";

  return (
    <div role="status" className="fixed bottom-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
      <div className={`bg-brand-surface ${textColor} rounded-lg px-4 py-3 shadow-lg text-sm font-medium max-w-xs`}>
        {message}
      </div>
    </div>
  );
}

interface ToastState {
  message: string;
  type: "success" | "error";
  visible: boolean;
}

export function useToast(): {
  toast: ToastState;
  showToast: (message: string, type?: "success" | "error") => void;
  dismissToast: () => void;
} {
  const [toast, setToast] = useState<ToastState>({
    message: "",
    type: "success",
    visible: false,
  });

  const showToast = useCallback((message: string, type: "success" | "error" = "success") => {
    setToast({ message, type, visible: true });
  }, []);

  const dismissToast = useCallback(() => {
    setToast((prev) => ({ ...prev, visible: false }));
  }, []);

  return { toast, showToast, dismissToast };
}
