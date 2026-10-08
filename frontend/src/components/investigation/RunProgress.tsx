import { Ban, CircleCheck, CircleDashed, CircleMinus, CircleX, KeyRound, LoaderCircle, Timer } from "lucide-react";
import { RUN_STATUS_META } from "../../lib/meta";
import type { Run, RunStatus } from "../../lib/types";

const ICONS: Record<RunStatus, typeof CircleCheck> = {
  pending: CircleDashed,
  running: LoaderCircle,
  found: CircleCheck,
  not_found: CircleMinus,
  not_verified: Ban,
  error: CircleX,
  rate_limited: Timer,
  requires_auth: KeyRound,
  skipped: CircleMinus,
};

export function RunStatusIcon({ status }: { status: RunStatus }) {
  const Icon = ICONS[status];
  return (
    <Icon
      className={`size-3.5 shrink-0 ${status === "running" ? "animate-spin" : ""}`}
      style={{ color: RUN_STATUS_META[status].color }}
      aria-label={RUN_STATUS_META[status].label}
    />
  );
}

/** Live per-source progress: real statuses from the backend, no simulated delays. */
export function RunProgress({ runs }: { runs: Run[] }) {
  const done = runs.filter((r) => r.status !== "pending" && r.status !== "running").length;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs text-muted">
        <span>
          {done} / {runs.length} source checks complete
        </span>
      </div>
      <div className="mb-3 h-1 overflow-hidden rounded-full bg-surface-3">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-500"
          style={{ width: `${runs.length ? (done / runs.length) * 100 : 0}%` }}
        />
      </div>
      <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
        {runs.map((r) => (
          <li key={r.id} className="flex min-w-0 items-center gap-2 text-[13px]" title={r.message ?? undefined}>
            <RunStatusIcon status={r.status} />
            <span className="truncate text-fg">{r.label}</span>
            {r.phase > 1 && <span className="truncate text-[11px] text-subtle">{r.target}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
