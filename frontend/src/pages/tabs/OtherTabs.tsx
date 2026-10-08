import { History, Newspaper, Users } from "lucide-react";
import { useState } from "react";
import { MentionCard } from "../../components/investigation/MentionCard";
import { ProfileGrid } from "../../components/investigation/ProfileCard";
import { Timeline } from "../../components/investigation/Timeline";
import { Button, EmptyState, ErrorNotice, SegmentedControl, Skeleton } from "../../components/ui/primitives";
import { useMentions, useTimeline } from "../../hooks/queries";
import { MENTION_CATEGORIES, TIMELINE_KINDS } from "../../lib/meta";
import type { Entity } from "../../lib/types";
import { useInvestigationContext } from "../InvestigationLayout";

function Page({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[1400px] space-y-4 p-6">{children}</div>;
}

const PROFILE_VIEWS = [
  { key: "clusters", label: "Identity clusters" },
  { key: "all", label: "All profiles" },
  { key: "conflicting", label: "Conflicting" },
] as const;

/** Profiles tied together by strong evidence (cross-links, shared email/website) form a cluster.
 * Cluster 0 holds the best-matching profile; other multi-profile clusters are separate identities. */
function groupByCluster(profiles: Entity[]) {
  const byCluster = new Map<number, Entity[]>();
  const rejected: Entity[] = [];
  for (const p of profiles) {
    if (p.match?.decision === "rejected" || p.match?.cluster === null || p.match?.cluster === undefined) rejected.push(p);
    else byCluster.set(p.match.cluster, [...(byCluster.get(p.match.cluster) ?? []), p]);
  }
  const groups: { title: string; description: string; profiles: Entity[] }[] = [];
  const unlinked: Entity[] = [];
  let other = 0;
  for (const [cluster, members] of [...byCluster.entries()].sort((a, b) => a[0] - b[0])) {
    if (cluster === 0) {
      groups.push({ title: "Primary identity", description: "The best-matching profile and every profile strongly linked to it.", profiles: members });
    } else if (members.length > 1) {
      other += 1;
      groups.push({
        title: `Separate identity ${String.fromCharCode(65 + other)}`,
        description: "These profiles are strongly linked to each other but not to the primary identity — likely a different entity using a similar handle.",
        profiles: members,
      });
    } else unlinked.push(...members);
  }
  if (unlinked.length) groups.push({ title: "Unlinked profiles", description: "No strong evidence ties these to any other profile.", profiles: unlinked });
  if (rejected.length) groups.push({ title: "Rejected by analyst", description: "Marked as a different entity.", profiles: rejected });
  return groups;
}

export function ProfilesTab() {
  const { profile, profileLoading, active } = useInvestigationContext();
  const [view, setView] = useState<(typeof PROFILE_VIEWS)[number]["key"]>("clusters");
  if (profileLoading || !profile) return <Page><Skeleton className="h-64" /></Page>;
  const all = profile.profiles;
  return (
    <Page>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">{all.length} discovered profiles</h2>
          <p className="text-xs text-muted">
            Each profile is a separate entity. Matching usernames alone are never treated as the same person — confirm or
            reject profiles to correct the analysis.
          </p>
        </div>
        <SegmentedControl label="Profile view" options={[...PROFILE_VIEWS]} value={view} onChange={setView} />
      </div>
      {all.length === 0 ? (
        <EmptyState icon={<Users className="size-8" />} title={active ? "Searching sources…" : "No profiles discovered"} />
      ) : view === "clusters" ? (
        groupByCluster(all).map((g) => (
          <section key={g.title} className="space-y-3">
            <div>
              <h3 className="label-caps">{g.title} · {g.profiles.length}</h3>
              <p className="text-xs text-subtle">{g.description}</p>
            </div>
            <ProfileGrid profiles={g.profiles} />
          </section>
        ))
      ) : (
        <ProfileGrid profiles={view === "conflicting" ? all.filter((p) => p.match?.factors.some((f) => f.weight < 0)) : all} />
      )}
    </Page>
  );
}

const SORTS = [
  { key: "newest", label: "Newest" },
  { key: "oldest", label: "Oldest" },
  { key: "confidence", label: "Confidence" },
  { key: "source", label: "Source" },
] as const;
const PAGE = 30;

export function MentionsTab() {
  const { inv, active } = useInvestigationContext();
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<(typeof SORTS)[number]["key"]>("newest");
  const [limit, setLimit] = useState(PAGE);
  const { data, isLoading, error, isFetching } = useMentions(inv.id, { category, sort, limit }, active);
  const counts = data ? { "": Object.values(data.counts).reduce((a, b) => a + b, 0), ...data.counts } : undefined;

  return (
    <Page>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">Mentions</h2>
          <p className="text-xs text-muted">{data ? `${data.total} results` : "Loading…"}</p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl label="Mention category" options={MENTION_CATEGORIES} value={category} counts={counts}
            onChange={(c) => { setCategory(c); setLimit(PAGE); }} />
          <SegmentedControl label="Sort mentions" options={[...SORTS]} value={sort} onChange={setSort} />
        </div>
      </div>
      {error ? <ErrorNotice error={error} /> : isLoading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}</div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState icon={<Newspaper className="size-8" />} title={active ? "Collecting mentions…" : "No mentions found"}>
          Mentions come from sources that publish public activity or search results.
        </EmptyState>
      ) : (
        <>
          <div className="space-y-3">{data.items.map((m) => <MentionCard key={m.id} mention={m} />)}</div>
          {data.items.length < data.total && (
            <div className="flex justify-center">
              <Button onClick={() => setLimit((l) => l + PAGE)} disabled={isFetching}>
                {isFetching ? "Loading…" : `Show more (${data.total - data.items.length} remaining)`}
              </Button>
            </div>
          )}
        </>
      )}
    </Page>
  );
}

export function TimelineTab() {
  const { inv, active } = useInvestigationContext();
  const [kind, setKind] = useState("");
  const { data, isLoading, error } = useTimeline(inv.id, kind, active);
  return (
    <Page>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">Timeline</h2>
          <p className="text-xs text-muted">Every event is derived from a dated public record and links to its source.</p>
        </div>
        <SegmentedControl label="Event type" options={TIMELINE_KINDS} value={kind} onChange={setKind} />
      </div>
      {error ? <ErrorNotice error={error} /> : isLoading ? <Skeleton className="h-64" /> : !data?.length ? (
        <EmptyState icon={<History className="size-8" />} title="No dated events">
          Events appear when sources report creation, publication or registration dates.
        </EmptyState>
      ) : (
        <div className="rounded-lg border border-line bg-surface p-6">
          <Timeline events={data} />
        </div>
      )}
    </Page>
  );
}
