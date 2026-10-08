import { FolderSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ConfidenceBadge, InvestigationStatusBadge } from "../components/ui/indicators";
import { EmptyState, ErrorNotice, Pill, Skeleton } from "../components/ui/primitives";
import { useInvestigations } from "../hooks/queries";
import { relativeTime } from "../lib/format";
import { SEED_TYPE_LABEL } from "../lib/meta";
import type { Investigation } from "../lib/types";

export function InvestigationTable({ investigations }: { investigations: Investigation[] }) {
  const navigate = useNavigate();
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-left text-[13px]">
        <thead className="border-b border-line text-xs text-subtle">
          <tr>
            <th className="px-4 py-2 font-medium">Investigation</th>
            <th className="px-4 py-2 font-medium">Seed</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 text-right font-medium">Profiles</th>
            <th className="px-4 py-2 text-right font-medium">Mentions</th>
            <th className="px-4 py-2 font-medium">Confidence</th>
            <th className="px-4 py-2 font-medium">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {investigations.map((i) => (
            <tr
              key={i.id}
              tabIndex={0}
              onClick={() => navigate(`/investigations/${i.id}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/investigations/${i.id}`)}
              className="cursor-pointer hover:bg-surface-2"
            >
              <td className="px-4 py-2.5">
                <div className="font-medium text-fg">{i.title}</div>
                {(i.tags.length > 0 || i.monitor_interval_hours) && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {i.monitor_interval_hours && <Pill color="var(--accent)">monitored</Pill>}
                    {i.tags.map((t) => <Pill key={t}>{t}</Pill>)}
                  </div>
                )}
              </td>
              <td className="px-4 py-2.5">
                <span className="font-mono text-xs text-muted">{i.seed}</span>
                <span className="ml-2 text-[11px] text-subtle">{SEED_TYPE_LABEL[i.seed_type]}</span>
              </td>
              <td className="px-4 py-2.5"><InvestigationStatusBadge status={i.status} /></td>
              <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted">{i.stats.profiles}</td>
              <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted">{i.stats.mentions}</td>
              <td className="px-4 py-2.5"><ConfidenceBadge score={i.stats.confidence} level={i.stats.level} /></td>
              <td className="px-4 py-2.5 text-xs text-subtle">{relativeTime(i.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InvestigationsPage() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  const { data, isLoading, error } = useInvestigations(debounced);
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold text-fg">Investigations</h1>
          <p className="text-xs text-muted">Each search creates an investigation with its own evidence and provenance.</p>
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by seed or title…"
          aria-label="Filter investigations"
          className="h-8 w-64 rounded-md border border-line-strong bg-surface-2 px-2.5 text-[13px] text-fg outline-none focus:border-accent/60"
        />
      </div>
      {error ? <ErrorNotice error={error} /> : isLoading ? <Skeleton className="h-48" /> : !data?.length ? (
        <EmptyState icon={<FolderSearch className="size-8" />} title={debounced ? "No matching investigations" : "No investigations yet"}>
          {debounced ? "Try a different filter." : "Use the search bar above to start one."}
        </EmptyState>
      ) : (
        <InvestigationTable investigations={data} />
      )}
    </div>
  );
}
