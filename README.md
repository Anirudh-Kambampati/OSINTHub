# OSINThub

**The OSINT Intelligence Console** — an evidence-backed public-information investigation workspace.

Enter a username, email, name, domain or URL. OSINThub queries **36 legitimate public sources**,
normalizes what they say into **observations with provenance**, resolves which discovered profiles
belong to the same public entity, and hands the analyst a profile, identity graph, timeline and
exportable report — **every fact links back to the source that stated it**.

[![CI](https://github.com/Anirudh-Kambampati/OSINTHub/actions/workflows/ci.yml/badge.svg)](https://github.com/Anirudh-Kambampati/OSINTHub/actions/workflows/ci.yml)

```
SEARCH → CLASSIFY → QUEUE → CONNECTORS → PIVOTS (websites, IPs, documents) → OBSERVATIONS
       → ENTITY RESOLUTION + CLUSTERING → ANALYST REVIEW → PROFILE / GRAPH / TIMELINE / REPORT
```

## Quick start

### Production-style (Docker)

```bash
cp .env.example .env          # set OSINT_DB_PASSWORD and OSINT_OPERATOR_CONTACT
docker compose up -d --build
# open http://localhost:8080 — the first account you create becomes the administrator
```

Four services: `db` (PostgreSQL 16), `api` (FastAPI, applies migrations on start), `worker`
(investigation queue, monitoring, retention) and `web` (nginx serving the console and proxying
`/api` on the same origin).

### Local development

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8000
```

Development uses SQLite and runs the worker inside the API process.

## Highlights

- **36 sources, one honest status model** — every source reports **Found, Not found, Not verified,
  Error, Rate limited** or **Requires auth**; errors never masquerade as "not found".
- **Provenance on every fact** — each claim is an `Observation(entity, attribute, value, source,
  confidence, observed_at)` backed by a stored retrieval with URL, time and reliability. Re-runs
  append, so first/last-seen accumulates.
- **Explainable entity resolution** — scoring factors you can audit (exact handle, verified links,
  mutual links, shared email/website), identity clusters so shared handles don't blend people, and
  analyst confirm/reject verdicts that override the score and land in the audit log.
- **Analyst workflow** — notes, tags, scheduled re-runs (daily/weekly/monthly), per-investigation
  access log, and exports: printable HTML report, full JSON with provenance, CSV datasets
  (formula-injection safe).
- **Hardened by default** — scrypt passwords, server-side sessions, CSRF headers, login rate
  limiting, SSRF-guarded outbound requests, strict CSP, proxied images, automatic retention.
- **Ships as a stack** — Docker Compose with healthchecks, Alembic migrations, structured JSON
  logs with request IDs, `/healthz` and `/readyz`.

## Boundaries

Observations are not truth: the console records what sources *said*, with confidence, never what it
wishes were true. Platforms without legitimate public access (**Instagram, LinkedIn**) are reported
**Not verified**, never scraped. No login/CAPTCHA/robots bypass, no breach or credential data, no
mailbox probing, no port scanning, no registrant contacts.

Details: [security & boundaries](docs/explanation/security-and-boundaries.md)

## Documentation

| Guide | Type | For |
|---|---|---|
| [Getting started](docs/getting-started.md) | Tutorial | First run → first investigation |
| [Add a source](docs/how-to/add-a-source.md) | How-to | Contributors extending connectors |
| [Deploy & operate](docs/how-to/deploy.md) | How-to | Running it beyond localhost |
| [Source catalog](docs/reference/sources.md) | Reference | What each of the 36 sources does |
| [Configuration](docs/reference/configuration.md) | Reference | Every `OSINT_*` environment variable |
| [How conclusions are reached](docs/explanation/entity-resolution.md) | Explanation | Scoring, clusters, confidence math |
| [Security & boundaries](docs/explanation/security-and-boundaries.md) | Explanation | Protections and collection ethics |

## Tests

```bash
cd backend && uv run pytest                                   # 102 tests, SQLite
OSINT_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest  # same suite on PostgreSQL
uv run python -m scripts.smoke_connectors                     # live check of every connector
cd frontend && npm test && npm run build                      # 18 tests + typecheck + build
```

CI runs the backend suite on SQLite **and** PostgreSQL, migrations up/down/up, the frontend
typecheck/tests/build, and boots the full Docker stack on every push.

## Extending

Adding a source takes about an afternoon: subclass `Connector`, implement `fetch`/`normalize`,
register it, add a fixture test. See [Add a source](docs/how-to/add-a-source.md).
