import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { vi } from "vitest";
import { routes } from "../App";
import { signedIn } from "./fixtures";

type Handler = (url: URL, init?: RequestInit) => unknown | Promise<unknown>;

/** Route table for the mocked backend: "METHOD /path" -> JSON body (or a function producing one). */
export function mockApi(table: Record<string, unknown | Handler>, { auth = signedIn as unknown } = {}) {
  table = { "GET /api/auth/status": auth, "GET /api/investigations/inv-1/notes": [], ...table };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url.pathname}`;
    if (!(key in table)) return new Response(JSON.stringify({ detail: "Not found" }), { status: 404 });
    const entry = table[key];
    const body = typeof entry === "function" ? await (entry as Handler)(url, init) : entry;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderRoute(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
