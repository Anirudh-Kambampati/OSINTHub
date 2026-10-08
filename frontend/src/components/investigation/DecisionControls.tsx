import clsx from "clsx";
import { CircleCheck, CircleX, Undo2 } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { useDecision } from "../../hooks/queries";
import type { Entity } from "../../lib/types";
import { ErrorNotice } from "../ui/primitives";

/** Analyst verdict on a discovered profile. It overrides the resolver and re-scores the investigation. */
export function DecisionControls({ profile, compact }: { profile: Entity; compact?: boolean }) {
  const { id: investigationId } = useParams();
  const decide = useDecision(investigationId);
  const [note, setNote] = useState("");
  const current = profile.match?.decision ?? null;

  const run = (decision: "confirmed" | "rejected" | null) =>
    decide.mutate({ entityId: profile.id, decision, note: note.trim() || undefined });

  if (compact) {
    return (
      <div className="flex items-center gap-1" role="group" aria-label="Analyst decision">
        <button
          type="button"
          title="Confirm: same entity as the subject"
          aria-pressed={current === "confirmed"}
          disabled={decide.isPending}
          onClick={() => run(current === "confirmed" ? null : "confirmed")}
          className={clsx("rounded p-1", current === "confirmed" ? "text-[var(--st-found)]" : "text-subtle hover:text-[var(--st-found)]")}
        >
          <CircleCheck className="size-4" />
        </button>
        <button
          type="button"
          title="Reject: a different entity"
          aria-pressed={current === "rejected"}
          disabled={decide.isPending}
          onClick={() => run(current === "rejected" ? null : "rejected")}
          className={clsx("rounded p-1", current === "rejected" ? "text-[var(--st-error)]" : "text-subtle hover:text-[var(--st-error)]")}
        >
          <CircleX className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-line bg-surface-2 p-3">
      <div className="text-xs text-muted">
        {current === "confirmed"
          ? "You confirmed this profile belongs to the subject."
          : current === "rejected"
            ? "You marked this profile as a different entity."
            : "Is this the same entity as the subject? Your verdict overrides the automated score."}
        {profile.match?.decision_note && <div className="mt-1 text-fg">“{profile.match.decision_note}”</div>}
      </div>
      {!current && (
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={1000}
          placeholder="Reason (optional)"
          aria-label="Decision note"
          className="h-7 w-full rounded border border-line-strong bg-surface px-2 text-xs text-fg outline-none focus:border-accent/60"
        />
      )}
      <div className="flex flex-wrap gap-2">
        {current ? (
          <button type="button" onClick={() => run(null)} disabled={decide.isPending}
            className="inline-flex items-center gap-1 rounded-md border border-line-strong px-2.5 py-1 text-xs text-fg hover:bg-surface-3">
            <Undo2 className="size-3.5" /> Clear decision
          </button>
        ) : (
          <>
            <button type="button" onClick={() => run("confirmed")} disabled={decide.isPending}
              className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs"
              style={{ color: "var(--st-found)", borderColor: "color-mix(in srgb, var(--st-found) 40%, transparent)" }}>
              <CircleCheck className="size-3.5" /> Confirm same entity
            </button>
            <button type="button" onClick={() => run("rejected")} disabled={decide.isPending}
              className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs"
              style={{ color: "var(--st-error)", borderColor: "color-mix(in srgb, var(--st-error) 40%, transparent)" }}>
              <CircleX className="size-3.5" /> Different entity
            </button>
          </>
        )}
      </div>
      {decide.error && <ErrorNotice error={decide.error} />}
    </div>
  );
}
