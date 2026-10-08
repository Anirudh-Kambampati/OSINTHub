# OSINT Intelligence Console

An evidence-backed public-information investigation workspace. Enter a username, email, name, domain or URL; the
console queries legitimate public sources, normalizes what they say into **observations with provenance**, resolves
which discovered profiles plausibly belong to the same public entity, and presents the result as a profile, mentions,
timeline and relationship graph — where every fact links back to the source that stated it.

```
SEARCH → CLASSIFY → CONNECTORS → NORMALIZE → OBSERVATIONS → RESOLVE → SCORE → PROFILE / GRAPH / TIMELINE / EVIDENCE
```

## Quick start

Requirements: Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# Backend (http://127.0.0.1:8000)
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000

# Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Configuration lives in `backend/.env` (see `backend/.env.example`). Everything works without API keys; sources that
require credentials report **Requires auth** until you add them.

### Tests

```bash
cd backend && uv run pytest        # classification, normalization, resolver, pipeline, API, security
cd frontend && npm test            # UI states: empty, loading, running, populated, partial, no-results, evidence drawer
```

## Architecture

| Layer | Location | Notes |
|---|---|---|
| Input classification | `backend/app/core/classify.py` | username / email / person / domain / URL, with ambiguity alternatives (`john.dev`) |
| Connectors | `backend/app/connectors/` | one module per source, common `Connector` contract, registered in `registry.py` |
| Normalization | `core/normalize.py`, `connectors/base.py::Findings` | one canonical form per attribute; identifier attributes become graph entities |
| Safe HTTP | `core/net.py` | SSRF guard, per-hop redirect validation, size caps, per-host concurrency, access log, secret redaction |
| Orchestration | `services/orchestrator.py` | phase 1 (seed) → phase 2 (website pivots) → phase 3 (document pivots) → resolution |
| Persistence | `services/store.py`, `models.py`, `alembic/` | SQLite by default, PostgreSQL via `OSINT_DATABASE_URL` |
| Entity resolution | `services/resolver.py` (pure), `services/resolution.py` (applies it) | explainable factors, capped scores |
| Read models | `services/views.py` | identity aggregation, presence, mentions, timeline, graph, evidence |
| API | `api/routes.py` | FastAPI, typed responses (`schemas.py`) |
| UI | `frontend/src/` | React + TypeScript, Tailwind v4 tokens, TanStack Query, React Flow + dagre |

### Data model: observations, not truth

Nothing stores "the truth" about a subject. **Entities** (profile, email, website, domain, repository, document,
certificate, IP…) are thin anchors. Everything believed about them is an **Observation**:
`(entity, attribute, value, normalized_value, source, confidence, observed_at)`. Every observation, relationship,
mention and timeline event references a **Source** — a concrete retrieval with URL, connector, category, reliability
and collection time. Re-running an investigation appends observations, so first/last-observed dates accumulate.

Other tables: `investigations`, `connector_runs` (per-source status, stored independently so one failure never sinks
the investigation), `relationships`, `entity_matches` (resolver output with factors), `mentions` (metadata + ≤280-char
snippet only), `timeline_events`, `access_log` (audit of every outbound request).

### Confidence

- **Observation confidence** — how clearly a source states a value (structured API field vs. page meta tag).
- **Match score** (per profile) — sum of explainable factors from `resolver.py`: seed factors (exact username +0.35,
  publicly listed seed email +0.60, …), corroboration with *other anchored* candidates (mutual link +0.40, verified
  Keybase proof +0.45, shared email +0.40, shared website +0.25, shared name/org…), contradictions (different public
  name −0.20). Each corroboration type counts once; corroboration is capped at 0.60; scores never exceed 0.97.
  A profile's own website is not independent evidence unless it links back.
- **Attribute confidence** — noisy-OR across *independent connectors* of
  `observation confidence × profile match × source reliability`. Agreement raises confidence; one source never makes
  a value certain.
- **Mention confidence** — mention confidence × the match score of the profile it's attributed to. Pure text
  matches stay LOW.
- Bands: LOW < 0.30 ≤ MEDIUM < 0.60 ≤ HIGH < 0.85 ≤ VERY HIGH. Values below 60% are shown rounded to 5% (`~35%`)
  to avoid false precision. Profiles below 0.30 don't contribute to the identity; the subject is only *named* from
  profiles at ≥ 0.60.

Labels are always hedged: *High-confidence match*, *Likely same entity*, *Possible match*, *Unverified*,
*Conflicting evidence*.

## Sources

| Connector | Access method | Inputs |
|---|---|---|
| GitHub | Official REST API (optional token) | username, email (`in:email` search), name |
| GitLab | Official REST API v4 | username |
| Hacker News | Official Firebase API + Algolia HN Search API | username |
| Hacker News search | Algolia HN Search API (text mentions) | username, name, domain, URL |
| DEV | Official Forem API | username |
| Keybase | Public lookup API (cryptographic proofs) | username |
| Bluesky | Public AppView XRPC API | username |
| Medium | Public author RSS feed | username |
| Gravatar | REST API v3 (SHA-256 of email) | email |
| Reddit / X / YouTube | Official APIs — **only with credentials** | username |
| Web search | Brave Search API — **only with key** | all |
| Instagram / LinkedIn | No legitimate automated lookup → always **Not verified** | username |
| Website | HTTP fetch, robots.txt honoured: title, meta, `rel=me`, `mailto:`, linked PDFs | URL, domain, pivots |
| Documents | PDF document-level metadata only (title, author, creator tool, dates) | pivots, `.pdf` URLs |
| DNS | DNS-over-HTTPS (A/AAAA/MX/NS/SPF/DMARC) | domain, URL, non-freemail email domain |
| RDAP | rdap.org bootstrap — registrar/dates/status; **registrant contacts excluded** | same |
| Certificate Transparency | crt.sh | same |
| Wayback Machine | Internet Archive CDX API | domain, URL, website pivots |

Run states are distinct and never collapsed: **Found, Not found, Not verified, Error, Rate limited, Requires auth**.
Transient upstream 502/503/504 get one polite retry; 429 is never retried.

### Adding a connector

1. Create `backend/app/connectors/<name>.py` subclassing `Connector`: set `name`, `label`, `category`, `reliability`,
   `supports` (and optionally `requires`, `accepts_pivots`, `timeout`, `targets()`, `manual_url()`).
2. Implement `fetch()` (network via `ctx.http`, raise `RateLimited` / `AuthRequired` / `NotVerifiable` /
   `ConnectorError`) and a pure `normalize()` that fills a `Findings` (profile platforms can use
   `_profile.emit_profile`).
3. Register it in `connectors/registry.py` and add a fixture-based normalization test.

## Security & privacy

- **SSRF**: only http(s) on ports 80/443; hostnames resolved and rejected if any address is non-public (loopback,
  RFC1918, link-local/metadata, reserved, multicast, IPv4-mapped); every redirect hop re-validated; embedded
  credentials rejected. Credentials are stripped on cross-host redirects. Response sizes are capped.
- **Secrets** are server-side env vars only, redacted from the access log, never sent to the browser.
- **Optional auth**: `OSINT_API_TOKEN` enforces a bearer token (constant-time compare) on every API route; the token
  is held in `sessionStorage`. Investigation creation is rate-limited per client.
- **Untrusted content** is reduced to plain text and length-capped server-side; React escapes on render; links render
  only for http(s) with `rel="noopener noreferrer nofollow"`; the app sets `referrer: no-referrer`.
- **OPSEC**: profile images are fetched through `/api/observations/{id}/image` so the investigator's browser never
  contacts the platform; only observed image URLs can be proxied (no open proxy); SVG is refused.
- **Collection boundaries**: no phone extraction, no registrant contacts, no document body parsing, no credential or
  leak sources, no login/CAPTCHA/robots bypass. Restricted platforms are reported, not scraped.

## Design decisions (and where they could change)

- **Greenfield**: the repository was empty, so the stack was chosen to be minimal: FastAPI + async SQLAlchemy +
  Alembic; Vite + React.
- **SQLite default, Postgres supported**: zero-setup local use. The schema is portable (UUID strings, JSON, tz-aware
  timestamps) and the migration compiles to PostgreSQL DDL; run `docker compose up -d db` and set
  `OSINT_DATABASE_URL`. Not yet exercised end-to-end against a live Postgres.
- **In-process jobs**: investigations run as bounded asyncio tasks behind `JobRunner`, with live per-source status
  persisted to `connector_runs`. Interrupted runs are marked partial on restart. Swap `JobRunner` for arq/Celery to
  scale horizontally.
- **Single-tenant**: there was no existing user system; an optional shared token protects the API. Per-user
  ownership of investigations is the next step for multi-user deployments.
- **Resolver is subject-centric**, not a full clustering engine: when one handle is held by several different people
  (e.g. `octocat`), profiles are scored against the seed and contradictions push them to *Conflicting evidence*
  rather than being split into separate clusters. Multi-cluster resolution is a natural extension of `resolver.py`.
- **Image similarity** is intentionally not used as identity evidence.
