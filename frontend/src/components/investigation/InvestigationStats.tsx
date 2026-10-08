import { formatConfidence } from "../../lib/format";
import { CONFIDENCE_META } from "../../lib/meta";
import type { Stats } from "../../lib/types";

function Tile({ label, value, hint, color }: { label: string; value: string | number; hint?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3" title={hint}>
      <div className="font-mono text-xl font-semibold tabular-nums" style={{ color: color ?? "var(--text)" }}>
        {value}
      </div>
      <div className="label-caps mt-0.5">{label}</div>
    </div>
  );
}

export function InvestigationStats({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      <Tile
        label="Profiles"
        value={stats.profiles}
        hint={`${stats.matched_profiles} of ${stats.profiles} profiles reach at least a possible match`}
      />
      <Tile label="Mentions" value={stats.mentions} />
      <Tile label="Sources" value={stats.sources} hint="Individual retrievals with provenance" />
      <Tile label="Relationships" value={stats.relationships} />
      <Tile label="Documents" value={stats.documents} />
      <Tile label="Domains" value={stats.domains} />
      <Tile
        label="Confidence"
        value={formatConfidence(stats.confidence)}
        color={stats.level ? CONFIDENCE_META[stats.level].color : undefined}
        hint="Mean match score of the profiles that make up the identity"
      />
    </div>
  );
}
