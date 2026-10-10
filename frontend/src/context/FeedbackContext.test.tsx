import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { TOAST_DURATION_MS } from "../lib/feedback";
import { FeedbackProvider, createFeedbackMutationCache, feedbackDispatcher, useActionFeedback, useFeedback } from "./FeedbackContext";

type Flags = { fail: boolean; unauthorized: boolean };

/**
 * The toast viewport keeps both live regions mounted for the life of the app (a11y: a region
 * that is swapped out mid-session stops being announced reliably), so there is always one empty
 * `role="status"` and one empty `role="alert"` in the DOM. Count only the ones showing a toast.
 */
const renderedToasts = (role: "status" | "alert") =>
  screen.getByRole(role).querySelectorAll(".toast-enter");

/** Drives a bare mutation (no per-call onError) so only the interceptor can report it. */
function Probe({ flags }: { flags: Flags }) {
  const { notify } = useFeedback();
  const navigate = useNavigate();
  const action = useActionFeedback<void, void>(
    {
      mutationFn: async () => {
        if (flags.unauthorized) throw new ApiError(401, "unauthorized");
        if (flags.fail) throw new ApiError(500, "boom");
      },
      // Deliberately no onError: the interceptor must surface this.
    },
    { success: "Saved." },
  );
  return (
    <div>
      <button onClick={() => action.mutate()}>Run</button>
      <button onClick={() => notify("success", "Note added.")}>Toast</button>
      <button onClick={() => notify("success", "Note added.")}>Toast again</button>
      <button onClick={() => notify("success", "A")}>A</button>
      <button onClick={() => notify("success", "B")}>B</button>
      <button onClick={() => notify("success", "C")}>C</button>
      <button onClick={() => notify("success", "D")}>D</button>
      <button onClick={() => navigate("/login")}>Go</button>
    </div>
  );
}

function makeClient() {
  return new QueryClient({
    mutationCache: createFeedbackMutationCache((error, fallback) =>
      feedbackDispatcher.notifyError?.(error, fallback),
    ),
    defaultOptions: { queries: { retry: false } },
  });
}

function renderProbe(flags: Flags) {
  const client = makeClient();
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={client}>
        <FeedbackProvider>
          <Probe flags={flags} />
        </FeedbackProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// `userEvent.setup()` must run before fake timers go in: user-event reads its delay config from
// the real clock at setup, and with that plumbing in place its awaits resolve under fake timers.
// Timers are otherwise driven explicitly with `advanceTimersByTimeAsync`, so a toast can't
// dismiss itself behind the test's back between an action and an assert.
let user: ReturnType<typeof userEvent.setup>;
beforeEach(() => {
  user = userEvent.setup();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("FeedbackProvider", () => {
  it("reports a mutation failure the component never handled", async () => {
    renderProbe({ fail: true, unauthorized: false });
    await user.click(screen.getByText("Run"));
    await vi.advanceTimersByTimeAsync(0);
    // 500 -> generic server copy, in the assertive region.
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/server had a problem/i));
    expect(renderedToasts("alert").length).toBeGreaterThan(0);
  });

  it("routes a 401 to sign-in instead of toasting", async () => {
    renderProbe({ fail: false, unauthorized: true });
    await user.click(screen.getByText("Run"));
    await vi.advanceTimersByTimeAsync(0);
    // The auth layer owns lost sessions; the feedback layer must stay silent.
    expect(renderedToasts("alert")).toHaveLength(0);
    expect(renderedToasts("status")).toHaveLength(0);
  });

  it("shows a success toast on settle-ok", async () => {
    renderProbe({ fail: false, unauthorized: false });
    await user.click(screen.getByText("Run"));
    await vi.advanceTimersByTimeAsync(0);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved."));
  });

  it("dedupes an identical message instead of stacking it", async () => {
    renderProbe({ fail: false, unauthorized: false });
    await user.click(screen.getByText("Toast"));
    await user.click(screen.getByText("Toast again"));
    await vi.advanceTimersByTimeAsync(0);
    const status = screen.getByRole("status");
    expect(status.querySelectorAll(".toast-enter")).toHaveLength(1);
  });

  it("caps the visible stack at three, dropping the oldest", async () => {
    renderProbe({ fail: false, unauthorized: false });
    for (const label of ["A", "B", "C", "D"]) {
      await user.click(screen.getByText(label));
    }
    await vi.advanceTimersByTimeAsync(0);
    const status = screen.getByRole("status");
    expect(status.querySelectorAll(".toast-enter")).toHaveLength(3);
    expect(status).not.toHaveTextContent("A");
    expect(status).toHaveTextContent("D");
  });

  it("auto-dismisses after the success duration", async () => {
    renderProbe({ fail: false, unauthorized: false });
    await user.click(screen.getByText("Toast"));
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.getByRole("status")).toHaveTextContent("Note added.");
    await vi.advanceTimersByTimeAsync(TOAST_DURATION_MS.success + 50);
    expect(renderedToasts("status")).toHaveLength(0);
  });

  it("keeps a toast up while it is hovered", async () => {
    renderProbe({ fail: false, unauthorized: false });
    await user.click(screen.getByText("Toast"));
    await vi.advanceTimersByTimeAsync(0);
    const item = screen.getByRole("status").querySelector(".toast-enter")!;
    await user.hover(item);
    await vi.advanceTimersByTimeAsync(TOAST_DURATION_MS.success + 200);
    expect(screen.getByRole("status")).toHaveTextContent("Note added.");
  });
});
