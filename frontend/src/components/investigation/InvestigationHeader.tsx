import clsx from "clsx";
import { RefreshCw, Trash2 } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import { useEvidence } from "../../context/evidence";
import { isActive, useDeleteInvestigation, useRerun } from "../../hooks/queries";
import { formatDate } from "../../lib/format";
import { SEED_TYPE_LABEL, attributeLabel } from "../../lib/meta";
import type { InvestigationDetail, ProfileView } from "../../lib/types";
import { ConfidenceBadge, InvestigationStatusBadge } from "../ui/indicators";
import { Button, Skeleton } from "../ui/primitives";
import { ProxiedAvatar } from "../ui/ProxiedAvatar";
import { ExportMenu, InvestigationToolbar } from "./InvestigationToolbar";

const SUBJECT_DESCRIPTION: Record<string, string> = {
  username: "Public identity profile",
  email: "Public identity profile",
  person: "Public identity profile",
  domain: "Domain intelligence profile",
  url: "Web resource profile",
};

const HEADLINE_ATTRIBUTES = ["email", "website", "organization", "location", "registrar"];
const HEADLINE_MIN_CONFIDENCE = 0.6;

const TABS = [
  { to: "", label: "Overview", end: true },
  { to: "profiles", label: "Profiles" },
  { to: "mentions", label: "Mentions" },
  { to: "timeline", label: "Timeline" },
  { to: "graph", label: "Graph" },
  { to: "sources", label: "Sources" },
];

export function InvestigationHeader({ inv, profile }: { inv: InvestigationDetail; profile: ProfileView | undefined }) {
  const { open } = useEvidence();
  const navigate = useNavigate();
  const rerun = useRerun(inv.id);
  const del = useDeleteInvestigation();
  const running = isActive(inv.status);
  const image = profile?.images[0];
  const headline = HEADLINE_ATTRIBUTES.map((a) => profile?.attributes.find((x) => x.attribute === a)).filter(
    // Only well-corroborated values headline the subject; weaker ones stay in the identity card.
    (a): a is NonNullable<typeof a> => !!a && a.confidence >= HEADLINE_MIN_CONFIDENCE,
  );
  const subject = profile?.subject.label ?? inv.title;
  const handle = inv.seed_type === "username" ? `@${inv.seed.replace(/^@/, "")}` : inv.seed;

  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto max-w-[1400px] px-6 pt-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
          <div className="flex flex-col items-center gap-1.5">
            <ProxiedAvatar observationId={image?.observation_id} label={subject} size={88} rounded="md" />
            {profile && profile.images.length > 0 && (
              <button
                type="button"
                onClick={() => open({ type: "images", images: profile.images, label: subject })}
                className="text-[11px] text-subtle hover:text-accent"
              >
                {profile.images.length} image source{profile.images.length > 1 ? "s" : ""}
              </button>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="label-caps">{SUBJECT_DESCRIPTION[inv.seed_type]}</span>
              <InvestigationStatusBadge status={inv.status} />
            </div>
            <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight text-fg">{subject}</h1>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
              <span className="font-mono">{handle}</span>
              <span className="text-subtle">·</span>
              <span>Seed type: {SEED_TYPE_LABEL[inv.seed_type]}</span>
              <span className="text-subtle">·</span>
              <span>Created {formatDate(inv.created_at)}</span>
            </div>
            <div className="mt-2.5">
              {profile ? (
                <ConfidenceBadge score={profile.confidence} level={profile.level} size="lg" />
              ) : (
                <Skeleton className="h-5 w-40" />
              )}
            </div>
            {headline.length > 0 && (
              <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 text-[13px]">
                {headline.map((a) => (
                  <div key={a.attribute} className="flex items-baseline gap-1.5">
                    <dt className="text-subtle">{attributeLabel(a.attribute)}:</dt>
                    <dd>
                      <button
                        type="button"
                        onClick={() => open({ type: "attribute", attribute: a })}
                        className="text-fg underline decoration-line-strong decoration-dotted underline-offset-4 hover:text-accent"
                        title="Show evidence"
                      >
                        {a.value}
                      </button>
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {inv.error && <p className="mt-2 text-xs text-[var(--st-not-verified)]">{inv.error}</p>}
            <InvestigationToolbar inv={inv} />
          </div>

          <div className="flex shrink-0 gap-2">
            <ExportMenu inv={inv} />
            <Button
              icon={<RefreshCw className={clsx("size-3.5", running && "animate-spin")} />}
              onClick={() => rerun.mutate()}
              disabled={running || rerun.isPending}
              title="Query all sources again; new observations are added alongside existing ones"
            >
              {running ? "Running" : "Re-run"}
            </Button>
            <Button
              variant="danger"
              icon={<Trash2 className="size-3.5" />}
              disabled={running || del.isPending}
              aria-label="Delete investigation"
              onClick={() => {
                if (window.confirm(`Delete the investigation "${inv.title}" and all its collected data?`)) {
                  del.mutate(inv.id, { onSuccess: () => navigate("/investigations") });
                }
              }}
            />
          </div>
        </div>

        <nav className="-mb-px mt-5 flex gap-1 overflow-x-auto" aria-label="Investigation sections">
          {TABS.map((t) => (
            <NavLink
              key={t.label}
              to={t.to}
              end={t.end}
              className={({ isActive: active }) =>
                clsx(
                  "border-b-2 px-3 pb-2.5 text-[13px] font-medium whitespace-nowrap transition-colors",
                  active ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg",
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
