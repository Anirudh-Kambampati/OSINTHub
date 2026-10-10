import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackProvider } from "../../context/FeedbackContext";
import { NotesPanel } from "./NotesPanel";

type Flags = { fail: boolean };

/** Mocks fetch so GET notes succeed and POST notes honour the `fail` flag. */
function mockApi(flags: Flags) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "GET" && url.pathname.endsWith("/notes")) {
      return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (method === "POST" && url.pathname.endsWith("/notes")) {
      if (flags.fail) {
        return new Response(JSON.stringify({ detail: "Storage unavailable." }), { status: 500, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ id: "n1", body: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/investigations/inv-1"]}>
      <QueryClientProvider client={client}>
        <FeedbackProvider>
          <NotesPanel investigationId="inv-1" />
        </FeedbackProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("NotesPanel feedback", () => {
  it("toasts 'Note added.' and clears the input on success", async () => {
    mockApi({ fail: false });
    renderPanel();
    const textarea = await screen.findByLabelText("New note");
    await userEvent.type(textarea, "Follow up on the domain lead");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));
    await vi.advanceTimersByTimeAsync(0);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Note added."));
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("keeps the input and shows one inline error when the save fails", async () => {
    mockApi({ fail: true });
    renderPanel();
    const textarea = await screen.findByLabelText("New note");
    await userEvent.type(textarea, "Draft note that must survive");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));
    await vi.advanceTimersByTimeAsync(0);
    // Exactly one alert carries content: the inline ErrorNotice. The toast viewport keeps a
    // persistent empty assertive live region mounted (a deliberate a11y choice — regions must
    // not be swapped out), so count alerts with text rather than alert nodes. No toast fires
    // because meta.inlineError opts out, so the failure isn't reported twice.
    const alerts = (await screen.findAllByRole("alert")).filter((n) => (n.textContent ?? "").trim().length > 0);
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(/server had a problem/i);
    const status = screen.getByRole("status");
    expect(status.querySelectorAll(".toast-enter")).toHaveLength(0);
    expect((textarea as HTMLTextAreaElement).value).toBe("Draft note that must survive");
  });
});
