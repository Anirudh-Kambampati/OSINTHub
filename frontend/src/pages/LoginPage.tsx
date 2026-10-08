import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { Button, ErrorNotice, Skeleton } from "../components/ui/primitives";
import { keys, useAuthStatus } from "../hooks/queries";
import { api } from "../lib/api";

function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <input
        {...props}
        className="h-9 rounded-md border border-line-strong bg-surface-2 px-3 text-[13px] text-fg outline-none focus:border-accent/60"
      />
    </label>
  );
}

export function LoginPage() {
  const { data: status, isLoading } = useAuthStatus();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [mismatch, setMismatch] = useState(false);
  const setup = !!status?.needs_setup;

  const submit = useMutation({
    mutationFn: () => (setup ? api.register(form.email, form.name, form.password) : api.login(form.email, form.password)),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: keys.auth });
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "auth" });
      navigate(from === "/login" ? "/" : from, { replace: true });
    },
  });

  if (isLoading) return <Skeleton className="m-auto mt-32 h-64 w-80" />;
  if (status?.user) return <Navigate to="/" replace />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (setup && form.password !== form.confirm) return setMismatch(true);
    setMismatch(false);
    submit.mutate();
  };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="flex min-h-full items-center justify-center bg-bg px-4 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-4 flex size-11 items-center justify-center rounded-xl border border-line-strong bg-surface-2">
            <Radar className="size-5 text-accent" aria-hidden />
          </div>
          <h1 className="text-lg font-semibold text-fg">{setup ? "Set up OSINT Console" : "Sign in to OSINT Console"}</h1>
          <p className="mt-1 text-[13px] text-muted">
            {setup ? "Create the first account. It becomes the administrator." : "Public-information investigation workspace."}
          </p>
        </div>
        <form onSubmit={onSubmit} className="space-y-3 rounded-lg border border-line bg-surface p-5">
          {setup && <Field label="Name" value={form.name} onChange={set("name")} autoComplete="name" required />}
          <Field label="Email" type="email" value={form.email} onChange={set("email")} autoComplete="email" required autoFocus />
          <Field
            label={setup ? "Password (10+ characters)" : "Password"}
            type="password"
            value={form.password}
            onChange={set("password")}
            autoComplete={setup ? "new-password" : "current-password"}
            minLength={setup ? 10 : undefined}
            required
          />
          {setup && (
            <Field label="Confirm password" type="password" value={form.confirm} onChange={set("confirm")} autoComplete="new-password" required />
          )}
          {mismatch && <ErrorNotice error={new Error("Passwords don't match.")} />}
          {submit.error && <ErrorNotice error={submit.error} />}
          <Button type="submit" variant="primary" className="w-full" disabled={submit.isPending}>
            {submit.isPending ? "Please wait…" : setup ? "Create administrator" : "Sign in"}
          </Button>
        </form>
        {!setup && (
          <p className="mt-4 text-center text-xs text-subtle">
            Accounts are created by an administrator{status?.allow_registration ? " or via self-registration" : ""}.
          </p>
        )}
      </div>
    </div>
  );
}
