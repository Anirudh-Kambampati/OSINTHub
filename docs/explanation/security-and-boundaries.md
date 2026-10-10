# Security & boundaries

Why OSINThub is built to refuse certain things — and what it does instead.

## The principle

Legitimate public information, collected through permitted channels, with provenance — so that
every finding you export is **defensible**. A tool that bypasses access controls produces leads
that collapse under scrutiny and expose the operator to ToS and legal risk. The boundary is
therefore a feature, documented so investigators can rely on it.

## What is never collected

- **No login, CAPTCHA or robots.txt bypass** — if a platform requires authentication for
  automated access, the connector stops and reports honestly.
- **No scraping of platforms without legitimate public access** — Instagram and LinkedIn ship as
  registered *policy-restricted* stubs: always **Not verified**, plus a manual profile URL for the
  analyst to review with their own logged-in browser.
- **No breach or credential data**, ever.
- **No mailbox probing** — email intelligence is provider classification plus public DNS
  (MX/SPF/DMARC) only.
- **No phone-number extraction**.
- **No registrant contacts** from RDAP/WHOIS.
- **No document body parsing** — linked PDFs yield metadata only.
- **No port scanning** — Shodan InternetDB is a passive index lookup.

## Account security

- **scrypt-hashed** passwords; server-side sessions in HttpOnly `SameSite` cookies (`Secure` in
  production)
- **CSRF header** (`X-OSINT-CSRF`) required on every state-changing request — browsers cannot add
  it cross-site without a CORS preflight the policy rejects
- **Login rate limiting** with timing-safe failure paths
- **Roles**: admin/analyst; **per-user investigation isolation** — non-owners get 404, not 403, so
  existence is not leaked
- **Audit log**: logins, investigation lifecycle and analyst decisions

## Outbound requests

Every hop passes an **SSRF guard**: public IPs only, ports 80/443 only, no credentials embedded in
URLs; credentials are stripped on cross-host redirects. On top of that: response size caps
(`OSINT_MAX_HTML_BYTES` etc.), per-host concurrency limits, one retry on transient 5xx —
**never** on 429 — and the operator contact in the User-Agent so sources can reach a human.
Secrets are redacted from access logs.

## Rendering

- External text is reduced to plain text **server-side** before it reaches the browser
- Links only for `http(s)` schemes
- Strict **Content-Security-Policy** set by nginx; the console's CSP allows only self-hosted
  scripts, with `frame-ancestors 'none'` and `form-action 'self'`
- Exported reports are served with `default-src 'none'` — an opened report executes nothing
- **Images are proxied**: the analyst's browser never contacts third-party platforms directly
  (no IP leakage to sources from mere viewing)

## Retention

`OSINT_RETENTION_DAYS` makes the worker delete old investigations automatically; individual cases
can be deleted from the UI at any time. A single-node check of the access log gives you the full
picture of who looked at what.

## Operations posture

- Queue claims are atomic with heartbeats — crashes and restarts lose no work
- `/healthz` (process) and `/readyz` (database) for orchestration
- Structured logs with request IDs; secrets never logged
- CI proves migrations reverse cleanly and boots the whole stack on every push

## When a source you want is missing

If a platform you need is restricted here, the supported path is **manual follow-up** via the
`manual_url` the stub provides, or an **official API for accounts you own** (e.g. Meta's Graph API
for your own business profiles). Requesting a scraper would be requesting a boundary removal —
that is a deliberate product decision, not a TODO.
