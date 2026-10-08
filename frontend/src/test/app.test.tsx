import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { investigation, profileView, run, stats } from "./fixtures";
import { mockApi, renderRoute } from "./render";

afterEach(() => vi.unstubAllGlobals());

const emptyMentions = { total: 0, counts: {}, items: [] };

describe("empty state", () => {
  it("invites the user to start an investigation when none exist", async () => {
    mockApi({ "GET /api/investigations": [] });
    renderRoute("/");
    expect(await screen.findByRole("heading", { name: "Start an Investigation" })).toBeInTheDocument();
    expect(screen.getByText(/Search a username, email, name, domain, or URL/)).toBeInTheDocument();
  });

  it("classifies input before searching", async () => {
    mockApi({
      "GET /api/investigations": [],
      "POST /api/classify": { valid: true, type: "username", normalized: "anirudh123", alternatives: [], error: null },
    });
    renderRoute("/");
    const input = (await screen.findAllByLabelText("Investigation search"))[0];
    await userEvent.type(input, "anirudh123");
    expect(await screen.findByText("Detected type")).toBeInTheDocument();
    expect(screen.getAllByText(/^username$/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Search public sources/ })).toBeEnabled();
  });
});

describe("investigation states", () => {
  it("shows skeletons while loading", () => {
    mockApi({ "GET /api/investigations/inv-1": () => new Promise(() => {}) });
    const { container } = renderRoute("/investigations/inv-1");
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
  });

  it("shows live per-source progress while running", async () => {
    mockApi({
      "GET /api/investigations/inv-1": investigation({
        status: "running",
        runs: [run(), run({ connector: "devto", label: "DEV", status: "running" }), run({ connector: "gitlab", label: "GitLab", status: "pending" })],
      }),
      "GET /api/investigations/inv-1/profile": profileView(),
      "GET /api/investigations/inv-1/mentions": emptyMentions,
    });
    renderRoute("/investigations/inv-1");
    expect(await screen.findByText("Investigation running")).toBeInTheDocument();
    expect(screen.getByText("1 / 3 source checks complete")).toBeInTheDocument();
  });

  it("renders a populated profile with identity, presence and profiles", async () => {
    mockApi({
      "GET /api/investigations/inv-1": investigation(),
      "GET /api/investigations/inv-1/profile": profileView(),
      "GET /api/investigations/inv-1/mentions": emptyMentions,
    });
    renderRoute("/investigations/inv-1");
    expect(await screen.findByRole("heading", { level: 1, name: "Anirudh K" })).toBeInTheDocument();
    expect(screen.getAllByText("anirudh@example.com").length).toBeGreaterThan(0);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("High-confidence match")).toBeInTheDocument();
  });

  it("reports partial failure without hiding successful results", async () => {
    mockApi({
      "GET /api/investigations/inv-1": investigation({
        status: "partial",
        runs: [run(), run({ connector: "certificates", label: "Certificate Transparency", status: "error", message: "HTTP 502" })],
      }),
      "GET /api/investigations/inv-1/profile": profileView(),
      "GET /api/investigations/inv-1/mentions": emptyMentions,
    });
    renderRoute("/investigations/inv-1");
    expect(await screen.findByText("Investigation completed with partial results.")).toBeInTheDocument();
    expect(screen.getByText(/Certificate Transparency/)).toBeInTheDocument();
    expect(screen.getAllByText("anirudh@example.com").length).toBeGreaterThan(0);
  });

  it("explains that no results does not mean no presence", async () => {
    mockApi({
      "GET /api/investigations/inv-1": investigation({
        stats: stats({ profiles: 0, matched_profiles: 0, mentions: 0, confidence: null, level: null }),
        runs: [run({ status: "not_found" }), run({ connector: "x", label: "X", status: "requires_auth" })],
      }),
      "GET /api/investigations/inv-1/profile": profileView({ attributes: [], profiles: [], presence: [] }),
      "GET /api/investigations/inv-1/mentions": emptyMentions,
    });
    renderRoute("/investigations/inv-1");
    expect(await screen.findByText("No verified public presence found.")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();
    expect(screen.getByText(/Some sources may be\s+unavailable or require authentication/)).toBeInTheDocument();
  });
});

describe("evidence drawer", () => {
  it("answers 'why does the system believe this?' for an attribute", async () => {
    mockApi({
      "GET /api/investigations/inv-1": investigation(),
      "GET /api/investigations/inv-1/profile": profileView(),
      "GET /api/investigations/inv-1/mentions": emptyMentions,
    });
    renderRoute("/investigations/inv-1");
    await userEvent.click(await screen.findByRole("button", { name: /Email anirudh@example.com: show evidence/ }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("Evidence (2)")).toBeInTheDocument();
    expect(within(drawer).getByText("Independent sources")).toBeInTheDocument();
    const links = within(drawer).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(
      expect.arrayContaining(["https://api.github.com/users/anirudh123"]),
    );
    expect(links.every((a) => a.getAttribute("rel")?.includes("noreferrer"))).toBe(true);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
