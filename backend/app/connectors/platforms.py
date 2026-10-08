"""Username lookups on platforms with official public JSON APIs.

Each connector is mostly a mapping from the platform's response to a `PublicProfile`; the
shared base handles fetching, not-found detection and emitting normalized observations.
"""

import html
import re
from typing import Any, ClassVar
from urllib.parse import quote

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import (
    Connector, ConnectorContext, ConnectorResult, Findings, check_status,
)
from app.connectors.social import parse_social_url
from app.core.enums import EntityKind, EventKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.text import html_to_text, parse_datetime


def _real_email(email: str | None) -> str | None:
    """Platform placeholder addresses (noreply) are not contact information."""
    if not email or "noreply" in email.lower() or "@" not in email:
        return None
    return email


def _split_links(urls: list[str]) -> tuple[list[str], str | None]:
    linked = [s for u in urls if u and (s := parse_social_url(u))]
    websites = [u for u in urls if u and not parse_social_url(u)]
    return linked, websites[0] if websites else None


class JsonProfileConnector(Connector):
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    api_url: ClassVar[str]
    profile_url: ClassVar[str]
    not_found_codes: ClassVar[tuple[int, ...]] = (404,)

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return self.profile_url.format(u=quote(target))

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> Any:
        resp = await ctx.http.get(self.api_url.format(u=quote(target)), headers={"Accept": "application/json"})
        if not check_status(resp, self.label, not_found=self.not_found_codes):
            return None
        return resp.json()

    def to_profile(self, raw: Any, target: str) -> PublicProfile | None:
        raise NotImplementedError

    def extra(self, f: Findings, raw: Any, profile: PublicProfile, ref, src: int) -> None:
        """Optional hook for repositories/mentions."""

    def normalize(self, raw: Any, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        profile = self.to_profile(raw, target) if raw else None
        if profile is None:
            return ConnectorResult(RunStatus.NOT_FOUND, f, f"No public {self.label} account with this username.")
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                source_url=self.api_url.format(u=quote(profile.key or profile.username)))
        self.extra(f, raw, profile, ref, src)
        return ConnectorResult(RunStatus.FOUND, f, pivots=website_pivots(profile.website))


class CodebergConnector(JsonProfileConnector):
    name = "codeberg"
    label = "Codeberg"
    category = SourceCategory.CODE
    description = "Public Codeberg (Forgejo) user profiles via the official API."
    api_url = "https://codeberg.org/api/v1/users/{u}"
    profile_url = "https://codeberg.org/{u}"

    def to_profile(self, raw, target):
        linked, website = _split_links([raw.get("website") or ""])
        return PublicProfile(
            platform="codeberg", username=raw["login"], url=raw.get("html_url") or f"https://codeberg.org/{raw['login']}",
            name=raw.get("full_name") or None, bio=raw.get("description") or None, location=raw.get("location") or None,
            website=website, email=_real_email(raw.get("email")), avatar=raw.get("avatar_url"),
            created_at=parse_datetime(raw.get("created")), linked_accounts=linked,
            stats={"followers": raw.get("followers_count")},
        )


class CratesIoConnector(JsonProfileConnector):
    name = "cratesio"
    label = "crates.io"
    category = SourceCategory.CODE
    description = "Rust package publisher accounts on crates.io (linked to GitHub by design)."
    api_url = "https://crates.io/api/v1/users/{u}"
    profile_url = "https://crates.io/users/{u}"

    def to_profile(self, raw, target):
        u = raw.get("user") or {}
        if not u.get("login"):
            return None
        linked = [parse_social_url(u["url"])] if u.get("url") and parse_social_url(u["url"]) else []
        return PublicProfile(
            platform="cratesio", username=u["login"], url=f"https://crates.io/users/{u['login']}",
            name=u.get("name") or None, avatar=u.get("avatar"), created_at=parse_datetime(u.get("created_at")),
            # crates.io logins *are* GitHub logins (OAuth), so this link is verified by the platform.
            verified_accounts=linked,
        )


class DockerHubConnector(JsonProfileConnector):
    name = "dockerhub"
    label = "Docker Hub"
    category = SourceCategory.CODE
    description = "Public Docker Hub user/organization profiles."
    api_url = "https://hub.docker.com/v2/users/{u}/"
    profile_url = "https://hub.docker.com/u/{u}"

    def to_profile(self, raw, target):
        handle = raw.get("username") or raw.get("orgname")
        if not handle:
            return None
        linked, website = _split_links([raw.get("profile_url") or ""])
        return PublicProfile(
            platform="dockerhub", username=handle, url=f"https://hub.docker.com/u/{handle}",
            name=raw.get("full_name") or None, location=raw.get("location") or None,
            organization=raw.get("company") or None, website=website, linked_accounts=linked,
            created_at=parse_datetime(raw.get("date_joined")),
        )


class HuggingFaceConnector(JsonProfileConnector):
    name = "huggingface"
    label = "Hugging Face"
    category = SourceCategory.CODE
    description = "Public Hugging Face profiles (models, datasets, organizations)."
    api_url = "https://huggingface.co/api/users/{u}/overview"
    profile_url = "https://huggingface.co/{u}"

    def to_profile(self, raw, target):
        if not raw.get("_id"):
            return None
        return PublicProfile(
            platform="huggingface", username=raw.get("user") or target, url=f"https://huggingface.co/{target}",
            name=raw.get("fullname") or None, avatar=raw.get("avatarUrl"),
            stats={"models": raw.get("numModels"), "datasets": raw.get("numDatasets"),
                   "followers": raw.get("numFollowers")},
        )

    def extra(self, f, raw, profile, ref, src):
        for org in (raw.get("orgs") or [])[:10]:
            if org.get("fullname") or org.get("name"):
                f.observe(ref, "organization", org.get("fullname") or org["name"], src, 0.7)


class ChessComConnector(JsonProfileConnector):
    name = "chesscom"
    label = "Chess.com"
    description = "Public Chess.com player profiles via the Published-Data API."
    api_url = "https://api.chess.com/pub/player/{u}"
    profile_url = "https://www.chess.com/member/{u}"
    not_found_codes = (404, 410)

    def to_profile(self, raw, target):
        if not raw.get("username"):
            return None
        linked = [s for u in [raw.get("twitch_url")] if u and (s := parse_social_url(u))]
        return PublicProfile(
            platform="chesscom", username=raw["username"], url=raw.get("url") or f"https://www.chess.com/member/{target}",
            name=raw.get("name") or None, location=raw.get("location") or None, avatar=raw.get("avatar"),
            created_at=parse_datetime(raw.get("joined")), linked_accounts=linked,
            stats={"followers": raw.get("followers"), "title": raw.get("title")},
        )


class LichessConnector(JsonProfileConnector):
    name = "lichess"
    label = "Lichess"
    description = "Public Lichess player profiles via the official API."
    api_url = "https://lichess.org/api/user/{u}"
    profile_url = "https://lichess.org/@/{u}"

    def to_profile(self, raw, target):
        if not raw.get("username") or raw.get("disabled") or raw.get("tosViolation"):
            return None
        prof = raw.get("profile") or {}
        name = " ".join(x for x in (prof.get("firstName"), prof.get("lastName")) if x) or prof.get("realName")
        urls = (prof.get("links") or "").split()
        linked, website = _split_links(urls)
        return PublicProfile(
            platform="lichess", username=raw["username"], url=f"https://lichess.org/@/{raw['username']}",
            name=name or None, bio=prof.get("bio") or None, location=prof.get("location") or None,
            website=website, linked_accounts=linked, created_at=parse_datetime((raw.get("createdAt") or 0) / 1000 or None),
            stats={"games": (raw.get("count") or {}).get("all")},
        )


class CodewarsConnector(JsonProfileConnector):
    name = "codewars"
    label = "Codewars"
    category = SourceCategory.CODE
    description = "Public Codewars profiles via the official API."
    api_url = "https://www.codewars.com/api/v1/users/{u}"
    profile_url = "https://www.codewars.com/users/{u}"

    def to_profile(self, raw, target):
        if not raw.get("username"):
            return None
        return PublicProfile(
            platform="codewars", username=raw["username"], url=f"https://www.codewars.com/users/{raw['username']}",
            name=raw.get("name") or None, organization=raw.get("clan") or None,
            stats={"honor": raw.get("honor"), "leaderboard": raw.get("leaderboardPosition")},
        )


class NpmConnector(Connector):
    """npm has no public profile API; packages a user maintains are listed by the registry search."""

    name = "npm"
    label = "npm"
    category = SourceCategory.CODE
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Packages maintained on the npm registry (official registry search API)."
    API = "https://registry.npmjs.org/-/v1/search"

    def manual_url(self, target, seed_type):
        return f"https://www.npmjs.com/~{quote(target)}"

    async def fetch(self, target, seed_type, ctx):
        resp = await ctx.http.get(self.API, params={"text": f"maintainer:{target}", "size": 20})
        check_status(resp, self.label)
        return {"objects": resp.json().get("objects", []), "url": str(resp.url)}

    def normalize(self, raw, target, seed_type):
        f = Findings(self.name)
        target_l = target.lower()
        packages = [o["package"] for o in raw.get("objects", [])
                    if any((m.get("username") or "").lower() == target_l
                           for m in o.get("package", {}).get("maintainers", []))]
        if not packages:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No npm packages maintained by this username.")
        profile = PublicProfile(platform="npm", username=target, url=f"https://www.npmjs.com/~{target}",
                                stats={"packages": len(packages)})
        emails = {m.get("email") for p in packages for m in p.get("maintainers", [])
                  if (m.get("username") or "").lower() == target_l and m.get("email")}
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability, source_url=raw["url"])
        for email in list(emails)[:3]:
            # Maintainer emails are published in package metadata by the maintainer.
            f.observe(ref, "email", email, src, 0.85)
        for p in packages[:15]:
            repo = f.entity(EntityKind.REPOSITORY, f"npm:{p['name']}", p["name"],
                            url=(p.get("links") or {}).get("npm"), description=p.get("description"))
            f.relate(ref, repo, RelType.OWNS, src, 0.9)
            f.event(EventKind.REPOSITORY, f"npm package {p['name']} published", parse_datetime(p.get("date")),
                    src, entity=repo, detail=p.get("description"))
            repo_url = ((p.get("links") or {}).get("repository") or "")
            if social := parse_social_url(repo_url.rsplit("/", 1)[0]):
                f.observe(ref, "linked_account", social, src, 0.75)
        return ConnectorResult(RunStatus.FOUND, f)


_HREF = re.compile(r'href="(https?://[^"]+)"')


def _field_url(value: str) -> str | None:
    """Profile field values are HTML; links carry the real URL in href, the text drops the scheme."""
    if m := _HREF.search(value):
        return html.unescape(m.group(1))
    text = html_to_text(value)
    return text if text.startswith(("http://", "https://")) else None


MASTODON_INSTANCES = ("mastodon.social", "fosstodon.org", "infosec.exchange", "hachyderm.io", "mstdn.social")


class MastodonConnector(Connector):
    """Account lookup on major Mastodon instances. Profile fields verified by the instance
    (rel=me back-links, `verified_at`) are recorded as verified links."""

    name = "mastodon"
    label = "Mastodon"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = f"Public Mastodon accounts on {', '.join(MASTODON_INSTANCES)} (official REST API)."

    def manual_url(self, target, seed_type):
        return f"https://mastodon.social/@{quote(target)}"

    async def fetch(self, target, seed_type, ctx):
        found = []
        for instance in MASTODON_INSTANCES:
            try:
                resp = await ctx.http.get(f"https://{instance}/api/v1/accounts/lookup", params={"acct": target})
            except Exception:  # one unreachable instance shouldn't fail the rest
                continue
            if resp.status_code == 200:
                found.append((instance, resp.json()))
            elif resp.status_code == 429:
                check_status(resp, f"{self.label} ({instance})")
        return found

    def normalize(self, raw, target, seed_type):
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f,
                                   f"No account with this handle on {len(MASTODON_INSTANCES)} major instances.")
        pivots = []
        for instance, acct in raw:
            if acct.get("suspended"):
                continue
            verified, linked, sites = [], [], []
            for fld in acct.get("fields") or []:
                url = _field_url(fld.get("value") or "")
                if not url:
                    continue
                social = parse_social_url(url)
                if fld.get("verified_at"):
                    (verified if social else sites).append(social or url)
                elif social:
                    linked.append(social)
                else:
                    sites.append(url)
            profile = PublicProfile(
                platform="mastodon", username=acct["username"], key=f"{acct['username']}@{instance}",
                url=acct.get("url") or f"https://{instance}/@{acct['username']}",
                name=acct.get("display_name") or None, bio=html_to_text(acct.get("note")) or None,
                avatar=acct.get("avatar"), created_at=parse_datetime(acct.get("created_at")),
                website=sites[0] if sites else None, linked_accounts=linked, verified_accounts=verified,
                stats={"followers": acct.get("followers_count"), "posts": acct.get("statuses_count")},
            )
            ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                    source_url=f"https://{instance}/api/v1/accounts/lookup?acct={acct['username']}")
            for site in sites[1:]:
                f.observe(ref, "website", site, src, 0.85)
            pivots += website_pivots(*sites[:1])
        if f.is_empty:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Only suspended accounts matched.")
        return ConnectorResult(RunStatus.FOUND, f, pivots=pivots)
