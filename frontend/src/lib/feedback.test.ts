import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { MAX_VISIBLE_TOASTS, TOAST_DURATION_MS, mapApiError, parseRetryAfter } from "./feedback";

describe("mapApiError", () => {
  const fallback = "Something went wrong.";

  it("surfaces the server detail for 403 and 422", () => {
    expect(mapApiError(new ApiError(403, "Current password is incorrect."), fallback))
      .toBe("Current password is incorrect.");
    expect(mapApiError(new ApiError(422, "Password is too weak."), fallback)).toBe("Password is too weak.");
  });

  it("falls back to caller copy when a 4xx has no detail", () => {
    expect(mapApiError(new ApiError(422, ""), fallback)).toBe(fallback);
  });

  it("reports a lost session for 401", () => {
    expect(mapApiError(new ApiError(401, "x"), fallback)).toBe("Session expired — sign in again.");
  });

  it("reports rate limiting for 429", () => {
    expect(mapApiError(new ApiError(429, "x"), fallback)).toMatch(/Too many attempts/);
  });

  it("reports a server problem for 5xx", () => {
    expect(mapApiError(new ApiError(500, "boom"), fallback)).toMatch(/server had a problem/);
    expect(mapApiError(new ApiError(503, "boom"), fallback)).toMatch(/server had a problem/);
  });

  it("reports an unreachable server for a network failure", () => {
    expect(mapApiError(new TypeError("Failed to fetch"), fallback)).toMatch(/reach the server/);
  });

  it("uses the caller's fallback for anything unrecognised", () => {
    expect(mapApiError(new Error("weird"), fallback)).toBe(fallback);
  });
});

describe("parseRetryAfter", () => {
  it("parses a plain second count", () => {
    expect(parseRetryAfter("30")).toBe(30);
    expect(parseRetryAfter(" 12 ")).toBe(12);
  });

  it("rejects missing or non-numeric values", () => {
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter(undefined)).toBeNull();
    expect(parseRetryAfter("Wed, 21 Oct 2026 07:28:00 GMT")).toBeNull();
    expect(parseRetryAfter("0")).toBeNull();
  });
});

describe("toast policy", () => {
  it("keeps errors on screen longer than successes", () => {
    expect(TOAST_DURATION_MS.error).toBeGreaterThan(TOAST_DURATION_MS.success);
  });

  it("caps the visible stack at three", () => {
    expect(MAX_VISIBLE_TOASTS).toBe(3);
  });
});
