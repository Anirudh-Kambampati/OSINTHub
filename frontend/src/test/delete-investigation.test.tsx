import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { investigation } from "./fixtures";
import { mockApi, renderRoute } from "./render";

afterEach(() => vi.unstubAllGlobals());

describe("delete investigation confirmation", () => {
  it("does not delete until the dialog is confirmed", async () => {
    const del = vi.fn();
    const fetchMock = mockApi({
      "GET /api/investigations/inv-1": investigation(),
      "DELETE /api/investigations/inv-1": del,
    });
    renderRoute("/investigations/inv-1");

    await userEvent.click(await screen.findByRole("button", { name: "Delete investigation" }));
    const dialog = await screen.findByRole("alertdialog", { name: /Delete this investigation/ });
    expect(within(dialog).getByText(/can’t be undone/)).toBeInTheDocument();

    // Cancel closes without deleting.
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(del).not.toHaveBeenCalled();

    // Reopen and confirm: the DELETE fires and a success toast follows.
    await userEvent.click(screen.getByRole("button", { name: "Delete investigation" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Investigation deleted."));

    const deleteCalls = fetchMock.mock.calls.filter(([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE");
    expect(deleteCalls).toHaveLength(1);
  });
});
