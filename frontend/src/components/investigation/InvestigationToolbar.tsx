import { BellRing, Download, Plus, Tag, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useUpdateInvestigation } from "../../hooks/queries";
import { exportUrls, type CsvDataset } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { MONITOR_OPTIONS } from "../../lib/meta";
import type { InvestigationDetail } from "../../lib/types";
import { Pill } from "../ui/primitives";

const CSV_DATASETS: { key: CsvDataset; label: string }[] = [
  { key: "attributes", label: "Identity attributes" },
  { key: "profiles", label: "Profiles & match evidence" },
  { key: "mentions", label: "Mentions" },
  { key: "observations", label: "All observations" },
  { key: "timeline", label: "Timeline" },
  { key: "sources", label: "Source checks" },
];

function TagEditor({ inv }: { inv: InvestigationDetail }) {
  const update = useUpdateInvestigation(inv.id);
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const save = (tags: string[]) => update.mutate({ tags });
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && draft.trim()) {
      e.preventDefault();
      save([...inv.tags, draft.trim()]);
      setDraft("");
      setAdding(false);
    } else if (e.key === "Escape") {
      setAdding(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Tag className="size-3.5 text-subtle" aria-hidden />
      {inv.tags.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded border border-line-strong px-1.5 py-px text-[11px] text-muted">
          {t}
          <button type="button" aria-label={`Remove tag ${t}`} onClick={() => save(inv.tags.filter((x) => x !== t))}
            className="text-subtle hover:text-fg">
            <X className="size-3" />
          </button>
        </span>
      ))}
      {adding ? (
        <input
          autoFocus
          value={draft}
          maxLength={32}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => setAdding(false)}
          placeholder="tag, Enter"
          aria-label="New tag"
          className="h-6 w-24 rounded border border-line-strong bg-surface-2 px-1.5 text-[11px] text-fg outline-none"
        />
      ) : (
        <button type="button" onClick={() => setAdding(true)}
          className="inline-flex items-center gap-0.5 rounded px-1 text-[11px] text-subtle hover:text-fg">
          <Plus className="size-3" /> Tag
        </button>
      )}
      {update.error && <span className="text-[11px] text-[var(--st-error)]">{update.error.message}</span>}
    </div>
  );
}

function MonitorSelect({ inv }: { inv: InvestigationDetail }) {
  const update = useUpdateInvestigation(inv.id);
  return (
    <label className="inline-flex items-center gap-1.5 text-[11px] text-subtle" title={inv.next_run_at ? `Next run ${formatDateTime(inv.next_run_at)}` : undefined}>
      <BellRing className="size-3.5" aria-hidden />
      Monitor
      <select
        value={inv.monitor_interval_hours ?? ""}
        onChange={(e) => update.mutate({ monitor_interval_hours: e.target.value ? Number(e.target.value) : null })}
        className="rounded border border-line-strong bg-surface-2 px-1 py-0.5 text-[11px] text-fg"
      >
        {MONITOR_OPTIONS.map((o) => (
          <option key={o.label} value={o.hours ?? ""}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

function ExportMenu({ inv }: { inv: InvestigationDetail }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const urls = exportUrls(inv.id);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: globalThis.KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const item = "block rounded px-2.5 py-1.5 text-xs text-fg hover:bg-surface-3";
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-surface-2 px-3 text-[13px] font-medium text-fg hover:bg-surface-3"
      >
        <Download className="size-3.5" /> Export
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-60 rounded-lg border border-line-strong bg-surface p-1 shadow-2xl">
          <a role="menuitem" className={item} href={urls.report} target="_blank" rel="noopener">Printable report (HTML / PDF)</a>
          <a role="menuitem" className={item} href={urls.json} download>Full dataset (JSON)</a>
          <div className="label-caps px-2.5 pt-2 pb-1">CSV</div>
          {CSV_DATASETS.map((d) => (
            <a key={d.key} role="menuitem" className={item} href={urls.csv(d.key)} download>{d.label}</a>
          ))}
        </div>
      )}
    </div>
  );
}

export function InvestigationToolbar({ inv }: { inv: InvestigationDetail }) {
  const fresh = inv.stats.new_entities + inv.stats.new_mentions;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <TagEditor inv={inv} />
      <MonitorSelect inv={inv} />
      {inv.previous_completed_at && (
        <Pill color={fresh ? "var(--accent)" : undefined}>
          {fresh ? `${inv.stats.new_entities} new entities · ${inv.stats.new_mentions} new mentions since last run` : "No changes since last run"}
        </Pill>
      )}
      {inv.owner_name && <span className="text-[11px] text-subtle">Owner: {inv.owner_name}</span>}
    </div>
  );
}

export { ExportMenu };
