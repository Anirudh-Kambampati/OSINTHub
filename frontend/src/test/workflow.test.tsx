import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { investigation, profileEntity, profileView } from "./fixtures";
import { mockApi, renderRoute } from "./render";

afterEach(() => vi.unstubAllGlobals());

const emptyMentions = { total: 0, counts: {}, items: [] };
const signedOut = { user: null, needs_setup: false, allow_registration: false };

describe("authentication", () => {
  it("sends signed-out users to the sign-in page", async () => {
    mockApi({}, { auth: signedOut });
    renderRoute("/investigations");
    expect(await screen.findByRole("heading", { name: "Sign in to OSINT Console" })).toBeInTheDocument();
  });

  it("offers first-run setup when no accounts exist", async () => {
    mockApi({}, { auth: { ...signedOut, needs_setup: true } });
    renderRoute("/");
    expect(await screen.findByRole("heading", { name: "Set up OSINT Console" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create administrator" })).toBeInTheDocument();
  });

  it("sends the CSRF header with every request", async () => {
    const fetchMock = mockApi({ "GET /api/investigations": [] });
    renderRoute("/investigations");
    await screen.findByText("No investigations yet");
    const headers = fetchMock.mock.calls.map(([, init]) => new Headers(init?.headers).get("X-OSINT-CSRF"));
    expect(headers.every((h) => h === "1")).toBe(true);
  });
});

describe("analyst workflow", () => {
  const base = {
    "GET /api/investigations/inv-1": investigation(),
    "GET /api/investigations/inv-1/mentions": emptyMentions,
  };

  it("groups profiles into identity clusters", async () => {
    const other = (key: string, label: string) =>
      profileEntity({
        id: key, key, label,
        data: { platform: key.split(":")[0], url: "https://example.com" },
        match: { score: 0.15, level: "low", label: "Conflicting evidence", cluster: 1, decision: null, decision_note: null, factors: [] },
      });
    mockApi({
      ...base,
      "GET /api/investigations/inv-1/profile": profileView({
        profiles: [profileEntity(), other("bluesky:x", "@x"), other("medium:x", "@x")],
      }),
    });
    renderRoute("/investigations/inv-1/profiles");
    expect(await screen.findByText(/Primary identity · 1/)).toBeInTheDocument();
    expect(screen.getByText(/Separate identity B · 2/)).toBeInTheDocument();
  });

  it("records a confirm decision from a profile card", async () => {
    const put = vi.fn(() => ({
      entity: { ...profileEntity(), match: { ...profileEntity().match!, decision: "confirmed", label: "Analyst confirmed" } },
      observations: [], relationships: [], mentions: 0,
    }));
    mockApi({ ...base, "GET /api/investigations/inv-1/profile": profileView(), "PUT /api/entities/ent-gh/decision": put });
    renderRoute("/investigations/inv-1/profiles");
    const card = (await screen.findAllByRole("group", { name: "Analyst decision" }))[0];
    await userEvent.click(within(card).getByTitle("Confirm: same entity as the subject"));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  });

  it("offers exports for the investigation", async () => {
    mockApi({ ...base, "GET /api/investigations/inv-1/profile": profileView() });
    renderRoute("/investigations/inv-1");
    await userEvent.click(await screen.findByRole("button", { name: "Export" }));
    const menu = screen.getByRole("menu");
    expect(within(menu).getByText("Printable report (HTML / PDF)").closest("a")).toHaveAttribute(
      "href", "/api/investigations/inv-1/report.html",
    );
    expect(within(menu).getByText("All observations").closest("a")).toHaveAttribute(
      "href", "/api/investigations/inv-1/export.csv?dataset=observations",
    );
  });
});

describe("responsive navigation", () => {
  it("opens the navigation drawer on small screens", async () => {
    mockApi({ "GET /api/investigations": [] });
    renderRoute("/investigations");
    await userEvent.click(await screen.findByRole("button", { name: "Open navigation" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("link", { name: /Settings/ })).toBeInTheDocument();
  });
});
