"""Platforms that only offer official, credentialed APIs. Without server-side credentials
they report REQUIRES_AUTHENTICATION — we never scrape around the requirement."""

from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import AuthRequired, Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.connectors.social import parse_social_url
from app.core.enums import EventKind, Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime


class RedditConnector(Connector):
    name = "reddit"
    label = "Reddit"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    requires = ("reddit_client_id", "reddit_client_secret")
    description = "Public Reddit user profiles via the official OAuth API (app-only credentials)."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://www.reddit.com/user/{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        s = ctx.settings
        token_resp = await ctx.http.request(
            "POST", "https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
            auth=(s.reddit_client_id.get_secret_value(), s.reddit_client_secret.get_secret_value()),
        )
        if token_resp.status_code != 200:
            raise AuthRequired("Reddit rejected the configured API credentials.")
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}
        about = await ctx.http.get(f"https://oauth.reddit.com/user/{target}/about", headers=headers)
        if not check_status(about, self.label):
            return None
        posts = await ctx.http.get(f"https://oauth.reddit.com/user/{target}/submitted", params={"limit": 10},
                                   headers=headers)
        return {"about": about.json().get("data", {}),
                "posts": posts.json().get("data", {}).get("children", []) if posts.status_code == 200 else []}

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw or raw["about"].get("is_suspended"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No active public Reddit account with this username.")
        a = raw["about"]
        sub = a.get("subreddit") or {}
        profile = PublicProfile(
            platform="reddit", username=a["name"], url=f"https://www.reddit.com/user/{a['name']}",
            name=sub.get("title") or None, bio=sub.get("public_description") or None,
            avatar=(a.get("icon_img") or "").split("?", 1)[0] or None,
            created_at=parse_datetime(a.get("created_utc")),
            stats={"karma": a.get("total_karma")},
        )
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability)
        for child in raw.get("posts", []):
            d = child.get("data", {})
            published = parse_datetime(d.get("created_utc"))
            url = f"https://www.reddit.com{d.get('permalink', '')}"
            f.mention(url=url, title=d.get("title", "Reddit post"), snippet=d.get("selftext"),
                      category=SourceCategory.SOCIAL, association="Authored by profile", source=src,
                      confidence=0.95, entity=ref, published_at=published)
            f.event(EventKind.MENTION, f"Reddit post in r/{d.get('subreddit')}", published, src, entity=ref)
        return ConnectorResult(RunStatus.FOUND, f)


class YouTubeConnector(Connector):
    name = "youtube"
    label = "YouTube"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    requires = ("youtube_api_key",)
    description = "Public YouTube channels by handle via the official YouTube Data API v3."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://www.youtube.com/@{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet,statistics", "forHandle": f"@{target}",
                    "key": ctx.settings.youtube_api_key.get_secret_value()},
        )
        check_status(resp, self.label)
        items = resp.json().get("items") or []
        return items[0] if items else None

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No YouTube channel with this handle.")
        sn = raw.get("snippet", {})
        handle = (sn.get("customUrl") or f"@{target}").lstrip("@")
        profile = PublicProfile(
            platform="youtube", username=handle, url=f"https://www.youtube.com/@{handle}",
            name=sn.get("title"), bio=sn.get("description") or None, location=sn.get("country"),
            avatar=((sn.get("thumbnails") or {}).get("high") or {}).get("url"),
            created_at=parse_datetime(sn.get("publishedAt")),
            stats={"subscribers": (raw.get("statistics") or {}).get("subscriberCount")},
        )
        emit_profile(f, profile, category=self.category, reliability=self.reliability)
        return ConnectorResult(RunStatus.FOUND, f)


class XConnector(Connector):
    name = "x"
    label = "X"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    requires = ("x_bearer_token",)
    description = "Public X accounts via the official X API v2 (bearer token)."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://x.com/{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(
            f"https://api.x.com/2/users/by/username/{target}",
            params={"user.fields": "created_at,description,location,profile_image_url,url,entities,name"},
            headers={"Authorization": f"Bearer {ctx.settings.x_bearer_token.get_secret_value()}"},
        )
        if not check_status(resp, self.label):
            return None
        return resp.json().get("data")

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public X account with this username.")
        urls = ((raw.get("entities") or {}).get("url") or {}).get("urls") or []
        website = urls[0].get("expanded_url") if urls else None
        linked = []
        if website and (social := parse_social_url(website)):
            linked.append(social)
            website = None
        profile = PublicProfile(
            platform="x", username=raw["username"], url=f"https://x.com/{raw['username']}",
            name=raw.get("name"), bio=raw.get("description") or None, location=raw.get("location"),
            website=website, avatar=raw.get("profile_image_url"), created_at=parse_datetime(raw.get("created_at")),
            linked_accounts=linked,
        )
        emit_profile(f, profile, category=self.category, reliability=self.reliability)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(website))


class PolicyRestrictedConnector(Connector):
    """Platforms without a legitimate public lookup method. Always NOT VERIFIED, by design."""

    reliability = Reliability.HIGH
    category = SourceCategory.SOCIAL
    supports = frozenset({SeedType.USERNAME})
    reason: str = ""
    profile_url: str = ""

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return self.profile_url.format(target)

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> Any:
        return None

    def normalize(self, raw: Any, target: str, seed_type: SeedType) -> ConnectorResult:
        return ConnectorResult(RunStatus.NOT_VERIFIED, Findings(self.name), self.reason)


class InstagramConnector(PolicyRestrictedConnector):
    name = "instagram"
    label = "Instagram"
    description = "No public lookup API; profile pages require login for automated access."
    reason = "Public source could not be legitimately queried: Instagram requires authentication for automated access."
    profile_url = "https://www.instagram.com/{}/"


class LinkedInConnector(PolicyRestrictedConnector):
    name = "linkedin"
    label = "LinkedIn"
    description = "No public lookup API; LinkedIn prohibits automated profile access."
    reason = "Public source could not be legitimately queried: LinkedIn prohibits automated profile access."
    profile_url = "https://www.linkedin.com/in/{}/"


class BraveSearchConnector(Connector):
    """Web discovery through the official Brave Search API. Results are text matches, not identity proof."""

    name = "web_search"
    label = "Web search"
    category = SourceCategory.SEARCH
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.USERNAME, SeedType.EMAIL, SeedType.PERSON, SeedType.DOMAIN, SeedType.URL})
    requires = ("brave_search_api_key",)
    description = "Public web search results via the Brave Search API."

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        resp = await ctx.http.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": f'"{target}"', "count": 20, "safesearch": "moderate"},
            headers={"Accept": "application/json",
                     "X-Subscription-Token": ctx.settings.brave_search_api_key.get_secret_value()},
        )
        check_status(resp, self.label)
        return {"results": (resp.json().get("web") or {}).get("results", []), "url": str(resp.url)}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        results = raw.get("results", [])
        if not results:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No web results.")
        src = f.source(name="Brave Search", category=self.category, kind="api_search", url=raw["url"],
                       reliability=self.reliability, title=f'Web search for "{target}"')
        for r in results:
            url = r.get("url")
            if not url:
                continue
            social = parse_social_url(url)
            f.mention(url=url, title=r.get("title") or url, snippet=r.get("description"),
                      category=SourceCategory.SOCIAL if social else SourceCategory.WEB,
                      association="Search result (text match)", source=src, confidence=0.25,
                      published_at=parse_datetime(r.get("page_age")))
        return ConnectorResult(RunStatus.FOUND, f)
