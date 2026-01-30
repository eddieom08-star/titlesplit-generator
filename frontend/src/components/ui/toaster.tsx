"use client";

import * as React from "react";
import { Toast, type ToastProps } from "./toast";

type ToastVariant = "default" | "success" | "error" | "warning" | "info";

interface ToastOptions {
  title?: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: string;
}

interface ToastContextValue {
  toast: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
  dismissAll: () => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

let toastCount = 0;
function generateId(): string {
  return `toast-${++toastCount}-${Date.now()}`;
}

interface ToastProviderProps {
  children: React.ReactNode;
  defaultDuration?: number;
}

export function ToastProvider({
  children,
  defaultDuration = 5000,
}: ToastProviderProps) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const timersRef = React.useRef<Map<string, NodeJS.Timeout>>(new Map());

  const dismiss = React.useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const dismissAll = React.useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
    setToasts([]);
  }, []);

  const toast = React.useCallback(
    (options: ToastOptions): string => {
      const id = generateId();
      const duration = options.duration ?? defaultDuration;

      setToasts((prev) => [...prev, { ...options, id }]);

      if (duration > 0) {
        const timer = setTimeout(() => {
          dismiss(id);
        }, duration);
        timersRef.current.set(id, timer);
      }

      return id;
    },
    [defaultDuration, dismiss]
  );

  React.useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  const contextValue = React.useMemo(
    () => ({ toast, dismiss, dismissAll }),
    [toast, dismiss, dismissAll]
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <Toaster toasts={toasts} onClose={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

interface ToasterProps {
  toasts: ToastItem[];
  onClose: (id: string) => void;
}

function Toaster({ toasts, onClose }: ToasterProps) {
  if (toasts.length === 0) return null;

  return (
    <div
      aria-label="Notifications"
      className="pointer-events-none fixed right-0 top-0 z-50 flex max-h-screen w-full flex-col gap-2 p-4 sm:max-w-[420px]"
    >
      {toasts.map((t) => (
        <Toast
          key={t.id}
          id={t.id}
          title={t.title}
          description={t.description}
          variant={t.variant}
          onClose={onClose}
        />
      ))}
    </div>
  );
}

export { Toaster };
export type { ToastOptions, ToastVariant };
