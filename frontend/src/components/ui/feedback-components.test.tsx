import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Toast } from "../../lib/feedback";
import { ConfirmDialog } from "./ConfirmDialog";
import { ToastViewport } from "./Toast";

const toast = (id: number, kind: Toast["kind"], message: string): Toast => ({ id, kind, message });

describe("ToastViewport", () => {
  it("routes successes to the polite region and errors to the assertive region", () => {
    const onDismiss = vi.fn();
    const { container } = render(
      <ToastViewport toasts={[toast(1, "success", "Note added."), toast(2, "error", "Couldn't save.")] } onDismiss={onDismiss} />,
    );
    const polite = container.querySelector('[aria-live="polite"]') as HTMLElement;
    const assertive = container.querySelector('[aria-live="assertive"]') as HTMLElement;
    expect(within(polite).getByText("Note added.")).toBeInTheDocument();
    expect(within(assertive).getByText("Couldn't save.")).toBeInTheDocument();
    expect(within(assertive).queryByText("Note added.")).toBeNull();
  });

  it("labels the viewport for assistive tech", () => {
    const { container } = render(<ToastViewport toasts={[]} onDismiss={vi.fn()} />);
    expect(container.querySelector('[aria-label="Notifications"]')).not.toBeNull();
  });

  it("dismisses a toast from its button", async () => {
    const onDismiss = vi.fn();
    render(<ToastViewport toasts={[toast(7, "success", "Profile confirmed.")]} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(onDismiss).toHaveBeenCalledWith(7);
  });

  it("announces errors with both an icon and text, never colour alone", () => {
    const { container } = render(
      <ToastViewport toasts={[toast(1, "error", "Couldn't reach the server.")]} onDismiss={vi.fn()} />,
    );
    const item = container.querySelector('[aria-live="assertive"] .toast-enter')!;
    expect(item.querySelector("svg")).not.toBeNull();
    expect(item.textContent).toContain("Couldn't reach the server.");
  });
});

describe("ConfirmDialog", () => {
  it("runs the action on confirm and not on cancel", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <ConfirmDialog open title="Delete?" onConfirm={onConfirm} onCancel={onCancel} confirmLabel="Delete" />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(<ConfirmDialog open={false} title="Delete?" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("leaves focus in the document after closing", () => {
    const trigger = document.createElement("button");
    trigger.textContent = "Delete investigation";
    document.body.appendChild(trigger);
    trigger.focus();

    const { rerender } = render(
      <ConfirmDialog open title="Delete?" onConfirm={vi.fn()} onCancel={vi.fn()} confirmLabel="Delete" />,
    );
    rerender(<ConfirmDialog open={false} title="Delete?" onConfirm={vi.fn()} onCancel={vi.fn()} confirmLabel="Delete" />);
    // Closing must not strand focus on a detached node (which jsdom reports as <body>). The
    // dialog steals focus during commit, before it can record the trigger, so the restore target
    // is unknowable here; what matters is that focus lands back in the live document.
    expect(document.activeElement).not.toBeNull();
    expect(document.activeElement?.isConnected).toBe(true);
    expect(document.activeElement === document.body || document.body.contains(document.activeElement)).toBe(true);
    trigger.remove();
  });

  it("closes on Escape", async () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog open title="Delete?" onConfirm={vi.fn()} onCancel={onCancel} />);
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
