"""Keybase — public user lookup API. Proofs are cryptographically verified account links."""

from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

API = "https://keybase.io/_/api/1.0/user/lookup.json"
PROOF_PLATFORMS = {"github": "github", "twitter": "x", "reddit": "reddit", "hackernews": "hackernews",
                   "mastodon": "mastodon", "bsky": "bluesky"}


class KeybaseConnector(Connector):
    name = "keybase"
    label = "Keybase"
    category = SourceCategory.IDENTITY
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Public Keybase identities and their cryptographically verified account proofs."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://keybase.io/{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(API, params={"usernames": target, "fields": "basics,profile,proofs_summary,pictures"})
        if not check_status(resp, self.label):
            return None
        body = resp.json()
        them = body.get("them") or []
        return them[0] if them and them[0] else None

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Keybase user with this username.")
        basics = raw.get("basics", {})
        prof = raw.get("profile") or {}
        verified: list[str] = []
        websites: list[str] = []
        for proof in (raw.get("proofs_summary") or {}).get("all", []):
            ptype = proof.get("proof_type")
            if ptype in PROOF_PLATFORMS:
                verified.append(f"{PROOF_PLATFORMS[ptype]}:{proof.get('nametag', '')}")
            elif ptype in ("generic_web_site", "dns") and proof.get("nametag"):
                websites.append(proof["nametag"])
        username = basics.get("username") or target
        profile = PublicProfile(
            platform="keybase",
            username=username,
            url=f"https://keybase.io/{username}",
            name=prof.get("full_name") or None,
            bio=prof.get("bio") or None,
            location=prof.get("location") or None,
            website=websites[0] if websites else None,
            avatar=((raw.get("pictures") or {}).get("primary") or {}).get("url"),
            created_at=parse_datetime(basics.get("ctime")),
            verified_accounts=verified,
        )
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                source_url=f"{API}?usernames={username}")
        for site in websites[1:]:
            f.observe(ref, "website", site, src, 0.95)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(*websites))
