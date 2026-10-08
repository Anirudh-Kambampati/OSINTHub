import { Network } from "lucide-react";
import { useState } from "react";
import { GraphView } from "../../components/investigation/GraphView";
import { EmptyState, ErrorNotice, Skeleton } from "../../components/ui/primitives";
import { useGraph } from "../../hooks/queries";
import { useInvestigationContext } from "../InvestigationLayout";

export function GraphTab() {
  const { inv, active } = useInvestigationContext();
  const [withMentions, setWithMentions] = useState(false);
  const { data, isLoading, error } = useGraph(inv.id, withMentions, active);
  return (
    <div className="flex min-h-[640px] flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-line px-6 py-2.5">
        <p className="text-xs text-muted">
          {data ? `${data.nodes.length} entities · ${data.edges.length} relationships` : "Loading graph…"}
          {data?.truncated && " · showing highest-confidence entities"}
        </p>
        <label className="flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={withMentions} onChange={(e) => setWithMentions(e.target.checked)} className="accent-[var(--accent)]" />
          Include mentions
        </label>
      </div>
      <div className="relative flex-1">
        {error ? <div className="p-6"><ErrorNotice error={error} /></div> : isLoading || !data ? (
          <Skeleton className="absolute inset-6" />
        ) : data.nodes.length <= 1 ? (
          <EmptyState icon={<Network className="size-8" />} title="No relationships yet" className="absolute inset-0" />
        ) : (
          <div className="absolute inset-0"><GraphView graph={data} /></div>
        )}
      </div>
    </div>
  );
}
