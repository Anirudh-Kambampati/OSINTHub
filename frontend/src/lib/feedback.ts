import { ApiError } from "./api";

export type ToastKind = "success" | "error" | "info";

export type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

/** Auto-dismiss per kind: errors linger longer than successes (spec: toast behavior). */
export const TOAST_DURATION_MS: Record<ToastKind, number> = {
  success: 4000,
  info: 5000,
  error: 8000,
};

export const MAX_VISIBLE_TOASTS = 3;

/**
 * Pull a delay in seconds out of a `Retry-After` header. Only a plain second count is
 * honoured — an HTTP-date form isn't worth the parsing here, so it falls back to null.
 */
export function parseRetryAfter(header: string | null | undefined): number | null {
  if (!header) return null;
  const seconds = Number(header.trim());
  return Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds) : null;
}

const withDelay = (message: string, retryAfter: string | null | undefined) => {
  const delay = parseRetryAfter(retryAfter);
  return delay ? `${message} Try again in ${delay} second${delay === 1 ? "" : "s"}.` : `${message} Try again shortly.`;
};

/**
 * Turn an API failure into a message that says what happened and what to do.
 *
 * 403/422 surface the server's own `detail` (a fixed constant, safe to show). Everything else
 * gets a fixed, human fallback — callers pass their own `fallback` as the last resort.
 */
export function mapApiError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Session expired — sign in again.";
    if (error.status === 403 || error.status === 422) return error.message || fallback;
    if (error.status === 429) return withDelay("Too many attempts.", undefined);
    if (error.status >= 500) return "The server had a problem — try again in a moment.";
  }
  // fetch() rejects with a TypeError for DNS/TCP failures and offline; timeouts surface as
  // AbortError. Both mean we never reached the server.
  if (error instanceof TypeError) return "Can't reach the server — check your connection.";
  if (error instanceof DOMException && error.name === "AbortError") {
    return "Can't reach the server — check your connection.";
  }
  return fallback;
}

/** True when the failure is a lost session, so callers can skip a redundant inline echo. */
export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
