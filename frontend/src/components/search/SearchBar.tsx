import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, LoaderCircle, Search } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useCreateInvestigation } from "../../hooks/queries";
import { api } from "../../lib/api";
import { SEED_TYPE_LABEL } from "../../lib/meta";
import type { SeedType } from "../../lib/types";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function SearchBar({ autoFocus, size = "md" }: { autoFocus?: boolean; size?: "md" | "lg" }) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [override, setOverride] = useState<SeedType | null>(null);
  const navigate = useNavigate();
  const create = useCreateInvestigation();
  const panelId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const debounced = useDebounced(value.trim(), 180);

  const { data: classification, isFetching } = useQuery({
    queryKey: ["classify", debounced],
    queryFn: () => api.classify(debounced),
    enabled: debounced.length >= 2,
    staleTime: Infinity,
  });
  const current = debounced === value.trim() ? classification : undefined;
  const type = override ?? current?.type ?? null;

  useEffect(() => setOverride(null), [debounced]);

  // "/" focuses search from anywhere, like most consoles.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(target.tagName)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!current?.valid || create.isPending) return;
    create.mutate(
      { seed: value.trim(), seedType: override ?? undefined },
      {
        onSuccess: (inv) => {
          setValue("");
          inputRef.current?.blur();
          navigate(`/investigations/${inv.id}`);
        },
      },
    );
  };

  const showPanel = focused && value.trim().length >= 2;
  return (
    <form onSubmit={submit} className="relative w-full" role="search">
      <div
        className={clsx(
          "flex items-center gap-2 rounded-lg border bg-surface-2 transition-colors",
          focused ? "border-accent/60" : "border-line-strong",
          size === "lg" ? "h-12 px-4" : "h-9 px-3",
        )}
      >
        <Search className={clsx("shrink-0 text-subtle", size === "lg" ? "size-5" : "size-4")} aria-hidden />
        <input
          ref={inputRef}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          maxLength={256}
          spellCheck={false}
          autoComplete="off"
          placeholder="Search name, username, email, domain or URL…"
          aria-label="Investigation search"
          aria-controls={panelId}
          aria-expanded={showPanel}
          className={clsx("min-w-0 flex-1 bg-transparent text-fg outline-none focus-visible:outline-none placeholder:text-subtle", size === "lg" && "text-[15px]")}
        />
        {type && current?.valid && (
          <span className="hidden rounded border border-line-strong px-1.5 py-px font-mono text-[10.5px] uppercase tracking-wider text-muted sm:inline">
            {type}
          </span>
        )}
        {!focused && !value && (
          <kbd className="hidden rounded border border-line px-1.5 font-mono text-[10.5px] text-subtle sm:inline">/</kbd>
        )}
      </div>

      {showPanel && (
        <div id={panelId} className="absolute top-full right-0 left-0 z-40 mt-1.5 rounded-lg border border-line-strong bg-surface p-3 shadow-2xl">
          {!current ? (
            <div className="flex items-center gap-2 text-xs text-muted">
              <LoaderCircle className="size-3.5 animate-spin" /> Classifying input…
            </div>
          ) : !current.valid ? (
            <div className="text-xs text-[var(--st-error)]">{current.error}</div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="label-caps">Detected type</div>
                  <div className="mt-0.5 font-mono text-[13px] font-semibold tracking-wide text-fg uppercase">
                    {type && SEED_TYPE_LABEL[type]}
                  </div>
                </div>
                <div className="truncate text-right font-mono text-xs text-muted">{current.normalized}</div>
              </div>
              {current.alternatives.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  Treat as:
                  {[current.type!, ...current.alternatives].map((t) => (
                    <button
                      key={t}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => setOverride(t === current.type ? null : t)}
                      className={clsx(
                        "rounded border px-1.5 py-px",
                        type === t ? "border-accent/60 text-fg" : "border-line-strong hover:text-fg",
                      )}
                    >
                      {SEED_TYPE_LABEL[t]}
                    </button>
                  ))}
                </div>
              )}
              {create.error && <div className="text-xs text-[var(--st-error)]">{create.error.message}</div>}
              <button
                type="submit"
                onMouseDown={(e) => e.preventDefault()}
                disabled={create.isPending || isFetching}
                className="flex w-full items-center justify-between rounded-md bg-accent px-3 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:brightness-110 disabled:opacity-60"
              >
                {create.isPending ? "Starting investigation…" : "Search public sources"}
                <ArrowRight className="size-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </form>
  );
}
