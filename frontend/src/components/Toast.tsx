/**
 * Toast notification container component.
 *
 * Renders a stack of toast notifications at the bottom-right corner.
 * Each toast can be dismissed by clicking. Uses inline styles only.
 */

import type { Toast } from "../hooks/useToast";

interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: number) => void;
}

const CONTAINER_STYLE: React.CSSProperties = {
  position: "fixed",
  bottom: 16,
  right: 16,
  zIndex: 10000,
  display: "flex",
  flexDirection: "column",
  gap: 8,
  pointerEvents: "none",
  maxWidth: 400,
};

const BASE_TOAST_STYLE: React.CSSProperties = {
  padding: "10px 16px",
  borderRadius: 6,
  color: "#fff",
  fontSize: 13,
  lineHeight: 1.4,
  cursor: "pointer",
  pointerEvents: "auto",
  boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
  wordBreak: "break-word",
  display: "flex",
  alignItems: "flex-start",
  gap: 8,
};

const TYPE_COLORS: Record<Toast["type"], string> = {
  error: "#d32f2f",
  info: "#1976d2",
  success: "#388e3c",
};

const TYPE_ICONS: Record<Toast["type"], string> = {
  error: "\u2716",
  info: "\u2139",
  success: "\u2714",
};

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div style={CONTAINER_STYLE}>
      {toasts.map((toast) => (
        <div
          key={toast.id}
          style={{
            ...BASE_TOAST_STYLE,
            backgroundColor: TYPE_COLORS[toast.type],
          }}
          onClick={() => onRemove(toast.id)}
          title="點擊關閉"
          role="alert"
        >
          <span style={{ flexShrink: 0 }}>{TYPE_ICONS[toast.type]}</span>
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
