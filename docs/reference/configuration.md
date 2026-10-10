# Configuration

Complete reference for `OSINT_*` environment variables. All settings are read **server-side only**
(Pydantic `BaseSettings`, prefix `OSINT_`, optional `.env` file; unknown names are ignored). Secrets
never reach the browser.

- Local development: copy `backend/.env.example` → `backend/.env`
- Docker Compose: copy the root `.env.example` → `.env`

## Core

| Variable | Default | Purpose |
|---|---|---|
| `OSINT_ENVIRONMENT` | `development` | `production` enables Secure cookies and disables the interactive API docs |
| `OSINT_DATABASE_URL` | `sqlite+aiosqlite:///./osint.db` | SQLAlchemy URL; compose sets PostgreSQL |
| `OSINT_LOG_JSON` | `false` | Structured JSON logs with request IDs |
| `OSINT_CORS_ORIGINS` | `http://localhost:5173` (list) | Allowed browser origins; compose sets `[]` (same-origin only) |
| `OSINT_OPERATOR_CONTACT` | — | Email or URL in the User-Agent. **Required by Wikidata** |

## Accounts & sessions

| Variable | Default | Purpose |
|---|---|---|
| `OSINT_ALLOW_REGISTRATION` | `false` | Open signup; first account is always admin regardless |
| `OSINT_SESSION_TTL_HOURS` | `72` | Session lifetime |
| `OSINT_COOKIE_SECURE` | `true` in production | Force `Secure` cookies (set `false` only for deliberate HTTP setups) |
| `OSINT_LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Per-process login throttle |
| `OSINT_CREATE_RATE_LIMIT_PER_MINUTE` | `10` | Per-process investigation-creation throttle |

## Worker & queue

| Variable | Default | Purpose |
|---|---|---|
| `OSINT_RUN_WORKER_IN_API` | `true` | Run investigations inside the API process (single node). Compose sets `false` — worker runs separately |
| `OSINT_MAX_CONCURRENT_INVESTIGATIONS` | `4` | Worker concurrency |
| `OSINT_RETENTION_DAYS` | unset (keep) | The worker deletes investigations older than N days |

(Worker internals: `OSINT_WORKER_POLL_SECONDS=2.0`,
`OSINT_WORKER_HEARTBEAT_TIMEOUT_SECONDS=300` — stale work is requeued.)

## HTTP & collection limits

| Variable | Default | Purpose |
|---|---|---|
| `OSINT_HTTP_TIMEOUT` | `12.0` | Outbound request timeout (seconds) |
| `OSINT_CONNECTOR_TIMEOUT` | `30.0` | Whole-connector budget |
| `OSINT_MAX_HTML_BYTES` | `2000000` | Response cap for HTML |
| `OSINT_MAX_DOCUMENT_BYTES` | `10000000` | Linked-document cap (metadata only) |
| `OSINT_MAX_IMAGE_BYTES` | `3000000` | Proxied-image cap |
| `OSINT_MAX_PIVOT_WEBSITES` | `3` | Websites followed per investigation |
| `OSINT_MAX_PIVOT_IPS` | `3` | IP pivots per investigation |
| `OSINT_MAX_DOCUMENTS` | `3` | Document pivots per investigation |

## API keys (optional sources stay "Requires auth" without them)

| Variable | Unlocks |
|---|---|
| `OSINT_GITHUB_TOKEN` | GitHub rate limit 60/h → 5000/h |
| `OSINT_REDDIT_CLIENT_ID` + `OSINT_REDDIT_CLIENT_SECRET` | Reddit (app-only OAuth; reddit.com/prefs/apps) |
| `OSINT_YOUTUBE_API_KEY` | YouTube Data API v3 |
| `OSINT_X_BEARER_TOKEN` | X API v2 |
| `OSINT_BRAVE_SEARCH_API_KEY` | Brave web search |

## Compose-only variables (root `.env`)

| Variable | Purpose |
|---|---|
| `OSINT_DB_PASSWORD` | PostgreSQL password (DB + API connection string) |
| `OSINT_HTTP_PORT` | Host port for the console (default `8080`) |

## Testing

| Variable | Purpose |
|---|---|
| `OSINT_TEST_DATABASE_URL` | Run the pytest suite against PostgreSQL instead of SQLite |
