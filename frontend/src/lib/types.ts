// Mirrors backend/app/schemas.py. Keep in sync when the API changes.

export type SeedType = "username" | "email" | "person" | "domain" | "url";
export type InvestigationStatus = "pending" | "running" | "completed" | "partial" | "failed";
export type RunStatus =
  | "pending"
  | "running"
  | "found"
  | "not_found"
  | "not_verified"
  | "error"
  | "rate_limited"
  | "requires_auth"
  | "skipped";
export type ConfidenceLevel = "low" | "medium" | "high" | "very_high";

export interface ClassifyResult {
  valid: boolean;
  type: SeedType | null;
  normalized: string | null;
  alternatives: SeedType[];
  error: string | null;
}

export interface Source {
  id: string;
  connector: string;
  name: string;
  category: string;
  kind: string;
  url: string;
  title: string | null;
  reliability: "low" | "medium" | "high";
  collected_at: string;
}

export interface Run {
  id: string;
  connector: string;
  label: string;
  category: string;
  target: string;
  phase: number;
  status: RunStatus;
  message: string | null;
  manual_url: string | null;
  result_count: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface Stats {
  new_entities: number;
  new_mentions: number;
  profiles: number;
  matched_profiles: number;
  mentions: number;
  sources: number;
  relationships: number;
  documents: number;
  domains: number;
  entities: number;
  connectors_run: number;
  connectors_total: number;
  confidence: number | null;
  level: ConfidenceLevel | null;
}

export interface Investigation {
  id: string;
  owner_id: string | null;
  owner_name: string | null;
  tags: string[];
  monitor_interval_hours: number | null;
  next_run_at: string | null;
  previous_completed_at: string | null;
  run_count: number;
  seed: string;
  seed_type: SeedType;
  title: string;
  status: InvestigationStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  stats: Stats;
}

export interface InvestigationDetail extends Investigation {
  runs: Run[];
}

export interface Factor {
  code: string;
  label: string;
  weight: number;
  related_entity_id: string | null;
}

export type Decision = "confirmed" | "rejected";

export interface Match {
  score: number;
  level: ConfidenceLevel;
  label: string;
  factors: Factor[];
  /** Identity cluster; 0 is the cluster of the best-matching profile. */
  cluster: number | null;
  decision: Decision | null;
  decision_note: string | null;
}

export interface Entity {
  id: string;
  kind: string;
  key: string;
  label: string;
  confidence: number;
  level: ConfidenceLevel;
  is_seed: boolean;
  data: Record<string, unknown> & { platform?: string; platform_label?: string; url?: string };
  match: Match | null;
  avatar_observation_id: string | null;
  /** Created since the previous completed run. */
  is_new: boolean;
}

export interface EntityRef {
  id: string;
  kind: string;
  label: string;
  platform: string | null;
  /** How strongly this entity is linked to the investigation subject. */
  confidence: number | null;
}

export interface EvidenceItem {
  observation_id: string;
  value: string;
  confidence: number;
  weight: number;
  observed_at: string;
  source: Source;
  entity: EntityRef;
}

export interface IdentityAttribute {
  attribute: string;
  value: string;
  normalized_value: string;
  confidence: number;
  level: ConfidenceLevel;
  first_observed: string;
  last_observed: string;
  source_count: number;
  evidence: EvidenceItem[];
}

export interface ImageCandidate {
  observation_id: string;
  original_url: string;
  confidence: number;
  level: ConfidenceLevel;
  first_observed: string;
  last_observed: string;
  source: Source;
  entity: EntityRef;
}

export interface Presence {
  connector: string;
  label: string;
  category: string;
  status: RunStatus;
  message: string | null;
  manual_url: string | null;
  target: string;
  profile: Entity | null;
}

export interface ProfileView {
  subject: Entity;
  seed_entity_id: string | null;
  confidence: number | null;
  level: ConfidenceLevel | null;
  images: ImageCandidate[];
  attributes: IdentityAttribute[];
  presence: Presence[];
  profiles: Entity[];
}

export interface Mention {
  id: string;
  url: string;
  title: string;
  snippet: string | null;
  category: string;
  association: string;
  published_at: string | null;
  observed_at: string;
  confidence: number;
  level: ConfidenceLevel;
  source: Source;
  entity: EntityRef | null;
}

export interface MentionPage {
  total: number;
  counts: Record<string, number>;
  items: Mention[];
}

export interface TimelineEvent {
  id: string;
  kind: string;
  title: string;
  detail: string | null;
  occurred_at: string;
  source: Source;
  entity: EntityRef | null;
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  confidence: number;
  level: ConfidenceLevel;
  is_seed: boolean;
  is_subject: boolean;
  data: Record<string, unknown> & { platform?: string; url?: string; match_label?: string | null };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  confidence: number;
  inferred: boolean;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface Observation {
  id: string;
  attribute: string;
  value: string;
  confidence: number;
  observed_at: string;
  source: Source;
}

export interface RelationshipOut {
  id: string;
  type: string;
  direction: "in" | "out";
  other: EntityRef;
  confidence: number;
  inferred: boolean;
  data: Record<string, unknown>;
  source: Source | null;
}

export interface EntityEvidence {
  entity: Entity;
  observations: Observation[];
  relationships: RelationshipOut[];
  mentions: number;
}

export interface ConnectorInfo {
  name: string;
  label: string;
  category: string;
  reliability: string;
  supports: SeedType[];
  accepts_pivots: string[];
  description: string;
  configured: boolean;
  requires: string[];
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "analyst";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthStatus {
  user: User | null;
  needs_setup: boolean;
  allow_registration: boolean;
}

export interface Note {
  id: string;
  body: string;
  author_id: string | null;
  author_name: string | null;
  created_at: string;
}

export interface AccessLogEntry {
  id: number;
  connector: string;
  method: string;
  url: string;
  status_code: number | null;
  error: string | null;
  at: string;
}

export interface AuditEvent {
  id: number;
  user_id: string | null;
  action: string;
  target: string | null;
  ip: string | null;
  at: string;
}
