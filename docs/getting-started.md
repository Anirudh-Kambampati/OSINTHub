# Getting started

A tutorial: by the end you will have OSINThub running, an administrator account, and your first
investigation with a provenance-backed profile.

## What you need

- **Docker** with Compose (recommended), *or* `uv` (Python 3.12) + Node 20 for local development
- About 5 minutes

## 1. Start the stack

```bash
cp .env.example .env
# Edit .env: set OSINT_DB_PASSWORD to a long random string and
# OSINT_OPERATOR_CONTACT to an email or URL — Wikimedia requires it for Wikidata.
docker compose up -d --build
```

Wait for the services to report healthy:

```bash
docker compose ps
```

| Service | Role |
|---|---|
| `db` | PostgreSQL 16 |
| `api` | FastAPI — applies Alembic migrations on start |
| `worker` | Claims queued investigations, runs monitoring and retention |
| `web` | nginx on port **8080** — serves the console, proxies `/api` same-origin |

Open **http://localhost:8080**.

## 2. Create the administrator

The first visit shows account setup: the **first account you create becomes the administrator**.
Afterwards, registration closes (`OSINT_ALLOW_REGISTRATION=false`) and admins create further users
with admin or analyst roles.

Every login is recorded in the audit log alongside investigation activity.

## 3. Start an investigation

From the home page, enter a seed. Supported seeds: **username, email, name, domain or URL**.

What happens next (visible in the investigation view):

1. The seed is **classified** and written to the durable job queue.
2. The **worker** claims it atomically and fans out to every applicable connector — 36 sources,
   each independently reporting Found / Not found / Not verified / Error / Rate limited /
   Requires auth.
3. Discovered websites, IPs and linked documents become **pivots** (bounded by
   `OSINT_MAX_PIVOT_WEBSITES` / `OSINT_MAX_PIVOT_IPS` / `OSINT_MAX_DOCUMENTS`).
4. Everything lands as **observations with provenance**; entity resolution then clusters the
   discovered profiles into identities.

Free public APIs rate-limit (GitHub allows 60 requests/hour anonymously — set
`OSINT_GITHUB_TOKEN`). Affected sources show **Rate limited** and the investigation is marked
partial; re-run later.

## 4. Read the results

- **Overview** — the profile: attributes with confidence, each one clickable through to an
  *evidence drawer* answering **"why does the system believe this?"** — source, URL, time,
  reliability.
- **Graph** — relationship view of resolved identities and the profiles tied to them.
- **Sources** — which of the 36 sources answered what, and how. The Settings page shows which
  sources are active versus "Requires auth" (add keys per
  [Configuration](reference/configuration.md)).
- **Mentions / timeline** — discovered posts and documents, ordered in time.

Weak values display rounded (`~35%`) — treat them as leads, not findings.

## 5. Make an analyst decision

For any profile: **confirm** or **reject**. The verdict overrides the resolution score, triggers
re-resolution, and is written to the audit log — the score never silently overrules a human.

Add notes and tags to the case, and schedule **monitoring** re-runs (daily/weekly/monthly) to see
what is *new since the last run*.

## 6. Export

From the investigation: a printable **HTML report** (print to PDF), a **JSON** export with full
provenance, or **CSV** datasets (attributes, profiles, mentions, observations, timeline, source
checks — formula-injection safe).

## Recap

You ran the stack, created the first admin, executed an investigation across 36 sources, audited a
claim down to its source, made an analyst decision, and exported the case.

## Where to go next

- [Deploy & operate](how-to/deploy.md) — TLS, scaling workers, retention
- [How conclusions are reached](explanation/entity-resolution.md) — what the scores mean
- [Source catalog](reference/sources.md) — what each source can and cannot answer
