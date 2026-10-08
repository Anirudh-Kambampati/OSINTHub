"""DEV (dev.to) — official public Forem API."""

from datetime import UTC, datetime
from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.core.enums import EventKind, Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

API = "https://dev.to/api"


def _parse_joined(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%b %d, %Y").replace(tzinfo=UTC)
    except ValueError:
        return parse_datetime(value)


class DevToConnector(Connector):
    name = "devto"
    label = "DEV"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Public DEV community profiles and articles via the official API."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://dev.to/{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(f"{API}/users/by_username", params={"url": target})
        if not check_status(resp, self.label):
            return None
        user = resp.json()
        articles: list[dict[str, Any]] = []
        a = await ctx.http.get(f"{API}/articles", params={"username": user["username"], "per_page": 10})
        if a.status_code == 200:
            articles = a.json()
        return {"user": user, "articles": articles, "articles_url": str(a.url)}

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No DEV account with this username.")
        u = raw["user"]
        linked = []
        if u.get("twitter_username"):
            linked.append(f"x:{u['twitter_username']}")
        if u.get("github_username"):
            linked.append(f"github:{u['github_username']}")
        profile = PublicProfile(
            platform="devto",
            username=u["username"],
            url=f"https://dev.to/{u['username']}",
            name=u.get("name"),
            bio=u.get("summary"),
            location=u.get("location"),
            website=u.get("website_url") or None,
            avatar=u.get("profile_image"),
            created_at=_parse_joined(u.get("joined_at")),
            linked_accounts=linked,
        )
        ref, _ = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                              source_url=f"{API}/users/by_username?url={u['username']}")
        if raw.get("articles"):
            src = f.source(name=self.label, category=self.category, kind="api_articles", url=raw["articles_url"],
                           reliability=self.reliability, title=f"Articles by @{u['username']} on DEV")
            for art in raw["articles"]:
                published = parse_datetime(art.get("published_at"))
                f.mention(url=art["url"], title=art["title"], snippet=art.get("description"),
                          category=SourceCategory.SOCIAL, association="Authored by profile", source=src,
                          confidence=0.95, entity=ref, published_at=published)
                f.event(EventKind.MENTION, f"Published on DEV: {art['title']}", published, src, entity=ref)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(profile.website))
