import { Radar } from "lucide-react";
import { SearchBar } from "../components/search/SearchBar";
import { ErrorNotice, Skeleton } from "../components/ui/primitives";
import { useInvestigations } from "../hooks/queries";
import { InvestigationTable } from "./InvestigationsPage";

const EXAMPLES = [
  ["anirudh123", "username"],
  ["jane@example.com", "email"],
  ["Jane Doe", "name"],
  ["example.com", "domain"],
];

export function StartInvestigation() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-6 pt-20 pb-10 text-center">
      <div className="mb-5 flex size-12 items-center justify-center rounded-xl border border-line-strong bg-surface-2">
        <Radar className="size-6 text-accent" aria-hidden />
      </div>
      <h1 className="text-xl font-semibold tracking-tight text-fg">Start an Investigation</h1>
      <p className="mt-1.5 text-[13px] text-muted">Search a username, email, name, domain, or URL.</p>
      <div className="mt-6 w-full">
        <SearchBar size="lg" autoFocus />
      </div>
      <div className="mt-4 flex flex-wrap justify-center gap-x-5 gap-y-1 text-xs text-subtle">
        {EXAMPLES.map(([v, t]) => (
          <span key={v}>
            <span className="font-mono text-muted">{v}</span> → {t}
          </span>
        ))}
      </div>
      <p className="mt-10 max-w-lg text-[11.5px] leading-relaxed text-subtle">
        Only legitimately accessible public sources are queried. Sources that require authentication or forbid automated
        access are reported as not verified rather than bypassed.
      </p>
    </div>
  );
}

export function HomePage() {
  const { data, isLoading, error } = useInvestigations();
  return (
    <div>
      <StartInvestigation />
      <div className="mx-auto max-w-[1100px] px-6 pb-10">
        {error ? <ErrorNotice error={error} /> : isLoading ? <Skeleton className="h-40" /> : data && data.length > 0 && (
          <section>
            <h2 className="label-caps mb-3">Recent investigations</h2>
            <InvestigationTable investigations={data.slice(0, 8)} />
          </section>
        )}
      </div>
    </div>
  );
}
