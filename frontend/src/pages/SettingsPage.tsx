import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PlatformMark } from "../components/ui/indicators";
import { Button, Card, ErrorNotice, Pill, Skeleton } from "../components/ui/primitives";
import { useConnectors } from "../hooks/queries";
import { getApiToken, setApiToken } from "../lib/api";
import { SEED_TYPE_LABEL } from "../lib/meta";

function TokenForm() {
  const qc = useQueryClient();
  const [value, setValue] = useState(getApiToken() ?? "");
  const [saved, setSaved] = useState(false);
  return (
    <Card title="API access">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setApiToken(value.trim() || null);
          setSaved(true);
          qc.invalidateQueries();
        }}
      >
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs text-muted">
          Console token (only needed when the server sets OSINT_API_TOKEN; kept for this browser session only)
          <input
            type="password"
            value={value}
            onChange={(e) => { setValue(e.target.value); setSaved(false); }}
            autoComplete="off"
            className="h-8 rounded-md border border-line-strong bg-surface-2 px-2.5 text-[13px] text-fg outline-none focus:border-accent/60"
          />
        </label>
        <Button type="submit" variant="primary">Save</Button>
        {saved && <span className="text-xs text-[var(--st-found)]">Saved</span>}
      </form>
    </Card>
  );
}

export function SettingsPage() {
  const { data, isLoading, error } = useConnectors();
  return (
    <div className="mx-auto max-w-[1100px] space-y-5 p-6">
      <div>
        <h1 className="text-base font-semibold text-fg">Settings</h1>
        <p className="text-xs text-muted">
          Source credentials are configured server-side through environment variables and are never sent to the browser.
        </p>
      </div>
      <TokenForm />
      <Card title="Source connectors" bodyClassName="p-0">
        {error ? <div className="p-4"><ErrorNotice error={error} /></div> : isLoading || !data ? <Skeleton className="m-4 h-40" /> : (
          <ul className="divide-y divide-line">
            {data.map((c) => (
              <li key={c.name} className="flex flex-wrap items-start gap-3 px-4 py-3">
                <PlatformMark platform={c.name} size={26} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-medium text-fg">{c.label}</span>
                    <Pill>{c.category}</Pill>
                    <Pill>{c.reliability} reliability</Pill>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">{c.description}</p>
                  <p className="mt-1 text-[11px] text-subtle">
                    Inputs: {c.supports.map((s) => SEED_TYPE_LABEL[s]).join(", ")}
                    {c.accepts_pivots.length > 0 && ` · follows discovered ${c.accepts_pivots.join(", ")}s`}
                  </p>
                </div>
                {c.configured ? (
                  <Pill color="var(--st-found)">Active</Pill>
                ) : (
                  <Pill color="var(--st-auth)" className="font-mono">Needs {c.requires.join(", ")}</Pill>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
