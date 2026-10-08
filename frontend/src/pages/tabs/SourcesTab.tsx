import { useNavigate, useParams } from "react-router";
import { RunStatusIcon } from "../../components/investigation/RunProgress";
import { SourceRow } from "../../components/investigation/SourceRow";
import { RunStatusBadge } from "../../components/ui/indicators";
import { Card, EmptyState, ExternalLink, SegmentedControl, Skeleton } from "../../components/ui/primitives";
import { useSources } from "../../hooks/queries";
import { SOURCE_GROUPS } from "../../lib/meta";
import { useInvestigationContext } from "../InvestigationLayout";

const GROUP_OPTIONS = [{ key: "", label: "All" }, ...Object.entries(SOURCE_GROUPS).map(([key, g]) => ({ key, label: g.label }))];

export function SourcesTab() {
  const { inv, active } = useInvestigationContext();
  const { group = "" } = useParams();
  const navigate = useNavigate();
  const { data: sources, isLoading } = useSources(inv.id, active);
  const categories = SOURCE_GROUPS[group]?.categories;
  const inGroup = (category: string) => !categories || categories.includes(category);
  const runs = inv.runs.filter((r) => inGroup(r.category));
  const retrievals = (sources ?? []).filter((s) => inGroup(s.category));

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-5 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">Sources & provenance</h2>
          <p className="text-xs text-muted">
            What was queried, what each source returned, and every retrieval that backs an observation.
          </p>
        </div>
        <SegmentedControl
          label="Source group"
          options={GROUP_OPTIONS}
          value={group}
          onChange={(g) => navigate(g ? `../sources/${g}` : "../sources", { relative: "path" })}
        />
      </div>

      <Card title={`Source checks (${runs.length})`} bodyClassName="p-0">
        {runs.length === 0 ? (
          <EmptyState title="No source checks in this group" className="py-6" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-line text-xs text-subtle">
                <tr>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Target</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Results</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {runs.map((r) => (
                  <tr key={r.id} className="align-top">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <RunStatusIcon status={r.status} />
                        <span className="text-fg">{r.label}</span>
                        {r.phase > 1 && <span className="text-[11px] text-subtle">pivot</span>}
                      </div>
                    </td>
                    <td className="max-w-56 truncate px-4 py-2 font-mono text-xs text-muted" title={r.target}>{r.target}</td>
                    <td className="px-4 py-2"><RunStatusBadge status={r.status} /></td>
                    <td className="px-4 py-2 font-mono text-xs text-muted tabular-nums">{r.result_count}</td>
                    <td className="px-4 py-2 text-xs text-muted">
                      {r.message}
                      {r.manual_url && r.status !== "found" && (
                        <div className="mt-0.5">
                          <ExternalLink href={r.manual_url} className="text-subtle">Check manually (not recorded as evidence)</ExternalLink>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Retrievals (${retrievals.length})`}>
        {isLoading ? <Skeleton className="h-32" /> : retrievals.length === 0 ? (
          <EmptyState title="No retrievals yet" className="py-6">
            Retrievals are recorded only when a source actually returned data.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {retrievals.map((s) => (
              <li key={s.id} className="py-2.5 first:pt-0 last:pb-0"><SourceRow source={s} /></li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
