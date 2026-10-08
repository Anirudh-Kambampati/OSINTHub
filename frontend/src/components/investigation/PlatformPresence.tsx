import { useEvidence } from "../../context/evidence";
import type { Presence } from "../../lib/types";
import { ConfidenceBadge, PlatformMark, RunStatusBadge } from "../ui/indicators";
import { Card, EmptyState } from "../ui/primitives";

const ORDER: Record<string, number> = { found: 0, running: 1, pending: 2, not_found: 3, not_verified: 4, requires_auth: 5, rate_limited: 6, error: 7 };

export function PlatformPresence({ presence }: { presence: Presence[] }) {
  const { open } = useEvidence();
  const rows = [...presence].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9));
  return (
    <Card title="Platform presence" bodyClassName="p-0">
      {rows.length === 0 ? (
        <EmptyState title="No profile sources apply to this seed type" className="py-6" />
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((p) => (
            <li key={p.connector}>
              <button
                type="button"
                onClick={() => open(p.profile ? { type: "entity", id: p.profile.id } : { type: "presence", presence: p })}
                className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-surface-2"
              >
                <PlatformMark platform={p.connector} size={22} />
                <span className="w-28 shrink-0 truncate text-[13px] text-fg">{p.label}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted">
                  {p.profile ? p.profile.label : (p.message ?? "")}
                </span>
                {p.profile?.match && <ConfidenceBadge score={p.profile.match.score} level={p.profile.match.level} />}
                <RunStatusBadge status={p.status} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
