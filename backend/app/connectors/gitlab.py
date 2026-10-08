"""GitLab.com — official public REST API (v4)."""

from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.connectors.social import parse_social_url
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

API = "https://gitlab.com/api/v4"


class GitLabConnector(Connector):
    name = "gitlab"
    label = "GitLab"
    category = SourceCategory.CODE
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Public GitLab.com user profiles via the official REST API."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://gitlab.com/{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(f"{API}/users", params={"username": target})
        check_status(resp, self.label)
        matches = resp.json()
        if not matches:
            return None
        user = matches[0]
        detail = await ctx.http.get(f"{API}/users/{user['id']}")
        if detail.status_code == 200:
            user = {**user, **detail.json()}
        return user

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw or raw.get("state") == "blocked":
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public GitLab account with this username.")
        linked = []
        if raw.get("twitter"):
            linked.append(f"x:{raw['twitter']}")
        if raw.get("linkedin"):
            linked.append(parse_social_url(raw["linkedin"]) or f"linkedin:{raw['linkedin']}")
        if raw.get("github"):
            linked.append(f"github:{raw['github']}")
        website = raw.get("website_url") or None
        profile = PublicProfile(
            platform="gitlab",
            username=raw["username"],
            url=raw.get("web_url") or f"https://gitlab.com/{raw['username']}",
            name=raw.get("name"),
            bio=raw.get("bio"),
            location=raw.get("location"),
            website=website,
            email=raw.get("public_email") or None,
            organization=raw.get("organization") or None,
            occupation=raw.get("job_title") or None,
            avatar=raw.get("avatar_url"),
            created_at=parse_datetime(raw.get("created_at")),
            linked_accounts=linked,
        )
        emit_profile(f, profile, category=self.category, reliability=self.reliability,
                     source_url=f"{API}/users/{raw['id']}")
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(website))
