"""Hacker News — official Firebase API for profiles, Algolia HN Search API for activity/mentions."""

import re
from typing import Any
from urllib.parse import quote

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import (
    Connector, ConnectorContext, ConnectorResult, Findings, check_status, domain_of_seed,
)
from app.connectors.social import parse_social_url
from app.core.classify import Classification
from app.core.enums import EventKind, Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import html_to_text, parse_datetime

FIREBASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA = "https://hn.algolia.com/api/v1"
ITEM_URL = "https://news.ycombinator.com/item?id={}"
URL_RE = re.compile(r"https?://[^\s<>\"')]+")
MAX_HITS = 20


def _hit_title(hit: dict[str, Any]) -> str:
    if hit.get("title"):
        return hit["title"]
    if hit.get("story_title"):
        return f"Comment on: {hit['story_title']}"
    return "Hacker News item"


class HackerNewsConnector(Connector):
    name = "hackernews"
    label = "Hacker News"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Public Hacker News profile (official API) and recent submissions/comments (Algolia HN API)."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://news.ycombinator.com/user?id={quote(target)}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        resp = await ctx.http.get(f"{FIREBASE}/user/{quote(target)}.json")
        check_status(resp, self.label)
        user = resp.json()
        if not user:
            return {"user": None, "hits": []}
        hits: list[dict[str, Any]] = []
        activity = await ctx.http.get(
            f"{ALGOLIA}/search_by_date", params={"tags": f"author_{user['id']}", "hitsPerPage": MAX_HITS}
        )
        if activity.status_code == 200:
            hits = activity.json().get("hits", [])
        return {"user": user, "hits": hits, "activity_url": str(activity.url)}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        user = raw.get("user")
        if not user:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Hacker News user with this exact (case-sensitive) name.")
        about = html_to_text(user.get("about"))
        urls = URL_RE.findall(about)
        linked = [s for u in urls if (s := parse_social_url(u))]
        websites = [u for u in urls if not parse_social_url(u)]
        profile = PublicProfile(
            platform="hackernews",
            username=user["id"],
            url=f"https://news.ycombinator.com/user?id={quote(user['id'])}",
            bio=about or None,
            website=websites[0] if websites else None,
            created_at=parse_datetime(user.get("created")),
            linked_accounts=linked,
            stats={"karma": user.get("karma")},
        )
        ref, _ = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                              source_url=f"{FIREBASE}/user/{quote(user['id'])}.json")
        if raw.get("hits"):
            src = f.source(name=self.label, category=SourceCategory.SOCIAL, kind="api_activity",
                           url=raw["activity_url"], reliability=self.reliability,
                           title=f"Recent Hacker News activity by {user['id']}")
            for hit in raw["hits"]:
                published = parse_datetime(hit.get("created_at_i") or hit.get("created_at"))
                title = _hit_title(hit)
                f.mention(
                    url=ITEM_URL.format(hit["objectID"]), title=title,
                    snippet=html_to_text(hit.get("comment_text")) or hit.get("url"),
                    category=SourceCategory.SOCIAL, association="Authored by profile",
                    source=src, confidence=0.95, entity=ref, published_at=published,
                )
                f.event(EventKind.MENTION, f"Hacker News: {title}", published, src, entity=ref)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(*websites[:1]))


class HackerNewsSearchConnector(Connector):
    """Full-text mentions. A text match is NOT identity evidence, so confidence stays low."""

    name = "hn_search"
    label = "Hacker News search"
    category = SourceCategory.NEWS
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.USERNAME, SeedType.PERSON, SeedType.DOMAIN, SeedType.URL})
    description = "Public stories and comments mentioning the identifier (Algolia HN Search API)."

    def targets(self, seed: Classification) -> list[str]:
        if seed.type in (SeedType.DOMAIN, SeedType.URL):
            domain = domain_of_seed(seed)
            return [domain] if domain else []
        return super().targets(seed)

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        params: dict[str, Any] = {"query": f'"{target}"', "hitsPerPage": MAX_HITS, "tags": "(story,comment)"}
        if seed_type in (SeedType.DOMAIN, SeedType.URL):
            params = {"query": target, "hitsPerPage": MAX_HITS, "restrictSearchableAttributes": "url", "tags": "story"}
        resp = await ctx.http.get(f"{ALGOLIA}/search", params=params)
        check_status(resp, self.label)
        return {"hits": resp.json().get("hits", []), "url": str(resp.url)}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        hits = raw.get("hits", [])
        if not hits:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Hacker News stories or comments mention this.")
        src = f.source(name="Hacker News", category=self.category, kind="api_search", url=raw["url"],
                       reliability=self.reliability, title=f'Hacker News search for "{target}"')
        is_domain = seed_type in (SeedType.DOMAIN, SeedType.URL)
        for hit in hits:
            published = parse_datetime(hit.get("created_at_i") or hit.get("created_at"))
            f.mention(
                url=ITEM_URL.format(hit["objectID"]), title=_hit_title(hit),
                snippet=html_to_text(hit.get("comment_text") or hit.get("story_text")) or hit.get("url"),
                category=SourceCategory.NEWS,
                association="Links to domain" if is_domain else "Text match (unverified)",
                source=src, confidence=0.7 if is_domain else 0.25, published_at=published,
            )
        return ConnectorResult(RunStatus.FOUND, f)
