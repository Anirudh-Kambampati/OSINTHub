# OSINThub

**An evidence-backed OSINT investigation console.**

Give it a username, email, name, domain or URL. OSINThub checks **36 public sources**, turns
what they say into **observations with provenance**, links profiles that belong to the same
person or organization, and hands you a profile, identity graph, timeline and exportable
report — **every fact links back to the source that stated it**.

[![CI](https://github.com/Anirudh-Kambampati/OSINTHub/actions/workflows/ci.yml/badge.svg)](https://github.com/Anirudh-Kambampati/OSINTHub/actions/workflows/ci.yml)

```
search → classify → queue → connectors → observations
       → entity resolution → analyst review → profile / graph / timeline / report
```

## What it's for

- **Investigating an online identity** — pivot from one handle or email to every public
  profile, website and document that mentions it, with first/last-seen timestamps.
- **Building an evidence trail** — each observation stores its source, URL, retrieval time and
  confidence, so a conclusion can always be defended.
- **Team review** — notes, tags, scheduled re-runs, per-investigation access logs, and exports
  (printable HTML report, full JSON, formula-injection-safe CSV).
- **Safe by design** — no login/CAPTCHA/robots bypass, no breach data, no mailbox probing.
  Instagram and LinkedIn are reported *Not verified*, never scraped. Details:
  [security & boundaries](docs/explanation/security-and-boundaries.md).

## Run it

### Docker (production-style)

```bash
cp .env.example .env          # set OSINT_DB_PASSWORD and OSINT_OPERATOR_CONTACT
docker compose up -d --build
# open http://localhost:8080 — the first account you create becomes the administrator
```

### Local development

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8000
```

Development uses SQLite and runs the worker inside the API process.

## Applications in the stack

| Service | Built with | Role |
|---|---|---|
| `web` | nginx + React (Vite) | Serves the console and proxies `/api` on the same origin |
| `api` | FastAPI (Python) | REST API, auth, applies Alembic migrations on start |
| `worker` | Python | Runs the investigation queue, monitoring and retention |
| `db` | PostgreSQL 16 | Stores investigations, observations and the audit log |

Locally these collapse into two processes: the FastAPI server (API + worker) and the Vite dev
server.

## Tests

```bash
cd backend && uv run pytest          # backend suite on SQLite
cd frontend && npm test && npm run build   # tests + typecheck + build
```

## Documentation

| Guide | For |
|---|---|
| [Getting started](docs/getting-started.md) | First run → first investigation |
| [Add a source](docs/how-to/add-a-source.md) | Extending connectors |
| [Deploy & operate](docs/how-to/deploy.md) | Running it beyond localhost |
| [Source catalog](docs/reference/sources.md) | What each of the 36 sources does |
| [Configuration](docs/reference/configuration.md) | Every `OSINT_*` environment variable |
| [Entity resolution](docs/explanation/entity-resolution.md) | How conclusions are reached |
| [Security & boundaries](docs/explanation/security-and-boundaries.md) | Protections and collection ethics |
