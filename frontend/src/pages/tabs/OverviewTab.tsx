import { CircleAlert, SearchX } from "lucide-react";
import { Link } from "react-router";
import { IdentityCard } from "../../components/investigation/IdentityCard";
import { InvestigationStats } from "../../components/investigation/InvestigationStats";
import { MentionCard } from "../../components/investigation/MentionCard";
import { PlatformPresence } from "../../components/investigation/PlatformPresence";
import { ProfileGrid } from "../../components/investigation/ProfileCard";
import { RunProgress } from "../../components/investigation/RunProgress";
import { Card, Skeleton } from "../../components/ui/primitives";
import { useMentions } from "../../hooks/queries";
import { useInvestigationContext } from "../InvestigationLayout";

const DEGRADED = new Set(["error", "rate_limited"]);

function summarize(labels: string[]): string {
  const counts = new Map<string, number>();
  labels.forEach((l) => counts.set(l, (counts.get(l) ?? 0) + 1));
  return [...counts].map(([l, n]) => (n > 1 ? `${l} (×${n})` : l)).join(", ");
}

export function NoResults({ searched }: { searched: number }) {
  return (
    <Card>
      <div className="flex flex-col items-center px-6 py-10 text-center">
        <SearchX className="mb-3 size-8 text-subtle" aria-hidden />
        <h3 className="text-sm font-semibold text-fg">No verified public presence found.</h3>
        <dl className="mt-4 grid grid-cols-[auto_auto] gap-x-6 gap-y-1 text-left text-[13px]">
          <dt className="text-muted">We searched</dt>
          <dd className="text-fg">{searched} sources</dd>
          <dt className="text-muted">Results</dt>
          <dd className="text-fg">0 verified profiles · 0 mentions</dd>
        </dl>
        <p className="mt-4 max-w-md text-[13px] text-muted">
          This does <strong className="text-fg">not</strong> mean the identity has no online presence. Some sources may be
          unavailable or require authentication.
        </p>
      </div>
    </Card>
  );
}

export function OverviewTab() {
  const { inv, profile, profileLoading, active } = useInvestigationContext();
  const mentions = useMentions(inv.id, { sort: "confidence", limit: 5 }, active);
  const degraded = inv.runs.filter((r) => DEGRADED.has(r.status));
  const hasData = !!profile && (profile.profiles.length > 0 || profile.attributes.length > 0 || inv.stats.mentions > 0);

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-5 p-6">
      {active && (
        <Card title="Investigation running">
          <RunProgress runs={inv.runs} />
        </Card>
      )}
      {!active && degraded.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border px-4 py-3 text-[13px]" role="status"
          style={{ borderColor: "color-mix(in srgb, var(--st-not-verified) 35%, transparent)", background: "color-mix(in srgb, var(--st-not-verified) 7%, transparent)" }}>
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-[var(--st-not-verified)]" aria-hidden />
          <div>
            <span className="font-medium text-fg">Investigation completed with partial results.</span>{" "}
            <span className="text-muted">
              {degraded.length} source check{degraded.length > 1 ? "s" : ""} failed or were rate limited:{" "}
              {summarize(degraded.map((r) => r.label))}.
            </span>{" "}
            <Link to="sources" className="text-accent hover:underline">Details</Link>
          </div>
        </div>
      )}

      <InvestigationStats stats={inv.stats} />

      {profileLoading || !profile ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      ) : !active && !hasData ? (
        <NoResults searched={inv.runs.length} />
      ) : (
        <>
          {profile.presence.length > 0 ? (
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <IdentityCard attributes={profile.attributes} />
              <PlatformPresence presence={profile.presence} />
            </div>
          ) : (
            <IdentityCard attributes={profile.attributes} />
          )}
          {profile.profiles.length > 0 && (
            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="label-caps">Discovered profiles</h2>
                {profile.profiles.length > 6 && (
                  <Link to="profiles" className="text-xs text-accent hover:underline">
                    All {profile.profiles.length} profiles
                  </Link>
                )}
              </div>
              <ProfileGrid profiles={profile.profiles.slice(0, 6)} />
            </section>
          )}
          {(mentions.data?.items.length ?? 0) > 0 && (
            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="label-caps">Highest-confidence mentions</h2>
                <Link to="mentions" className="text-xs text-accent hover:underline">
                  All {mentions.data!.total} mentions
                </Link>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {mentions.data!.items.map((m) => (
                  <MentionCard key={m.id} mention={m} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
