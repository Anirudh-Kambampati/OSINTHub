import clsx from "clsx";
import { ExternalLink as ExternalIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { safeHref } from "../../lib/format";

export function Card({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("rounded-lg border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="label-caps">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  icon?: ReactNode;
};

export function Button({ variant = "secondary", size = "md", icon, className, children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={clsx(
        "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
        variant === "primary" && "bg-accent text-[var(--on-accent)] hover:brightness-110",
        variant === "secondary" && "border border-line-strong bg-surface-2 text-fg hover:bg-surface-3",
        variant === "ghost" && "text-muted hover:bg-surface-2 hover:text-fg",
        variant === "danger" && "border border-line-strong bg-surface-2 text-[var(--st-error)] hover:bg-surface-3",
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}

export function Dot({ color, pulse }: { color: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex size-2 shrink-0">
      {pulse && (
        <span className="absolute inline-flex size-full animate-ping rounded-full opacity-60" style={{ background: color }} />
      )}
      <span className="relative inline-flex size-2 rounded-full" style={{ background: color }} />
    </span>
  );
}

export function Pill({ children, color, className }: { children: ReactNode; color?: string; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded border px-1.5 py-px text-[11px] font-medium whitespace-nowrap",
        className,
      )}
      style={{
        color: color ?? "var(--text-muted)",
        borderColor: color ? `color-mix(in srgb, ${color} 35%, transparent)` : "var(--border-strong)",
        background: color ? `color-mix(in srgb, ${color} 10%, transparent)` : "transparent",
      }}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function ExternalLink({
  href,
  children,
  className,
  icon = true,
}: {
  href: string | null | undefined;
  children: ReactNode;
  className?: string;
  icon?: boolean;
}) {
  const safe = safeHref(href);
  if (!safe) return <span className={className}>{children}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      referrerPolicy="no-referrer"
      className={clsx("inline-flex items-center gap-1 hover:text-accent", className)}
    >
      {children}
      {icon && <ExternalIcon className="size-3 shrink-0 opacity-60" aria-hidden />}
    </a>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon && <div className="mb-3 text-subtle">{icon}</div>}
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-[13px] text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  counts,
  label,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  counts?: Record<string, number>;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          onClick={() => onChange(o.key)}
          className={clsx(
            "h-7 rounded-md px-2.5 text-xs font-medium transition-colors",
            value === o.key ? "bg-surface-3 text-fg ring-1 ring-line-strong" : "text-muted hover:bg-surface-2 hover:text-fg",
          )}
        >
          {o.label}
          {counts && o.key in counts && <span className="ml-1.5 text-subtle tabular-nums">{counts[o.key]}</span>}
        </button>
      ))}
    </div>
  );
}

export function ErrorNotice({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div
      role="alert"
      className="rounded-md border px-3 py-2 text-[13px]"
      style={{
        color: "var(--st-error)",
        borderColor: "color-mix(in srgb, var(--st-error) 35%, transparent)",
        background: "color-mix(in srgb, var(--st-error) 8%, transparent)",
      }}
    >
      {message}
    </div>
  );
}
