import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";
import { Button } from "./primitives";

/**
 * Capture whatever had focus before the dialog opened, so it can be restored on close. This must
 * be a layout effect: it flushes synchronously during the commit where `open` flips true, before
 * the confirm button's `autoFocus` takes over. A passive `useEffect` can be deferred past that
 * commit, by which time `activeElement` is already inside the dialog (or <body>), and the restore
 * would send focus to the wrong place.
 */
function useRestoreFocus(open: boolean, panel: React.RefObject<HTMLDivElement | null>) {
  const restoreFocus = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (!open) return;
    // In real browsers `activeElement` is still the trigger here and we just record it. In
    // jsdom the confirm button's `autoFocus` is applied during commit — before layout effects
    // run — so the dialog has already stolen focus by this point, and we would otherwise record
    // the panel itself. Either way, capturing the previously focused element is unreliable, so
    // close uses the standard heuristic instead: restore only while focus is still trapped.
    const active = document.activeElement;
    restoreFocus.current = active instanceof HTMLElement && !panel.current?.contains(active) ? active : null;
  }, [open, panel]);
  return restoreFocus;
}

/**
 * Confirmation for a destructive action. Traps focus while open and returns it to whatever
 * opened it on close, mirroring the Drawer's behaviour. Non-destructive confirmations don't
 * belong here (spec: only destructive actions are confirmed).
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  busy = false,
}: {
  open: boolean;
  title: ReactNode;
  body?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const restoreFocus = useRestoreFocus(open, panel);

  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
      if (e.key === "Tab") {
        // Keep focus on the two buttons inside the dialog.
        const focusables = panel.current?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && (active === first || active === panel.current)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      // Hand focus back to whatever opened us, but only while focus is still ours. If the user
      // closed by clicking elsewhere, that element has focus and is where it should stay — never
      // yank focus back to the trigger.
      if (restoreFocus.current?.isConnected && panel.current?.contains(document.activeElement)) {
        restoreFocus.current.focus();
      }
    };
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[var(--overlay)]" onClick={onCancel} aria-hidden />
      <div
        ref={panel}
        role="alertdialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : "Confirm"}
        tabIndex={-1}
        className="relative w-full max-w-sm rounded-lg border border-line bg-surface p-5 shadow-2xl outline-none"
      >
        <h2 className="text-[15px] font-semibold text-fg">{title}</h2>
        {body && <div className="mt-2 text-[13px] text-muted">{body}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy} autoFocus>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
