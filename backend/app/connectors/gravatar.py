"""Gravatar — public profile keyed by the SHA-256 of an email address (official REST API v3)."""

import hashlib
from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.connectors.social import parse_social_url
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory

API = "https://api.gravatar.com/v3/profiles/{}"


class GravatarConnector(Connector):
    name = "gravatar"
    label = "Gravatar"
    category = SourceCategory.IDENTITY
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.EMAIL})
    description = "Public Gravatar profile associated with an email address."

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        digest = hashlib.sha256(target.strip().lower().encode()).hexdigest()
        resp = await ctx.http.get(API.format(digest))
        if not check_status(resp, self.label):
            return None
        return {"hash": digest, "profile": resp.json()}

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public Gravatar profile for this email.")
        p = raw["profile"]
        profile_url = p.get("profile_url") or f"https://gravatar.com/{raw['hash']}"
        username = profile_url.rstrip("/").rsplit("/", 1)[-1]
        accounts = [s for a in p.get("verified_accounts") or [] if (s := parse_social_url(a.get("url", "")))]
        links = [link.get("url") for link in p.get("links") or [] if link.get("url")]
        website = next((u for u in links if not parse_social_url(u)), None)
        profile = PublicProfile(
            platform="gravatar",
            username=username,
            url=profile_url,
            name=p.get("display_name") or None,
            bio=p.get("description") or None,
            location=p.get("location") or None,
            organization=p.get("company") or None,
            occupation=p.get("job_title") or None,
            website=website,
            avatar=p.get("avatar_url"),
            verified_accounts=accounts,
        )
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                source_url=API.format(raw["hash"]))
        # The profile was retrieved by this exact email's hash: strong email linkage.
        f.observe(ref, "email", target, src, 0.95)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(website))
