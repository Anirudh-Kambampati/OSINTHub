import { useEvidence } from "../../context/evidence";
import { PLATFORM_META } from "../../lib/meta";
import type { Entity } from "../../lib/types";
import { ConfidenceBadge, ConfidenceBar, PlatformMark } from "../ui/indicators";
import { Button, ExternalLink, Pill } from "../ui/primitives";
import { ProxiedAvatar } from "../ui/ProxiedAvatar";

export function ProfileCard({ profile }: { profile: Entity }) {
  const { open } = useEvidence();
  const platform = profile.data.platform;
  const match = profile.match;
  const conflicting = match?.factors.some((f) => f.weight < 0);
  const stats = (profile.data.stats ?? {}) as Record<string, number | string | null>;
  return (
    <article className="flex flex-col rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong">
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <PlatformMark platform={platform} size={22} />
          <span className="text-[13px] font-medium text-fg">{platform ? (PLATFORM_META[platform]?.label ?? platform) : "Profile"}</span>
        </div>
        {conflicting && <Pill color="var(--st-error)">Conflicts</Pill>}
      </header>

      <div className="mt-4 flex items-center gap-3">
        <ProxiedAvatar observationId={profile.avatar_observation_id} label={profile.label} size={44} />
        <div className="min-w-0">
          <div className="truncate font-mono text-[13px] text-fg">{profile.label}</div>
          <div className="text-xs text-muted">Public profile</div>
        </div>
      </div>

      {Object.keys(stats).length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
          {Object.entries(stats)
            .filter(([, v]) => v !== null && v !== undefined)
            .slice(0, 3)
            .map(([k, v]) => (
              <div key={k} className="flex gap-1">
                <dt className="text-subtle">{k.replace(/([A-Z])/g, " $1").replace(/_/g, " ").toLowerCase()}</dt>
                <dd className="font-mono text-muted tabular-nums">{String(v)}</dd>
              </div>
            ))}
        </dl>
      )}

      <div className="mt-4 space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted">{match?.label ?? "Unscored"}</span>
          <ConfidenceBadge score={match?.score} level={match?.level} />
        </div>
        {match && <ConfidenceBar score={match.score} />}
      </div>

      <footer className="mt-4 flex gap-2">
        <ExternalLink
          href={profile.data.url}
          className="inline-flex h-7 items-center rounded-md border border-line-strong bg-surface-2 px-2.5 text-xs font-medium text-fg hover:bg-surface-3"
        >
          View profile
        </ExternalLink>
        <Button size="sm" variant="ghost" onClick={() => open({ type: "entity", id: profile.id })}>
          Evidence
        </Button>
      </footer>
    </article>
  );
}

export function ProfileGrid({ profiles }: { profiles: Entity[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {profiles.map((p) => (
        <ProfileCard key={p.id} profile={p} />
      ))}
    </div>
  );
}
