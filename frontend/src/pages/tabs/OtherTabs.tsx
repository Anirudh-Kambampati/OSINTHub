import { History, Newspaper, Users } from "lucide-react";
import { useState } from "react";
import { MentionCard } from "../../components/investigation/MentionCard";
import { ProfileGrid } from "../../components/investigation/ProfileCard";
import { Timeline } from "../../components/investigation/Timeline";
import { Button, EmptyState, ErrorNotice, SegmentedControl, Skeleton } from "../../components/ui/primitives";
import { useMentions, useTimeline } from "../../hooks/queries";
import { MENTION_CATEGORIES, TIMELINE_KINDS } from "../../lib/meta";
import { useInvestigationContext } from "../InvestigationLayout";

function Page({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[1400px] space-y-4 p-6">{children}</div>;
}

const PROFILE_FILTERS = [
  { key: "all", label: "All" },
  { key: "matched", label: "Possible match or better" },
  { key: "conflicting", label: "Conflicting" },
] as const;

export function ProfilesTab() {
  const { profile, profileLoading, active } = useInvestigationContext();
  const [filter, setFilter] = useState<(typeof PROFILE_FILTERS)[number]["key"]>("all");
  if (profileLoading || !profile) return <Page><Skeleton className="h-64" /></Page>;
  const profiles = profile.profiles.filter((p) =>
    filter === "matched" ? (p.match?.score ?? 0) >= 0.3
    : filter === "conflicting" ? p.match?.factors.some((f) => f.weight < 0)
    : true,
  );
  return (
    <Page>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">{profile.profiles.length} discovered profiles</h2>
          <p className="text-xs text-muted">
            Each profile is a separate entity. Matching usernames alone are never treated as the same person.
          </p>
        </div>
        <SegmentedControl label="Filter profiles" options={[...PROFILE_FILTERS]} value={filter} onChange={setFilter} />
      </div>
      {profiles.length === 0 ? (
        <EmptyState icon={<Users className="size-8" />} title={active ? "Searching sources…" : "No profiles in this view"} />
      ) : (
        <ProfileGrid profiles={profiles} />
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
