/**
 * Toast notification hook.
 *
 * Provides functions to show error/info/success toasts and
 * manages their lifecycle (auto-removal after 5 seconds, max 5 visible).
 */

import { useCallback, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  type: "error" | "info" | "success";
}

const MAX_TOASTS = 5;
const AUTO_DISMISS_MS = 5000;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextIdRef = useRef(1);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (message: string, type: Toast["type"]) => {
      const id = nextIdRef.current++;
      setToasts((prev) => {
        const updated = [...prev, { id, message, type }];
        // Keep only the most recent MAX_TOASTS
        return updated.length > MAX_TOASTS
          ? updated.slice(updated.length - MAX_TOASTS)
          : updated;
      });
      // Auto-dismiss
      setTimeout(() => {
        removeToast(id);
      }, AUTO_DISMISS_MS);
    },
    [removeToast],
  );

  const showError = useCallback(
    (message: string) => addToast(message, "error"),
    [addToast],
  );

  const showInfo = useCallback(
    (message: string) => addToast(message, "info"),
    [addToast],
  );

  const showSuccess = useCallback(
    (message: string) => addToast(message, "success"),
    [addToast],
  );

  return { toasts, showError, showInfo, showSuccess, removeToast };
}
