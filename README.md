# OSINT Intelligence Console

An evidence-backed public-information investigation workspace. Enter a username, email, name, domain or URL; the
console queries 36 legitimate public sources, normalizes what they say into **observations with provenance**,
resolves which discovered profiles belong to the same public entity, and presents a profile, identity clusters,
mentions, timeline and relationship graph — every fact links back to the source that stated it.

```
SEARCH → CLASSIFY → QUEUE → CONNECTORS → PIVOTS (websites, IPs, documents) → OBSERVATIONS
       → ENTITY RESOLUTION + CLUSTERING → ANALYST REVIEW → PROFILE / GRAPH / TIMELINE / REPORT
```

## Run it

### Production-style (Docker)

```bash
cp .env.example .env          # set OSINT_DB_PASSWORD and OSINT_OPERATOR_CONTACT
docker compose up -d --build
# open http://localhost:8080 — the first account you create becomes the administrator
```

Services: `db` (PostgreSQL 16), `api` (FastAPI; applies migrations on start), `worker` (investigation queue,
monitoring, retention), `web` (nginx serving the console and proxying `/api` on the same origin). Put a
TLS-terminating proxy in front of `web` for anything beyond localhost.

### Local development

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8000
```

Development uses SQLite and runs the worker inside the API process. Configuration: `backend/.env.example`.

### Tests

```bash
cd backend && uv run pytest                                   # 100+ tests, SQLite
OSINT_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest  # same suite on PostgreSQL
uv run python -m scripts.smoke_connectors                     # live check of every connector
cd frontend && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend suite on SQLite and PostgreSQL, migrations up/down/up, the
frontend typecheck/tests/build, and boots the full Docker stack.

## Sources

| Area | Sources (access method) |
|---|---|
| Code & developer | GitHub (REST API; email via user + commit author-email search), GitLab, Codeberg, Hugging Face, npm registry, crates.io, Docker Hub, Stack Overflow, Codewars |
| Social & identity | Hacker News (Firebase + Algolia), DEV, Keybase (cryptographic proofs), Bluesky (AppView), Mastodon (5 major instances, verified profile fields), Medium (RSS), Gravatar, Chess.com, Lichess |
| People (name seeds) | ORCID public registry, Wikidata (notable people only), GitHub/Stack Overflow name search |
| Mentions | Hacker News search, Brave Search API* |
| Credentialed APIs | Reddit*, X*, YouTube* — official APIs only |
| Not legitimately queryable | Instagram, LinkedIn — always reported **Not verified**, never scraped |
| Email | Provider classification (free/disposable/custom), MX/SPF/DMARC — no mailbox probing, no breach data |
| Domain & web | DNS-over-HTTPS, RDAP (registrant contacts excluded), Certificate Transparency (crt.sh), Wayback Machine, security.txt, website metadata + `rel=me` + tech fingerprint (robots.txt honoured) |
| Pivots | Websites found on profiles → website + archive; resolved IPs → RDAP owner + Shodan InternetDB (passive index); linked PDFs → document metadata only |

\* needs a server-side key (`.env.example`). Wikidata needs `OSINT_OPERATOR_CONTACT` (Wikimedia's robot policy).
Every source reports a distinct state — **Found, Not found, Not verified, Error, Rate limited, Requires auth** —
and errors never masquerade as "not found". The Settings page shows which sources are active.

## How conclusions are reached

**Observations, not truth.** Entities (profile, email, website, domain, repository, IP…) are anchors; everything
believed about them is an `Observation(entity, attribute, value, source, confidence, observed_at)`, and every source
is a stored retrieval with URL, time and reliability. Re-runs append observations, so first/last-seen accumulates.

**Entity resolution** (`backend/app/services/resolver.py`) scores each profile from explainable factors:
exact username +0.35 · seed email listed +0.60 · verified link (Keybase proof, Mastodon-verified field, crates.io
login) +0.45 · mutual link +0.40 · shared email +0.40 · one-way link +0.25 · shared website +0.25 · shared name /
organization / location · different public name −0.20. Each factor counts once; corroboration is capped; scores never
exceed 97%. A profile's own website corroborates it only if the site links back.

**Identity clusters** group profiles tied by strong pairwise evidence, so several people using one handle appear as
separate identities instead of one blended profile.

**Analyst decisions** — confirm or reject any profile; the verdict overrides the score, re-runs resolution and is
written to the audit log.

**Attribute confidence** is a noisy-OR across independent connectors of
`observation confidence × profile match × source reliability`, capped at 97%. Mention confidence is scaled by the
match of the profile it belongs to; pure text matches stay low. Weak values display rounded (`~35%`).

## Analyst workflow

Notes, tags, monitoring (daily/weekly/monthly re-runs with "new since last run"), per-investigation access log, and
exports: printable HTML report (print to PDF), full JSON with provenance, and CSV datasets (attributes, profiles,
mentions, observations, timeline, source checks — formula-injection safe).

## Security & privacy

- **Accounts:** scrypt-hashed passwords, server-side sessions in HttpOnly SameSite cookies (Secure in production),
  CSRF header on every state change, login rate limiting with timing-safe failure paths, admin/analyst roles,
  per-user investigation isolation (non-owners get 404), audit log of logins, investigations and decisions.
- **Outbound requests:** SSRF guard on every hop (public IPs only, ports 80/443, no credentials in URLs), credentials
  stripped on cross-host redirects, response size caps, per-host concurrency, one retry on transient 5xx (never on
  429), secrets redacted from the access log, operator contact in the User-Agent.
- **Rendering:** external text reduced to plain text server-side; links only for http(s); strict CSP from nginx;
  reports served with `default-src 'none'`; images proxied so the investigator's browser never contacts platforms.
- **Collection boundaries:** no phone extraction, no registrant contacts, no document body parsing, no breach or
  credential sources, no login/CAPTCHA/robots bypass, no port scanning (InternetDB is a passive index).
- **Retention:** `OSINT_RETENTION_DAYS` deletes old investigations automatically; deletion is available per case.

## Operations

- **Queue:** pending investigations are claimed atomically from the database; workers heartbeat, stale work is
  requeued, so restarts don't lose investigations. Scale by running more `worker` replicas (PostgreSQL).
- **Health:** `/healthz` (process) and `/readyz` (database). Structured JSON logs with request IDs
  (`OSINT_LOG_JSON=true`).
- **Migrations:** Alembic (`backend/alembic/versions`), applied automatically by the API container.

## Extending

Add a source: create `backend/app/connectors/<name>.py` subclassing `Connector` (or `JsonProfileConnector` for a
simple profile API), implement `fetch` (network via `ctx.http`) and a pure `normalize` that fills `Findings`,
register it in `connectors/registry.py`, add a fixture test and a smoke target.

## Known limits

- Platforms without legitimate public access (Instagram, LinkedIn) are reported, not searched; Reddit, X, YouTube
  and web search need your own API keys.
- Free public APIs rate-limit (GitHub 60 requests/hour anonymously — set `OSINT_GITHUB_TOKEN`; archive.org and
  crt.sh are often slow). Affected sources show **Rate limited** / **Error** and the case is marked partial.
- Login rate limiting is per API process; put the API behind a proxy-level limiter if you run many replicas.
