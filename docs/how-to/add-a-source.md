# Add a source

A recipe for contributors: add a legitimate public source to OSINThub in about an afternoon.

## Before you start

A source belongs here only if it is **publicly and legitimately queryable**: an official API, or
public endpoints that permit automated access. If the platform requires login, CAPTCHAs, or
prohibits automated access, the correct implementation is a `PolicyRestrictedConnector` stub that
always reports **Not verified** (see `InstagramConnector` in
`backend/app/connectors/authenticated.py`) — never a scraper.

## 1. Create the connector

Create `backend/app/connectors/<name>.py` and subclass one of:

| Base | Use when |
|---|---|
| `Connector` (`base.py`) | General case — you control `fetch` and `normalize` |
| `JsonProfileConnector` (`platforms.py`) | Simple profile APIs: declarative fields, URLs, stats |
| `PolicyRestrictedConnector` (`authenticated.py`) | No legitimate lookup exists — always Not verified |

Minimal shape:

```python
class ExampleConnector(Connector):
    name = "example"                 # unique id, stable across renames
    label = "Example"                # display name
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})

    async def fetch(self, target, seed_type, ctx) -> dict | None:
        # All network I/O goes through ctx.http (SSRF guard, size caps,
        # per-host concurrency, retries, operator User-Agent).
        resp = await ctx.http.get(f"https://api.example.com/users/{quote(target)}")
        check_status(resp, self.label)      # maps HTTP status to honest RunStatus
        return resp.json() if resp.ok else None

    def normalize(self, raw, target, seed_type) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No such account.")
        # fill f: f.source(...) then emit_profile / f.mention / f.event ...
        return ConnectorResult(RunStatus.FOUND, f)
```

Rules that keep the system honest:

- **`normalize` must be pure** — no network, deterministic; it turns stored raw data into findings.
  This is what makes fixtures testable.
- **Status discipline** — Found, Not found, Not verified, Error, Rate limited, Requires auth.
  Never report Error as Not found.
- If credentials are needed, declare them: `requires = ("some_api_key",)` and add a
  `SecretStr | None` field to `Settings` in `backend/app/config.py`.

## 2. Use the helpers for profiles

`emit_profile(f, profile, ...)` from `connectors/_profile.py` stores a `PublicProfile` as a
profile entity plus observations; `website_pivots(url)` returns pivot suggestions for linked
websites. Keybase-style verified links, Mastodon-verified fields, etc. should flow into
`linked_accounts` — they carry extra resolution weight (see
[How conclusions are reached](../explanation/entity-resolution.md)).

## 3. Register it

Add the connector to `backend/app/connectors/registry.py` — import the class and add
`ExampleConnector(),` to the list. The Settings page and investigations pick it up automatically.

## 4. Add a fixture test

Create a test in `backend/tests/` following `test_connectors_new.py`: store realistic raw JSON as
a fixture and assert on `normalize` output — status, entity keys, findings, links. This is why
`normalize` is pure.

## 5. Add a smoke target

Add an entry to `scripts/smoke_connectors.py` mapping your connector name to a known-good seed:

```python
"example": ("some_real_handle", SeedType.USERNAME),
```

Live checks run with:

```bash
uv run python -m scripts.smoke_connectors
```

## 6. Run the checks

```bash
uv run pytest                          # full backend suite
cd ../frontend && npm test             # if you touched shared contracts
```

CI repeats this on SQLite and PostgreSQL and boots the whole stack — a green pipeline means the
source is integrated end to end.
