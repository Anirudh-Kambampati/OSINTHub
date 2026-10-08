import clsx from "clsx";
import { formatConfidence } from "../../lib/format";
import { CONFIDENCE_META, INVESTIGATION_STATUS_META, PLATFORM_META, RUN_STATUS_META, levelOf } from "../../lib/meta";
import type { ConfidenceLevel, InvestigationStatus, RunStatus } from "../../lib/types";
import { Dot, Pill } from "./primitives";

export function ConfidenceBadge({
  score,
  level,
  showPercent = true,
  size = "sm",
}: {
  score: number | null | undefined;
  level?: ConfidenceLevel | null;
  showPercent?: boolean;
  size?: "sm" | "lg";
}) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-subtle">Unscored</span>;
  }
  const meta = CONFIDENCE_META[level ?? levelOf(score)];
  return (
    <span
      className={clsx("inline-flex items-center gap-1.5 font-medium whitespace-nowrap", size === "lg" ? "text-sm" : "text-xs")}
      style={{ color: meta.color }}
      title={`${meta.label} confidence (${Math.round(score * 100)}%)`}
    >
      <Dot color={meta.color} />
      <span className={clsx("uppercase tracking-wide", size === "lg" ? "text-[12px]" : "text-[10.5px]")}>{meta.label}</span>
      {showPercent && <span className="font-mono tabular-nums text-muted">{formatConfidence(score)}</span>}
    </span>
  );
}

export function ConfidenceBar({ score, className }: { score: number; className?: string }) {
  const meta = CONFIDENCE_META[levelOf(score)];
  return (
    <div className={clsx("h-1 w-full overflow-hidden rounded-full bg-surface-3", className)} aria-hidden>
      <div className="h-full rounded-full" style={{ width: `${Math.max(3, score * 100)}%`, background: meta.color }} />
    </div>
  );
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const meta = RUN_STATUS_META[status];
  return (
    <Pill color={meta.color}>
      <Dot color={meta.color} pulse={status === "running"} />
      {meta.label}
    </Pill>
  );
}

export function InvestigationStatusBadge({ status }: { status: InvestigationStatus }) {
  const meta = INVESTIGATION_STATUS_META[status];
  return (
    <Pill color={meta.color}>
      <Dot color={meta.color} pulse={status === "running" || status === "pending"} />
      {meta.label}
    </Pill>
  );
}

export function PlatformMark({ platform, size = 28 }: { platform: string | null | undefined; size?: number }) {
  const meta = (platform && PLATFORM_META[platform]) || { label: platform ?? "?", mono: (platform ?? "?").slice(0, 2).toUpperCase(), hue: 215 };
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-md font-mono font-semibold"
      style={{
        width: size,
        height: size,
        fontSize: Math.max(9, size * 0.36),
        color: `hsl(${meta.hue} 70% 72%)`,
        background: `hsl(${meta.hue} 30% 16%)`,
        border: `1px solid hsl(${meta.hue} 30% 24%)`,
      }}
    >
      {meta.mono}
    </span>
  );
}
