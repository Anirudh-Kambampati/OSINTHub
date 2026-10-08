import { ArrowLeft, CircleCheck, CircleMinus, CirclePlus, Info } from "lucide-react";
import type { ReactNode } from "react";
import { useEvidence, type EvidenceTarget } from "../../context/evidence";
import { useEntityEvidence } from "../../hooks/queries";
import { formatConfidence, formatDate, formatDateTime } from "../../lib/format";
import { ENTITY_KIND_LABEL, PLATFORM_META, RUN_STATUS_META, attributeLabel } from "../../lib/meta";
import type { IdentityAttribute, ImageCandidate, Match, Mention, Observation, Presence } from "../../lib/types";
import { ConfidenceBadge, PlatformMark, RunStatusBadge } from "../ui/indicators";
import { ErrorNotice, ExternalLink, Pill, Skeleton } from "../ui/primitives";
import { ProxiedAvatar } from "../ui/ProxiedAvatar";
import { DecisionControls } from "./DecisionControls";
import { SourceRow } from "./SourceRow";

export function evidenceTitle(t: EvidenceTarget): { title: string; subtitle?: string } {
  switch (t.type) {
    case "attribute":
      return { title: t.attribute.value, subtitle: `${attributeLabel(t.attribute.attribute)} · evidence` };
    case "entity":
      return { title: "Entity inspector", subtitle: "Observations, relationships and provenance" };
    case "images":
      return { title: "Image sources", subtitle: t.label };
    case "mention":
      return { title: t.mention.title, subtitle: "Mention · evidence" };
    case "presence":
      return { title: t.presence.label, subtitle: "Source status" };
  }
}

export function EvidenceContent({ target, onBack }: { target: EvidenceTarget; onBack?: () => void }) {
  return (
    <div className="space-y-5">
      {onBack && (
        <button type="button" onClick={onBack} className="flex items-center gap-1 text-xs text-muted hover:text-fg">
          <ArrowLeft className="size-3.5" /> Back
        </button>
      )}
      {target.type === "attribute" && <AttributeEvidence attribute={target.attribute} />}
      {target.type === "entity" && <EntityInspector entityId={target.id} />}
      {target.type === "images" && <ImageSources images={target.images} />}
      {target.type === "mention" && <MentionEvidence mention={target.mention} />}
      {target.type === "presence" && <PresenceEvidence presence={target.presence} />}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="label-caps mb-2">{title}</h3>
      {children}
    </section>
  );
}

function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[140px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words text-fg">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Explainer({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-xs text-muted">
      <Info className="mt-px size-3.5 shrink-0 text-subtle" />
      <div>{children}</div>
    </div>
  );
}

function AttributeEvidence({ attribute: a }: { attribute: IdentityAttribute }) {
  const { open } = useEvidence();
  return (
    <>
      <KeyValue
        items={[
          ["Confidence", <ConfidenceBadge key="c" score={a.confidence} level={a.level} />],
          ["Independent sources", a.source_count],
          ["First observed", formatDateTime(a.first_observed)],
          ["Last observed", formatDateTime(a.last_observed)],
        ]}
      />
      <Explainer>
        Confidence combines each independent source's reliability, how confidently that source states the value,
        and how strongly the profile it appeared on matches the investigated subject. Agreement between independent
        sources raises confidence; a single source never makes a value certain.
      </Explainer>
      <Section title={`Evidence (${a.evidence.length})`}>
        <ul className="space-y-2">
          {a.evidence.map((e) => (
            <li key={e.observation_id} className="rounded-md border border-line bg-surface-2 p-3">
              <div className="flex items-start gap-2">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--st-found)]" aria-label="Observed" />
                <div className="min-w-0 flex-1 space-y-1.5">
                  <SourceRow source={e.source} compact />
                  <div className="text-xs text-muted">
                    Stated on{" "}
                    <button
                      type="button"
                      className="text-fg underline decoration-line-strong underline-offset-2 hover:text-accent"
                      onClick={() => open({ type: "entity", id: e.entity.id })}
                    >
                      {e.entity.platform ? `${PLATFORM_META[e.entity.platform]?.label ?? e.entity.platform} ` : ""}
                      {e.entity.label}
                    </button>{" "}
                    as <span className="font-mono text-fg">{e.value}</span>
                  </div>
                  <div className="flex flex-wrap gap-3 text-[11px] text-subtle">
                    <span>Source confidence {formatConfidence(e.confidence)}</span>
                    <span>Subject match weight {formatConfidence(e.weight)}</span>
                    <span>Observed {formatDate(e.observed_at)}</span>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

export function MatchFactors({ match }: { match: Match }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-fg">{match.label}</span>
        <ConfidenceBadge score={match.score} level={match.level} />
      </div>
      <ul className="space-y-1">
        {match.factors.map((f, i) => (
          <li key={`${f.code}-${i}`} className="flex items-start gap-2 text-xs">
            {f.weight >= 0 ? (
              <CirclePlus className="mt-px size-3.5 shrink-0 text-[var(--st-found)]" aria-label="Supporting" />
            ) : (
              <CircleMinus className="mt-px size-3.5 shrink-0 text-[var(--st-error)]" aria-label="Contradicting" />
            )}
            <span className="flex-1 text-muted">{f.label}</span>
            <span className="font-mono tabular-nums text-subtle">
              {f.weight >= 0 ? "+" : ""}
              {Math.round(f.weight * 100)}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-subtle">
        Matching usernames alone never establish identity. Scores are capped below certainty.
      </p>
    </div>
  );
}

function groupObservations(observations: Observation[]) {
  const groups = new Map<string, Observation[]>();
  for (const o of observations) groups.set(o.attribute, [...(groups.get(o.attribute) ?? []), o]);
  return [...groups.entries()];
}

function EntityInspector({ entityId }: { entityId: string }) {
  const { open } = useEvidence();
  const { data, isLoading, error } = useEntityEvidence(entityId);
  if (isLoading)
    return (
      <div className="space-y-3">
        <Skeleton className="h-10" />
        <Skeleton className="h-32" />
        <Skeleton className="h-24" />
      </div>
    );
  if (error || !data) return <ErrorNotice error={error} />;
  const e = data.entity;
  const platform = e.data.platform;
  return (
    <>
      <div className="flex items-center gap-3">
        {e.avatar_observation_id ? (
          <ProxiedAvatar observationId={e.avatar_observation_id} label={e.label} size={44} />
        ) : platform ? (
          <PlatformMark platform={platform} size={44} />
        ) : null}
        <div className="min-w-0">
          <div className="label-caps">
            {platform ? `${PLATFORM_META[platform]?.label ?? platform} · ` : ""}
            {ENTITY_KIND_LABEL[e.kind] ?? e.kind}
          </div>
          <div className="truncate text-base font-semibold text-fg">{e.label}</div>
        </div>
      </div>
      <KeyValue
        items={[
          ["Type", ENTITY_KIND_LABEL[e.kind] ?? e.kind],
          ["Confidence", <ConfidenceBadge key="c" score={e.confidence} level={e.level} />],
          ...(e.data.url
            ? ([["Source", <ExternalLink key="u" href={String(e.data.url)}>{String(e.data.url)}</ExternalLink>]] as [
                string,
                ReactNode,
              ][])
            : []),
          ["Mentions", data.mentions],
        ]}
      />
      {e.match && (
        <Section title="Why this is linked to the subject">
          <MatchFactors match={e.match} />
        </Section>
      )}
      {e.kind === "profile" && (
        <Section title="Analyst decision">
          <DecisionControls profile={e} />
        </Section>
      )}
      {data.observations.length > 0 && (
        <Section title="Observations">
          <div className="space-y-3">
            {groupObservations(data.observations).map(([attr, obs]) => (
              <div key={attr}>
                <div className="mb-1 text-xs font-medium text-muted">{attributeLabel(attr)}</div>
                <ul className="space-y-1">
                  {obs.map((o) => (
                    <li key={o.id} className="flex items-start justify-between gap-3 text-[13px]">
                      <span className="min-w-0 break-words text-fg">{o.value}</span>
                      <span className="shrink-0 text-[11px] text-subtle">
                        <ExternalLink href={o.source.url} icon={false}>
                          {o.source.name}
                        </ExternalLink>{" "}
                        · {formatDate(o.observed_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}
      {data.relationships.length > 0 && (
        <Section title={`Related entities (${data.relationships.length})`}>
          <ul className="divide-y divide-line rounded-md border border-line">
            {data.relationships.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-3 py-2">
                <span className="w-28 shrink-0 font-mono text-[10.5px] text-subtle">
                  {r.direction === "out" ? `${r.type} →` : `← ${r.type}`}
                </span>
                <button
                  type="button"
                  onClick={() => open({ type: "entity", id: r.other.id })}
                  className="min-w-0 flex-1 truncate text-left text-[13px] text-fg hover:text-accent"
                >
                  {r.other.label}
                  <span className="ml-1.5 text-[11px] text-subtle">{ENTITY_KIND_LABEL[r.other.kind] ?? r.other.kind}</span>
                </button>
                {r.inferred ? (
                  <Pill color="var(--conf-medium)">inferred</Pill>
                ) : (
                  r.source && (
                    <ExternalLink href={r.source.url} icon={false} className="shrink-0 text-[11px] text-subtle">
                      {r.source.name}
                    </ExternalLink>
                  )
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

function ImageSources({ images }: { images: ImageCandidate[] }) {
  return (
    <>
      <Explainer>
        Images are shown as published on each source and loaded through the server, so your browser never contacts the
        platform. Visual similarity is <strong>not</strong> treated as identity evidence.
      </Explainer>
      <ul className="space-y-2">
        {images.map((img) => (
          <li key={img.observation_id} className="flex gap-3 rounded-md border border-line bg-surface-2 p-3">
            <ProxiedAvatar observationId={img.observation_id} label={img.entity.label} size={56} rounded="md" />
            <div className="min-w-0 flex-1 space-y-1">
              <SourceRow source={img.source} compact />
              <div className="text-xs text-muted">From {img.entity.label}</div>
              <div className="flex flex-wrap gap-3 text-[11px] text-subtle">
                <ConfidenceBadge score={img.confidence} level={img.level} />
                <span>First observed {formatDate(img.first_observed)}</span>
                <span>Last observed {formatDate(img.last_observed)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function MentionEvidence({ mention: m }: { mention: Mention }) {
  const { open } = useEvidence();
  return (
    <>
      {m.snippet && <blockquote className="border-l-2 border-line-strong pl-3 text-[13px] text-muted">{m.snippet}</blockquote>}
      <KeyValue
        items={[
          ["Association", m.association],
          ["Confidence", <ConfidenceBadge key="c" score={m.confidence} level={m.level} />],
          ["Published", formatDateTime(m.published_at)],
          ["Observed", formatDateTime(m.observed_at)],
          ["Link", <ExternalLink key="l" href={m.url}>{m.url}</ExternalLink>],
          ...(m.entity
            ? ([
                [
                  "Linked entity",
                  <button key="e" type="button" className="hover:text-accent" onClick={() => open({ type: "entity", id: m.entity!.id })}>
                    {m.entity.label}
                  </button>,
                ],
              ] as [string, ReactNode][])
            : []),
        ]}
      />
      <Section title="Retrieved via">
        <SourceRow source={m.source} />
      </Section>
      {m.association.includes("unverified") || m.association.includes("text match") ? (
        <Explainer>
          This mention matched the search text only. A text match is not evidence that it concerns the same person.
        </Explainer>
      ) : null}
    </>
  );
}

function PresenceEvidence({ presence: p }: { presence: Presence }) {
  const { open } = useEvidence();
  return (
    <>
      <KeyValue
        items={[
          ["Status", <RunStatusBadge key="s" status={p.status} />],
          ["Queried for", <span key="t" className="font-mono">{p.target}</span>],
          ["Meaning", RUN_STATUS_META[p.status].description],
          ...(p.message ? ([["Detail", p.message]] as [string, ReactNode][]) : []),
        ]}
      />
      {p.profile && (
        <button
          type="button"
          onClick={() => open({ type: "entity", id: p.profile!.id })}
          className="text-[13px] text-accent hover:underline"
        >
          Inspect discovered profile →
        </button>
      )}
      {p.manual_url && p.status !== "found" && (
        <Explainer>
          You can check manually:{" "}
          <ExternalLink href={p.manual_url} className="text-fg">
            {p.manual_url}
          </ExternalLink>
          . Anything you find there is not recorded as evidence.
        </Explainer>
      )}
    </>
  );
}
