import type {
  ClassifyResult,
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

const TOKEN_KEY = "osint.apiToken";

export function getApiToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setApiToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token simply isn't remembered */
  }
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
  const token = getApiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
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

export const api = {
  classify: (value: string) => json<ClassifyResult>("/api/classify", { method: "POST", body: JSON.stringify({ value }) }),
  connectors: () => json<ConnectorInfo[]>("/api/connectors"),
  investigations: () => json<Investigation[]>("/api/investigations"),
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
