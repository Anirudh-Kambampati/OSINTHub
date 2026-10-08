import { useEvidence } from "../../context/evidence";
import { PLATFORM_META } from "../../lib/meta";
import type { TimelineEvent } from "../../lib/types";
import { ConfidenceBadge } from "../ui/indicators";
import { ExternalLink, Pill } from "../ui/primitives";

const KIND_COLOR: Record<string, string> = {
  profile: "var(--conf-high)",
  mention: "var(--conf-medium)",
  repository: "var(--st-auth)",
  document: "var(--st-rate-limited)",
  domain: "var(--conf-very-high)",
  certificate: "var(--conf-very-high)",
  archive: "var(--text-muted)",
};

const monthDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit" });

export function Timeline({ events }: { events: TimelineEvent[] }) {
  const { open } = useEvidence();
  const byYear = new Map<number, TimelineEvent[]>();
  for (const e of events) {
    const y = new Date(e.occurred_at).getFullYear();
    byYear.set(y, [...(byYear.get(y) ?? []), e]);
  }
  return (
    <ol className="space-y-8">
      {[...byYear.entries()].map(([year, items]) => (
        <li key={year}>
          <h3 className="mb-3 font-mono text-sm font-semibold text-fg">{year}</h3>
          <ol className="relative ml-[72px] border-l border-line">
            {items.map((e) => (
              <li key={e.id} className="relative pb-4 pl-5 last:pb-0">
                <time
                  dateTime={e.occurred_at}
                  className="absolute top-0.5 -left-[72px] w-14 text-right font-mono text-[11px] text-subtle tabular-nums"
                >
                  {monthDay.format(new Date(e.occurred_at))}
                </time>
                <span
                  className="absolute top-1.5 -left-[4.5px] size-2 rounded-full ring-4 ring-bg"
                  style={{ background: KIND_COLOR[e.kind] ?? "var(--text-muted)" }}
                  aria-hidden
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] text-fg">{e.title}</span>
                  <Pill>{e.kind}</Pill>
                </div>
                {e.detail && <div className="mt-0.5 line-clamp-1 text-xs text-muted">{e.detail}</div>}
                <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-subtle">
                  <ExternalLink href={e.source.url} icon={false}>
                    via {e.source.name}
                  </ExternalLink>
                  {e.entity && (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 hover:text-accent"
                      onClick={() => open({ type: "entity", id: e.entity!.id })}
                      title="How strongly this entity is linked to the subject"
                    >
                      {e.entity.platform ? `${PLATFORM_META[e.entity.platform]?.label ?? e.entity.platform} ` : ""}
                      {e.entity.label}
                      {e.entity.confidence !== null && <ConfidenceBadge score={e.entity.confidence} showPercent={false} />}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </li>
      ))}
    </ol>
  );
}
