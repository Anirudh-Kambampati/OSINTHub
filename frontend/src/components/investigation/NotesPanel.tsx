import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useCurrentUser } from "../../context/auth";
import { useFeedback } from "../../context/FeedbackContext";
import { useAddNote, useDeleteNote, useNotes } from "../../hooks/queries";
import { relativeTime } from "../../lib/format";
import { Button, Card, ErrorNotice, Skeleton } from "../ui/primitives";

export function NotesPanel({ investigationId }: { investigationId: string }) {
  const me = useCurrentUser();
  const { notify } = useFeedback();
  const { data: notes, isLoading } = useNotes(investigationId);
  const add = useAddNote(investigationId);
  const del = useDeleteNote(investigationId);
  const [body, setBody] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (body.trim())
      add.mutate(body.trim(), {
        onSuccess: () => {
          setBody("");
          notify("success", "Note added.");
        },
      });
  };
  return (
    <Card title="Analyst notes">
      <form onSubmit={submit} className="space-y-2">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          maxLength={10_000}
          rows={3}
          placeholder="Record hypotheses, next steps or why you confirmed a profile…"
          aria-label="New note"
          className="w-full resize-y rounded-md border border-line-strong bg-surface-2 px-3 py-2 text-[13px] text-fg outline-none placeholder:text-subtle focus:border-accent/60"
        />
        <div className="flex justify-end">
          <Button type="submit" size="sm" variant="primary" disabled={!body.trim() || add.isPending}>Add note</Button>
        </div>
        {add.error && <ErrorNotice error={add.error} />}
      </form>
      {isLoading ? <Skeleton className="mt-3 h-12" /> : (
        <ul className="mt-3 space-y-3">
          {notes?.map((n) => (
            <li key={n.id} className="group border-l-2 border-line-strong pl-3">
              <div className="flex items-center gap-2 text-[11px] text-subtle">
                <span className="text-muted">{n.author_name ?? "Former user"}</span>
                <span>{relativeTime(n.created_at)}</span>
                {(n.author_id === me?.id || me?.role === "admin") && (
                  <button type="button" aria-label="Delete note" onClick={() => del.mutate(n.id, { onSuccess: () => notify("success", "Note deleted.") })}
                    className="ml-auto opacity-0 group-hover:opacity-100 hover:text-[var(--st-error)] focus:opacity-100">
                    <Trash2 className="size-3.5" />
                  </button>
                )}
              </div>
              <p className="mt-0.5 text-[13px] whitespace-pre-wrap text-fg">{n.body}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
