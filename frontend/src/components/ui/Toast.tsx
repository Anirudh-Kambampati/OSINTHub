import { AlertTriangle, Check, Info, X } from "lucide-react";
import type { Toast as ToastModel, ToastKind } from "../../lib/feedback";

const ICON: Record<ToastKind, typeof Check> = {
  success: Check,
  error: AlertTriangle,
  info: Info,
};

// Errors carry an icon *and* text so meaning never rests on color alone (spec: accessibility).
const TONE: Record<ToastKind, { color: string; border: string; bg: string }> = {
  success: {
    color: "var(--st-found)",
    border: "color-mix(in srgb, var(--st-found) 35%, transparent)",
    bg: "color-mix(in srgb, var(--st-found) 10%, transparent)",
  },
  error: {
    color: "var(--st-error)",
    border: "color-mix(in srgb, var(--st-error) 35%, transparent)",
    bg: "color-mix(in srgb, var(--st-error) 8%, transparent)",
  },
  info: {
    color: "var(--st-auth)",
    border: "color-mix(in srgb, var(--st-auth) 35%, transparent)",
    bg: "color-mix(in srgb, var(--st-auth) 10%, transparent)",
  },
};

function ToastItem({ toast, onDismiss }: { toast: ToastModel; onDismiss: (id: number) => void }) {
  const Icon = ICON[toast.kind];
  const tone = TONE[toast.kind];
  return (
    <div
      className="toast-enter pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-md border px-3 py-2.5 shadow-lg"
      style={{ color: "var(--fg)", borderColor: tone.border, background: tone.bg }}
    >
      <Icon className="mt-0.5 size-4 shrink-0" style={{ color: tone.color }} aria-hidden />
      <p className="min-w-0 flex-1 text-[13px] leading-snug">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="-mt-0.5 -mr-1 shrink-0 rounded p-1 text-subtle hover:text-fg"
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}

/**
 * The viewport. Both regions stay mounted for the life of the app so screen readers reliably
 * announce additions — never swap the region node out. Polite for success/info, assertive for
 * errors, matching the spec's accessibility contract. Bottom-right on desktop, top-center on
 * small screens. Toasts never take focus (non-modal).
 */
export function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: ToastModel[];
  onDismiss: (id: number) => void;
}) {
  const polite = toasts.filter((t) => t.kind !== "error");
  const assertive = toasts.filter((t) => t.kind === "error");
  const stack = "pointer-events-none flex w-full max-w-sm flex-col items-stretch gap-2";
  return (
    <div
      aria-label="Notifications"
      className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex flex-col items-center p-4 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:top-auto sm:items-end"
    >
      <div role="status" aria-live="polite" className={stack}>
        {polite.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
        ))}
      </div>
      <div role="alert" aria-live="assertive" className={stack}>
        {assertive.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
        ))}
      </div>
    </div>
  );
}
