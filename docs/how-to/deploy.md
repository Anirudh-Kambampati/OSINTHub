# Deploy & operate

A recipe for running OSINThub beyond localhost.

## The stack

```bash
cp .env.example .env      # OSINT_DB_PASSWORD, OSINT_OPERATOR_CONTACT, optional API keys
docker compose up -d --build
```

| Service | Notes |
|---|---|
| `db` | PostgreSQL 16, volume `pgdata`, healthcheck `pg_isready` |
| `api` | FastAPI; applies migrations on start; `OSINT_RUN_WORKER_IN_API=false` |
| `worker` | `python -m app.worker`; depends on a healthy `api`; scale freely |
| `web` | nginx on `${OSINT_HTTP_PORT:-8080}`; proxies `/api` same-origin |

Images restart automatically (`restart: unless-stopped`). The root `.env` is read if present
(`required: false` — the stack still boots with defaults for local experiments).

## Put TLS in front

nginx serves plain HTTP. For anything beyond localhost, place a TLS-terminating reverse proxy in
front of `web` (Caddy, Traefik, nginx, a cloud load balator). Two reasons:

1. Session cookies become `Secure` in production — browsers only send them over HTTPS on
   non-localhost hosts.
2. `OSINT_COOKIE_SECURE` defaults to true when `OSINT_ENVIRONMENT=production`; set it to `false`
   only for deliberate HTTP-only setups (localhost is fine with `true`).

## Configure

All settings are `OSINT_*` environment variables — full table in
[Configuration](../reference/configuration.md). Minimum for production:

```bash
OSINT_DB_PASSWORD=<long random>       # compose-only; DB + API connection string
OSINT_OPERATOR_CONTACT=<email or URL> # sent in the User-Agent; required by Wikidata
OSINT_ENVIRONMENT=production          # Secure cookies, strict checks, no API docs
```

API keys (GitHub, Reddit, YouTube, X, Brave) unlock the credentialed sources; without them those
sources report **Requires auth**. Sources page in Settings shows what is active.

## Scale workers

Pending investigations are **claimed atomically** from the database; workers heartbeat and stale
work is requeued, so restarts never lose cases. On PostgreSQL, scale horizontally:

```bash
docker compose up -d --scale worker=4
```

SQLite deployments should keep a single worker (dev default: the worker runs inside the API
process via `OSINT_RUN_WORKER_IN_API=true`).

## Health & logs

- `GET /healthz` — process liveness; `GET /readyz` — database readiness (503 when down)
- `OSINT_LOG_JSON=true` — structured JSON logs with request IDs; each API request logs
  method, path, status and duration, with secrets redacted
- The `web` container answers `GET /healthz` with its own `ok` for load balancers

## Retention & storage

```bash
OSINT_RETENTION_DAYS=180    # the worker deletes investigations older than N days; unset = keep
```

Individual cases can be deleted from the UI at any time.

## Rate limiting beyond one node

Login and create rate limits are **per API process**. If you run multiple API replicas, enforce a
limiter at the proxy layer as well.

## Upgrades

```bash
git pull
docker compose up -d --build
```

Migrations run automatically on API start. They are reversible — CI proves
`upgrade head → downgrade base → upgrade head` on every push.
