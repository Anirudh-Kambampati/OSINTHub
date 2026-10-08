import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { PlatformMark } from "../components/ui/indicators";
import { Button, Card, ErrorNotice, Pill, SegmentedControl, Skeleton } from "../components/ui/primitives";
import { useCurrentUser } from "../context/auth";
import { useAudit, useConnectors, useCreateUser, useUpdateUser, useUsers } from "../hooks/queries";
import { api } from "../lib/api";
import { formatDateTime, relativeTime } from "../lib/format";
import { SEED_TYPE_LABEL } from "../lib/meta";
import type { User } from "../lib/types";

const inputCls =
  "h-8 rounded-md border border-line-strong bg-surface-2 px-2.5 text-[13px] text-fg outline-none focus:border-accent/60";

function PasswordForm() {
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => navigate("/login", { replace: true }),
  });
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        change.mutate();
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-muted">
        Current password
        <input type="password" className={inputCls} value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        New password (10+ characters)
        <input type="password" className={inputCls} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
      </label>
      <Button type="submit" disabled={change.isPending}>Change password</Button>
      <span className="text-[11px] text-subtle">Signs you out everywhere.</span>
      {change.error && <div className="w-full"><ErrorNotice error={change.error} /></div>}
    </form>
  );
}

function UserAdmin({ me }: { me: User }) {
  const { data: users, isLoading } = useUsers(true);
  const create = useCreateUser();
  const update = useUpdateUser();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "analyst" as User["role"] });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(form, { onSuccess: () => setForm({ name: "", email: "", password: "", role: "analyst" }) });
  };
  return (
    <Card title="Users" bodyClassName="p-0">
      {isLoading || !users ? <Skeleton className="m-4 h-24" /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line text-xs text-subtle">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Last sign-in</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2 text-fg">{u.name}{u.id === me.id && <span className="ml-1.5 text-[11px] text-subtle">(you)</span>}</td>
                  <td className="px-4 py-2 text-muted">{u.email}</td>
                  <td className="px-4 py-2">
                    <select
                      aria-label={`Role for ${u.name}`}
                      value={u.role}
                      disabled={u.id === me.id}
                      onChange={(e) => update.mutate({ id: u.id, role: e.target.value as User["role"] })}
                      className="rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 text-xs text-fg"
                    >
                      <option value="analyst">Analyst</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </td>
                  <td className="px-4 py-2 text-xs text-subtle">{relativeTime(u.last_login_at)}</td>
                  <td className="px-4 py-2">
                    <Button
                      size="sm"
                      variant={u.is_active ? "ghost" : "secondary"}
                      disabled={u.id === me.id}
                      onClick={() => update.mutate({ id: u.id, is_active: !u.is_active })}
                    >
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3 border-t border-line p-4">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Name
          <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Email
          <input type="email" className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Initial password
          <input type="password" className={inputCls} value={form.password} minLength={10} autoComplete="new-password"
            onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Role
          <select className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}>
            <option value="analyst">Analyst</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <Button type="submit" variant="primary" disabled={create.isPending}>Add user</Button>
        {(create.error || update.error) && <div className="w-full"><ErrorNotice error={create.error ?? update.error} /></div>}
      </form>
    </Card>
  );
}

function AuditLog() {
  const { data, isLoading } = useAudit(true);
  return (
    <Card title="Audit log" bodyClassName="p-0">
      {isLoading || !data ? <Skeleton className="m-4 h-24" /> : data.length === 0 ? (
        <p className="p-4 text-xs text-subtle">No events yet.</p>
      ) : (
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <tbody className="divide-y divide-line">
              {data.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-1.5 whitespace-nowrap text-subtle">{formatDateTime(e.at)}</td>
                  <td className="px-4 py-1.5 font-mono text-fg">{e.action}</td>
                  <td className="max-w-md truncate px-4 py-1.5 text-muted" title={e.target ?? undefined}>{e.target}</td>
                  <td className="px-4 py-1.5 font-mono text-subtle">{e.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

const CONNECTOR_FILTERS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "needs", label: "Needs configuration" },
] as const;

function ConnectorCatalog() {
  const { data, isLoading, error } = useConnectors();
  const [filter, setFilter] = useState<(typeof CONNECTOR_FILTERS)[number]["key"]>("all");
  const list = (data ?? []).filter((c) => (filter === "active" ? c.configured : filter === "needs" ? !c.configured : true));
  return (
    <Card
      title={`Source connectors${data ? ` (${data.filter((c) => c.configured).length}/${data.length} active)` : ""}`}
      actions={<SegmentedControl label="Filter connectors" options={[...CONNECTOR_FILTERS]} value={filter} onChange={setFilter} />}
      bodyClassName="p-0"
    >
      {error ? <div className="p-4"><ErrorNotice error={error} /></div> : isLoading ? <Skeleton className="m-4 h-40" /> : (
        <ul className="divide-y divide-line">
          {list.map((c) => (
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
                  {c.supports.length > 0 ? `Inputs: ${c.supports.map((s) => SEED_TYPE_LABEL[s]).join(", ")}` : "Runs on discovered pivots"}
                  {c.accepts_pivots.length > 0 && ` · follows discovered ${c.accepts_pivots.join(", ")}s`}
                </p>
              </div>
              {c.configured ? (
                <Pill color="var(--st-found)">Active</Pill>
              ) : (
                <Pill color="var(--st-auth)" className="font-mono">Set {c.requires.join(", ")}</Pill>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SettingsPage() {
  const me = useCurrentUser();
  return (
    <div className="mx-auto max-w-[1100px] space-y-5 p-6">
      <div>
        <h1 className="text-base font-semibold text-fg">Settings</h1>
        <p className="text-xs text-muted">
          Source credentials and operator contact are server-side environment variables (see backend/.env.example) and never
          reach the browser.
        </p>
      </div>
      {me && (
        <Card title="Account">
          <div className="mb-4 text-[13px]">
            <span className="text-fg">{me.name}</span> <span className="text-muted">· {me.email} · {me.role === "admin" ? "Administrator" : "Analyst"}</span>
          </div>
          <PasswordForm />
        </Card>
      )}
      {me?.role === "admin" && <UserAdmin me={me} />}
      <ConnectorCatalog />
      {me?.role === "admin" && <AuditLog />}
    </div>
  );
}
