import { useEvidence } from "../../context/evidence";
import { hostOf, relativeTime } from "../../lib/format";
import type { Mention } from "../../lib/types";
import { ConfidenceBadge } from "../ui/indicators";
import { Button, ExternalLink, Pill } from "../ui/primitives";

export function MentionCard({ mention: m }: { mention: Mention }) {
  const { open } = useEvidence();
  const when = m.published_at ?? m.observed_at;
  return (
    <article className="rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong">
      <header className="flex items-center justify-between gap-3 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          <span className="font-medium text-fg">{m.source.name}</span>
          <Pill>{m.category}</Pill>
        </div>
        <time dateTime={when} className="shrink-0 text-subtle" title={when}>
          {m.published_at ? relativeTime(m.published_at) : `observed ${relativeTime(m.observed_at)}`}
        </time>
      </header>
      <h3 className="mt-2 text-[13.5px] font-medium leading-snug text-fg">{m.title}</h3>
      {m.snippet && <p className="mt-1 line-clamp-2 text-[13px] [overflow-wrap:anywhere] text-muted">{m.snippet}</p>}
      <dl className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
        <div className="flex gap-1.5">
          <dt className="text-subtle">Source</dt>
          <dd className="text-muted">{hostOf(m.url)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-subtle">Evidence</dt>
          <dd className="text-muted">{m.association}</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt className="text-subtle">Confidence</dt>
          <dd>
            <ConfidenceBadge score={m.confidence} level={m.level} showPercent={false} />
          </dd>
        </div>
      </dl>
      <footer className="mt-3 flex gap-2">
        <ExternalLink
          href={m.url}
          className="inline-flex h-7 items-center rounded-md border border-line-strong bg-surface-2 px-2.5 text-xs font-medium text-fg hover:bg-surface-3"
        >
          View source
        </ExternalLink>
        <Button size="sm" variant="ghost" onClick={() => open({ type: "mention", mention: m })}>
          Inspect evidence
        </Button>
      </footer>
    </article>
  );
}
