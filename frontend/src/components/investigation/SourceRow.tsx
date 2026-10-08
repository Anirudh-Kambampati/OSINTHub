import { formatDateTime } from "../../lib/format";
import type { Source } from "../../lib/types";
import { ExternalLink, Pill } from "../ui/primitives";

const RELIABILITY_COLOR = { high: "var(--conf-very-high)", medium: "var(--conf-medium)", low: "var(--conf-low)" };

export function SourceRow({ source, compact }: { source: Source; compact?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <ExternalLink href={source.url} className="truncate font-medium text-fg">
          {source.name}
        </ExternalLink>
        <Pill>{source.kind.replace(/_/g, " ")}</Pill>
        {!compact && <Pill color={RELIABILITY_COLOR[source.reliability]}>{source.reliability} reliability</Pill>}
      </div>
      {!compact && source.title && <div className="mt-0.5 truncate text-xs text-muted">{source.title}</div>}
      <div className="mt-0.5 text-[11px] text-subtle">Collected {formatDateTime(source.collected_at)}</div>
    </div>
  );
}
