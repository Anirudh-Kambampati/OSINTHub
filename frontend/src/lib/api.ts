import type {
  AccessLogEntry,
  AuditEvent,
  AuthStatus,
  ClassifyResult,
  Decision,
  Note,
  User,
  ConnectorInfo,
  EntityEvidence,
  Graph,
  Investigation,
  InvestigationDetail,
  MentionPage,
  ProfileView,
  SeedType,
  Source,
  TimelineEvent,
} from "./types";

/** Called when the server says the session is gone; the auth layer redirects to sign-in. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  // Required on state-changing requests; browsers can't send it cross-site without a preflight.
  headers.set("X-OSINT-CSRF", "1");
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/api/auth/")) onUnauthorized?.();
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const inv = (id: string) => `/api/investigations/${encodeURIComponent(id)}`;

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export type CsvDataset = "attributes" | "profiles" | "mentions" | "observations" | "timeline" | "sources";

export const exportUrls = (id: string) => ({
  json: `${inv(id)}/export.json`,
  report: `${inv(id)}/report.html`,
  csv: (dataset: CsvDataset) => `${inv(id)}/export.csv?dataset=${dataset}`,
});

export const api = {
  // auth & users
  authStatus: () => json<AuthStatus>("/api/auth/status"),
  login: (email: string, password: string) => json<User>("/api/auth/login", send("POST", { email, password })),
  register: (email: string, name: string, password: string) =>
    json<User>("/api/auth/register", send("POST", { email, name, password })),
  logout: async () => {
    await request("/api/auth/logout", { method: "POST" });
  },
  changePassword: async (current_password: string, new_password: string) => {
    await request("/api/auth/password", send("POST", { current_password, new_password }));
  },
  users: () => json<User[]>("/api/users"),
  createUser: (body: { email: string; name: string; password: string; role: User["role"] }) =>
    json<User>("/api/users", send("POST", body)),
  updateUser: (id: string, body: Partial<Pick<User, "role" | "is_active">> & { password?: string }) =>
    json<User>(`/api/users/${encodeURIComponent(id)}`, send("PATCH", body)),
  audit: () => json<AuditEvent[]>("/api/audit"),

  classify: (value: string) => json<ClassifyResult>("/api/classify", { method: "POST", body: JSON.stringify({ value }) }),
  connectors: () => json<ConnectorInfo[]>("/api/connectors"),
  investigations: (q?: string) => json<Investigation[]>(`/api/investigations${qs({ q })}`),
  updateInvestigation: (id: string, body: { title?: string; tags?: string[]; monitor_interval_hours?: number | null }) =>
    json<InvestigationDetail>(inv(id), send("PATCH", body)),
  notes: (id: string) => json<Note[]>(`${inv(id)}/notes`),
  addNote: (id: string, body: string) => json<Note>(`${inv(id)}/notes`, send("POST", { body })),
  deleteNote: async (id: string, noteId: string) => {
    await request(`${inv(id)}/notes/${encodeURIComponent(noteId)}`, { method: "DELETE" });
  },
  accessLog: (id: string) => json<AccessLogEntry[]>(`${inv(id)}/access-log`),
  setDecision: (entityId: string, decision: Decision, note?: string) =>
    json<EntityEvidence>(`/api/entities/${encodeURIComponent(entityId)}/decision`, send("PUT", { decision, note })),
  clearDecision: (entityId: string) =>
    json<EntityEvidence>(`/api/entities/${encodeURIComponent(entityId)}/decision`, { method: "DELETE" }),
  createInvestigation: (seed: string, seed_type?: SeedType) =>
    json<InvestigationDetail>("/api/investigations", { method: "POST", body: JSON.stringify({ seed, seed_type }) }),
  investigation: (id: string) => json<InvestigationDetail>(inv(id)),
  rerun: (id: string) => json<InvestigationDetail>(`${inv(id)}/search`, { method: "POST" }),
  deleteInvestigation: async (id: string) => {
    await request(inv(id), { method: "DELETE" });
  },
  profile: (id: string) => json<ProfileView>(`${inv(id)}/profile`),
  mentions: (id: string, opts: { category?: string; sort?: string; limit?: number; offset?: number }) =>
    json<MentionPage>(`${inv(id)}/mentions${qs(opts)}`),
  timeline: (id: string, kind?: string) => json<TimelineEvent[]>(`${inv(id)}/timeline${qs({ kind })}`),
  graph: (id: string, includeMentions: boolean) =>
    json<Graph>(`${inv(id)}/graph${qs({ include_mentions: includeMentions })}`),
  sources: (id: string) => json<Source[]>(`${inv(id)}/sources`),
  evidence: (entityId: string) => json<EntityEvidence>(`/api/entities/${encodeURIComponent(entityId)}/evidence`),
  /** Images are fetched through the backend proxy (with auth) so the browser never contacts the platform. */
  imageBlob: async (observationId: string) =>
    (await request(`/api/observations/${encodeURIComponent(observationId)}/image`)).blob(),
};
