"""Live smoke test: run every connector against a known public target and report its status.

    uv run python -m scripts.smoke_connectors            # all connectors
    uv run python -m scripts.smoke_connectors github npm  # a subset

Hits real public APIs. Expect a few transient errors from flaky upstreams (crt.sh, archive.org).
"""

import asyncio
import sys
import time

import httpx

from app.config import get_settings
from app.connectors.base import ConnectorContext, ConnectorError
from app.connectors.registry import CONNECTORS
from app.core.enums import SeedType
from app.core.net import HostLimiter, SourceHttp

# Known public test subjects: platform mascots, project accounts, fictitious test identities,
# reserved domains, or prominent public figures with encyclopedic entries.
TARGETS: dict[str, tuple[str, SeedType]] = {
    "github": ("octocat", SeedType.USERNAME),
    "gitlab": ("gitlab-bot", SeedType.USERNAME),
    "hackernews": ("pg", SeedType.USERNAME),
    "devto": ("ben", SeedType.USERNAME),
    "keybase": ("chris", SeedType.USERNAME),
    "bluesky": ("bsky.app", SeedType.USERNAME),
    "medium": ("ev", SeedType.USERNAME),
    "mastodon": ("Gargron", SeedType.USERNAME),
    "codeberg": ("forgejo", SeedType.USERNAME),
    "huggingface": ("julien-c", SeedType.USERNAME),
    "npm": ("sindresorhus", SeedType.USERNAME),
    "cratesio": ("dtolnay", SeedType.USERNAME),
    "dockerhub": ("bitnami", SeedType.USERNAME),
    "stackoverflow": ("Jon Skeet", SeedType.PERSON),
    "codewars": ("jhoffner", SeedType.USERNAME),
    "chesscom": ("hikaru", SeedType.USERNAME),
    "lichess": ("DrNykterstein", SeedType.USERNAME),
    "orcid": ("Josiah Carberry", SeedType.PERSON),
    "wikidata": ("Ada Lovelace", SeedType.PERSON),
    "reddit": ("spez", SeedType.USERNAME),
    "x": ("jack", SeedType.USERNAME),
    "youtube": ("YouTube", SeedType.USERNAME),
    "instagram": ("instagram", SeedType.USERNAME),
    "linkedin": ("williamhgates", SeedType.USERNAME),
    "gravatar": ("beau@dentedreality.com.au", SeedType.EMAIL),
    "email_intel": ("octocat@github.com", SeedType.EMAIL),
    "hn_search": ("octocat", SeedType.USERNAME),
    "web_search": ("octocat", SeedType.USERNAME),
    "website": ("https://example.com/", SeedType.URL),
    "dns": ("example.com", SeedType.DOMAIN),
    "rdap": ("example.com", SeedType.DOMAIN),
    "certificates": ("example.com", SeedType.DOMAIN),
    "wayback": ("example.com", SeedType.DOMAIN),
    "security_txt": ("google.com", SeedType.DOMAIN),
    "ip_intel": ("1.1.1.1", SeedType.URL),
    "documents": ("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", SeedType.URL),
}


async def run_one(name: str, client: httpx.AsyncClient, limiter: HostLimiter) -> tuple[str, str, str, float]:
    connector = CONNECTORS[name]
    target, seed_type = TARGETS[name]
    ctx = ConnectorContext(SourceHttp(client, get_settings(), limiter, name, []), get_settings())
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(connector.run(target, seed_type, ctx),
                                        timeout=connector.timeout or get_settings().connector_timeout)
        f = result.findings
        detail = (f"{len({r for r in f.entities if r.kind == 'profile'})} profiles, {len(f.observations)} obs, "
                  f"{len(f.mentions)} mentions, {len(f.events)} events") if not f.is_empty else (result.message or "")
        status = result.status.value
    except ConnectorError as exc:
        status, detail = exc.status.value, str(exc)
    except Exception as exc:  # noqa: BLE001
        status, detail = "error", f"{type(exc).__name__}: {exc}"
    return name, status, detail[:110], time.perf_counter() - start


async def main(names: list[str]) -> None:
    async with httpx.AsyncClient(follow_redirects=False) as client:
        limiter = HostLimiter()
        results = await asyncio.gather(*(run_one(n, client, limiter) for n in names))
    for name, status, detail, secs in results:
        print(f"{name:14} {status:14} {secs:5.1f}s  {detail}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or list(TARGETS)))
