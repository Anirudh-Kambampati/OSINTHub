# Source catalog

What each of the 36 sources can answer, how it is accessed, and what it needs from you.

## Areas

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

\* needs a server-side key — see [Configuration](configuration.md). Wikidata requires
`OSINT_OPERATOR_CONTACT` (Wikimedia's robot policy).

## Statuses

Every source reports exactly one of these per run. The distinction is deliberate: **errors never
masquerade as "not found"**, so an investigator can tell "no such account" apart from "we could not
ask".

| Status | Meaning |
|---|---|
| **Found** | The source answered with data |
| **Not found** | The source was reached and definitively has no such record |
| **Not verified** | No legitimate query method exists for this platform (policy) |
| **Error** | The source failed or misbehaved — not evidence of absence |
| **Rate limited** | Quota exhausted (e.g. GitHub's 60 req/hour anonymous); re-run later |
| **Requires auth** | The connector needs an API key you have not configured |

A partial investigation (some Error / Rate limited) is marked as such rather than presented as
complete.

## Notes by area

- **GitHub without a token** allows 60 requests/hour — set `OSINT_GITHUB_TOKEN` for real
  investigations (5000/hour).
- **Email seeds** never probe mailboxes: only provider classification and public DNS records
  (MX/SPF/DMARC).
- **RDAP** lookups exclude registrant contact details.
- **Website fetches** honour `robots.txt`, cap response sizes, and follow no login flows; images
  are proxied so the analyst's browser never contacts third-party platforms directly.
- **Shodan InternetDB** is a passive IP index, not port scanning.
- **Instagram / LinkedIn** ship as registered stubs so the UI can explain *why* they are always
  **Not verified** and hand the analyst a manual profile URL.

The Settings page shows which sources are active in your deployment.
