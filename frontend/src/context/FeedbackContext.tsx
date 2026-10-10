import { MutationCache, useMutation, type UseMutationOptions } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ToastViewport } from "../components/ui/Toast";
import { isUnauthorized, mapApiError, MAX_VISIBLE_TOASTS, TOAST_DURATION_MS, type Toast, type ToastKind } from "../lib/feedback";

type FeedbackApi = {
  notify: (kind: ToastKind, message: string) => void;
  notifyError: (error: unknown, fallback: string) => void;
  /** True while a toast is hovered or focused, so auto-dismiss timers can pause. */
  paused: boolean;
};

const FeedbackContext = createContext<FeedbackApi | null>(null);

let nextId = 1;

/**
 * Bridges the module-scope QueryClient (constructed outside React) to the provider's handlers.
 * The provider registers on mount; until then the interceptor no-ops.
 */
export const feedbackDispatcher: {
  notifyError?: (error: unknown, fallback: string) => void;
} = {};

/** Per-mutation metadata the feedback layer reads; callers set it to opt out or customize. */
export type FeedbackMeta = { inlineError?: boolean; errorFallback?: string };
type MetaMutation = { meta?: FeedbackMeta };

/**
 * Build the MutationCache that reports every mutation error automatically — including ones a
 * component forgot to handle. Passed to the QueryClient (v5 has no hook for this). A mutation
 * that sets `meta.inlineError` keeps its failure in a form field instead of a toast.
 * A 401 is left to the auth layer, which already routes to sign-in.
 */
export function createFeedbackMutationCache(notifyError: (error: unknown, fallback: string) => void) {
  return new MutationCache({
    onError: (error, _variables, _onMutateResult, mutation) => {
      const meta = (mutation as unknown as MetaMutation).meta;
      if (meta?.inlineError) return;
      // A 401 is a lost session: the auth layer already routes to sign-in and shows why, so
      // toasting here would report the same thing twice.
      if (isUnauthorized(error)) return;
      notifyError(error, meta?.errorFallback ?? "That didn't go through.");
    },
  });
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [paused, setPaused] = useState(false);

  // Dedupe by message: an identical message replaces the existing one and restarts its timer.
  const notify = useCallback((kind: ToastKind, message: string) => {
    setToasts((prev) => {
      const withoutDupes = prev.filter((t) => t.message !== message);
      const next = [...withoutDupes, { id: nextId++, kind, message }];
      return next.slice(-MAX_VISIBLE_TOASTS); // cap, dropping the oldest
    });
  }, []);

  const dismiss = useCallback((id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);

  const notifyError = useCallback(
    (error: unknown, fallback: string) => {
      if (isUnauthorized(error)) return; // announced once via the redirect path, not doubled
      notify("error", mapApiError(error, fallback));
    },
    [notify],
  );

  const value = useMemo<FeedbackApi>(() => ({ notify, notifyError, paused }), [notify, notifyError, paused]);

  // Register handlers the module-scope MutationCache can reach, and clear them on unmount.
  useEffect(() => {
    feedbackDispatcher.notifyError = notifyError;
    return () => {
      feedbackDispatcher.notifyError = undefined;
    };
  }, [notifyError]);

  // Auto-dismiss timers, paused while any toast is hovered or focused.
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  useEffect(() => {
    if (paused) {
      timers.current.forEach((t) => clearTimeout(t));
      timers.current.clear();
      return;
    }
    for (const toast of toasts) {
      if (timers.current.has(toast.id)) continue;
      timers.current.set(
        toast.id,
        setTimeout(() => {
          timers.current.delete(toast.id);
          dismiss(toast.id);
        }, TOAST_DURATION_MS[toast.kind]),
      );
    }
  }, [toasts, paused, dismiss]);

  useEffect(() => () => timers.current.forEach((t) => clearTimeout(t)), []);

  return (
    <FeedbackContext.Provider value={value}>
      <div
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
      >
        <ToastViewport toasts={toasts} onDismiss={dismiss} />
      </div>
      {children}
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): FeedbackApi {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error("useFeedback must be used within a FeedbackProvider");
  return ctx;
}

type ActionFeedbackOptions<TData, TVariables> = {
  success?: string | ((data: TData, variables: TVariables) => string);
  error?: string;
};

/**
 * Wrap a mutation so it reports a success toast on settle-ok and an error message otherwise.
 * Errors go through the shared MutationCache interceptor (unless `meta.inlineError` is set),
 * so callers only supply the success copy and an optional error fallback. Returns the mutation
 * plus `submit`, which is `mutateAsync` with success feedback applied.
 */
export function useActionFeedback<TData = unknown, TVariables = void>(
  config: UseMutationOptions<TData, unknown, TVariables, unknown>,
  copy: ActionFeedbackOptions<TData, TVariables> = {},
) {
  const { notify, notifyError } = useFeedback();
  const { onSuccess, onError, meta, ...rest } = config;
  const successCopy = copy.success;
  const errorCopy = copy.error;
  const mutation = useMutation<TData, unknown, TVariables, unknown>({
    ...rest,
    // Report here rather than in `submit`, so both `.mutate()` and `.submit()` give feedback —
    // a caller reaching for the plain react-query API still gets the toast.
    meta: errorCopy ? { ...meta, errorFallback: errorCopy } : meta,
    // react-query v5 hands onSuccess/onError four args: (result, variables, onMutateResult,
    // context). Forward all four verbatim so a caller's own callbacks keep working unchanged.
    onSuccess: (data, variables, onMutateResult, context) => {
      if (successCopy) {
        notify("success", typeof successCopy === "function" ? successCopy(data, variables) : successCopy);
      }
      return onSuccess?.(data, variables, onMutateResult, context);
    },
    onError: (error, variables, onMutateResult, context) => {
      // The MutationCache interceptor already toasts errors that lack `inlineError`; only add
      // an inline echo here when the caller explicitly asked for one.
      if (errorCopy) notifyError(error, errorCopy);
      return onError?.(error, variables, onMutateResult, context);
    },
  });

  const submit = useCallback((variables: TVariables) => mutation.mutateAsync(variables), [mutation]);

  return { ...mutation, submit };
}
