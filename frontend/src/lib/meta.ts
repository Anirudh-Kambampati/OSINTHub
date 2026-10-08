import type { ConfidenceLevel, InvestigationStatus, RunStatus, SeedType } from "./types";

export const SEED_TYPE_LABEL: Record<SeedType, string> = {
  username: "Username",
  email: "Email",
  person: "Person / name",
  domain: "Domain",
  url: "URL",
};

export const CONFIDENCE_META: Record<ConfidenceLevel, { label: string; color: string }> = {
  very_high: { label: "Very high", color: "var(--conf-very-high)" },
  high: { label: "High", color: "var(--conf-high)" },
  medium: { label: "Medium", color: "var(--conf-medium)" },
  low: { label: "Low", color: "var(--conf-low)" },
};

export function levelOf(score: number): ConfidenceLevel {
  if (score >= 0.85) return "very_high";
  if (score >= 0.6) return "high";
  if (score >= 0.3) return "medium";
  return "low";
}

export const RUN_STATUS_META: Record<RunStatus, { label: string; color: string; description: string }> = {
  pending: { label: "Queued", color: "var(--text-subtle)", description: "Waiting to run." },
  running: { label: "Running", color: "var(--st-running)", description: "Querying the source now." },
  found: { label: "Found", color: "var(--st-found)", description: "The source returned public results." },
  not_found: { label: "Not found", color: "var(--st-not-found)", description: "The source was queried and had no match." },
  not_verified: {
    label: "Not verified",
    color: "var(--st-not-verified)",
    description: "The public source could not be legitimately queried, so presence is unknown.",
  },
  error: { label: "Error", color: "var(--st-error)", description: "The source failed; this is not the same as not found." },
  rate_limited: { label: "Rate limited", color: "var(--st-rate-limited)", description: "The source asked us to slow down." },
  requires_auth: {
    label: "Requires auth",
    color: "var(--st-auth)",
    description: "Needs official API credentials configured on the server.",
  },
  skipped: { label: "Skipped", color: "var(--text-subtle)", description: "Not applicable." },
};

export const INVESTIGATION_STATUS_META: Record<InvestigationStatus, { label: string; color: string }> = {
  pending: { label: "Queued", color: "var(--text-subtle)" },
  running: { label: "Running", color: "var(--st-running)" },
  completed: { label: "Completed", color: "var(--st-found)" },
  partial: { label: "Partial", color: "var(--st-not-verified)" },
  failed: { label: "Failed", color: "var(--st-error)" },
};

export const ATTRIBUTE_LABEL: Record<string, string> = {
  name: "Name",
  username: "Username",
  email: "Email",
  phone: "Phone",
  website: "Website",
  organization: "Organization",
  occupation: "Occupation",
  location: "Location",
  bio: "Bio",
  registrar: "Registrar",
  registered_at: "Registered",
  expires_at: "Expires",
  registry_status: "Registry status",
  nameserver: "Nameserver",
  mail_server: "Mail server",
  ip_address: "IP address",
  spf: "SPF policy",
  dmarc: "DMARC policy",
  certificate_issuer: "Certificate issuer",
  subdomain_count: "Subdomains seen",
  first_archived: "First archived",
  last_archived: "Last archived",
  title: "Page title",
  description: "Description",
  author: "Author",
  creator_tool: "Creator tool",
  producer: "Producer",
  created_at: "Created",
  modified_at: "Modified",
  linked_account: "Linked account",
  avatar: "Profile image",
  image: "Image",
  alias: "Alias",
  domain: "Domain",
  email_provider: "Email provider",
  domain_accepts_mail: "Domain accepts mail",
  technology: "Technology",
  network_name: "Network",
  network_owner: "Network owner",
  network_range: "Address range",
  country: "Country",
  open_port: "Open port",
  reverse_hostname: "Hostname",
  known_vulnerability: "Known vulnerability",
  tag: "Tag",
  security_contact: "Security contact",
  security_policy: "Disclosure policy",
  security_txt_expires: "security.txt expires",
  security_hiring: "Security hiring",
  security_acknowledgments: "Acknowledgments",
};

export const attributeLabel = (a: string) => ATTRIBUTE_LABEL[a] ?? a.replace(/_/g, " ");

export const IDENTITY_GROUPS: { title: string; attributes: string[] }[] = [
  { title: "Identifiers", attributes: ["name", "alias", "username", "email", "phone", "location", "bio"] },
  { title: "Email", attributes: ["email_provider", "domain", "domain_accepts_mail"] },
  { title: "Affiliations & web", attributes: ["organization", "occupation", "website", "title", "description"] },
  {
    title: "Registration",
    attributes: ["registrar", "registered_at", "expires_at", "registry_status", "first_archived", "last_archived"],
  },
  {
    title: "Infrastructure",
    attributes: ["nameserver", "mail_server", "ip_address", "spf", "dmarc", "certificate_issuer", "subdomain_count", "technology"],
  },
  {
    title: "Network exposure",
    attributes: ["network_owner", "network_name", "network_range", "country", "open_port", "reverse_hostname", "known_vulnerability"],
  },
  {
    title: "Security contacts",
    attributes: ["security_contact", "security_policy", "security_txt_expires", "security_acknowledgments", "security_hiring"],
  },
];

export const ENTITY_KIND_LABEL: Record<string, string> = {
  person: "Person",
  username: "Username",
  email: "Email",
  phone: "Phone",
  profile: "Profile",
  organization: "Organization",
  website: "Website",
  domain: "Domain",
  repository: "Repository",
  document: "Document",
  image: "Image",
  ip: "IP address",
  certificate: "Certificate",
  location: "Location",
  mention: "Mention",
};

/** Sidebar "Sources" groups -> backend source categories. */
export const SOURCE_GROUPS: Record<string, { label: string; categories: string[] }> = {
  social: { label: "Social", categories: ["social", "identity"] },
  web: { label: "Web", categories: ["web", "search", "news", "archive"] },
  code: { label: "Code", categories: ["code"] },
  domains: { label: "Domains", categories: ["domain", "dns", "certificate"] },
  documents: { label: "Documents", categories: ["document"] },
};

export const MENTION_CATEGORIES = [
  { key: "", label: "All" },
  { key: "social", label: "Social" },
  { key: "web", label: "Web" },
  { key: "news", label: "News" },
  { key: "document", label: "Documents" },
];

export const TIMELINE_KINDS = [
  { key: "", label: "All" },
  { key: "profile", label: "Profiles" },
  { key: "mention", label: "Mentions" },
  { key: "repository", label: "Repositories" },
  { key: "document", label: "Documents" },
  { key: "domain", label: "Domains" },
  { key: "certificate", label: "Certificates" },
  { key: "archive", label: "Archive" },
];

/** Neutral monograms rather than brand logos. */
export const PLATFORM_META: Record<string, { label: string; mono: string; hue: number }> = {
  github: { label: "GitHub", mono: "GH", hue: 220 },
  gitlab: { label: "GitLab", mono: "GL", hue: 20 },
  hackernews: { label: "Hacker News", mono: "HN", hue: 28 },
  devto: { label: "DEV", mono: "DV", hue: 250 },
  keybase: { label: "Keybase", mono: "KB", hue: 205 },
  bluesky: { label: "Bluesky", mono: "BS", hue: 210 },
  medium: { label: "Medium", mono: "MD", hue: 150 },
  reddit: { label: "Reddit", mono: "RD", hue: 15 },
  youtube: { label: "YouTube", mono: "YT", hue: 0 },
  x: { label: "X", mono: "X", hue: 215 },
  instagram: { label: "Instagram", mono: "IG", hue: 330 },
  linkedin: { label: "LinkedIn", mono: "IN", hue: 205 },
  gravatar: { label: "Gravatar", mono: "GV", hue: 190 },
  mastodon: { label: "Mastodon", mono: "MA", hue: 260 },
  codeberg: { label: "Codeberg", mono: "CB", hue: 200 },
  huggingface: { label: "Hugging Face", mono: "HF", hue: 45 },
  npm: { label: "npm", mono: "NP", hue: 355 },
  cratesio: { label: "crates.io", mono: "CR", hue: 30 },
  dockerhub: { label: "Docker Hub", mono: "DH", hue: 205 },
  stackoverflow: { label: "Stack Overflow", mono: "SO", hue: 28 },
  codewars: { label: "Codewars", mono: "CW", hue: 0 },
  chesscom: { label: "Chess.com", mono: "CH", hue: 95 },
  lichess: { label: "Lichess", mono: "LI", hue: 0 },
  orcid: { label: "ORCID", mono: "ID", hue: 85 },
  wikidata: { label: "Wikidata", mono: "WD", hue: 210 },
  email_intel: { label: "Email domain", mono: "@", hue: 190 },
  ip_intel: { label: "IP intelligence", mono: "IP", hue: 160 },
  security_txt: { label: "security.txt", mono: "ST", hue: 140 },
  hn_search: { label: "Hacker News search", mono: "HN", hue: 28 },
  web_search: { label: "Web search", mono: "WS", hue: 215 },
  website: { label: "Website", mono: "WB", hue: 215 },
  dns: { label: "DNS", mono: "NS", hue: 170 },
  rdap: { label: "RDAP", mono: "RD", hue: 170 },
  certificates: { label: "Certificates", mono: "CT", hue: 140 },
  wayback: { label: "Wayback", mono: "AR", hue: 30 },
  documents: { label: "Documents", mono: "PDF", hue: 0 },
};

export const MONITOR_OPTIONS: { hours: number | null; label: string }[] = [
  { hours: null, label: "Off" },
  { hours: 24, label: "Daily" },
  { hours: 24 * 7, label: "Weekly" },
  { hours: 24 * 30, label: "Monthly" },
];
