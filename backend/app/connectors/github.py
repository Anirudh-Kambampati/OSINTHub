"""GitHub — official REST API (api.github.com). Optional OSINT_GITHUB_TOKEN raises rate limits."""

from typing import Any

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import (
    Connector, ConnectorContext, ConnectorResult, EntityRef, Findings, check_status,
)
from app.connectors.social import parse_social_url
from app.core.enums import EntityKind, EventKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

API = "https://api.github.com"
MAX_SEARCH_RESULTS = 5
MAX_REPOS = 10


class GitHubConnector(Connector):
    name = "github"
    label = "GitHub"
    category = SourceCategory.CODE
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME, SeedType.EMAIL, SeedType.PERSON})
    description = "Public developer profiles and repositories via the official GitHub REST API."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://github.com/{target}" if seed_type == SeedType.USERNAME else None

    def _headers(self, ctx: ConnectorContext) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if ctx.settings.github_token:
            headers["Authorization"] = f"Bearer {ctx.settings.github_token.get_secret_value()}"
        return headers

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        headers = self._headers(ctx)
        logins: list[str]
        search_url = commit_url = None
        commit_logins: dict[str, str | None] = {}
        if seed_type == SeedType.USERNAME:
            logins = [target]
        else:
            q = f"{target} in:email" if seed_type == SeedType.EMAIL else f'"{target}" in:name'
            resp = await ctx.http.get(f"{API}/search/users", params={"q": q, "per_page": MAX_SEARCH_RESULTS}, headers=headers)
            check_status(resp, self.label)
            search_url = str(resp.url)
            logins = [item["login"] for item in resp.json().get("items", [])][:MAX_SEARCH_RESULTS]
            if seed_type == SeedType.EMAIL:
                # Public commits record their author email; GitHub links them to the account.
                commits = await ctx.http.get(f"{API}/search/commits",
                                             params={"q": f"author-email:{target}", "per_page": 10}, headers=headers)
                if commits.status_code == 200:
                    commit_url = str(commits.url)
                    for item in commits.json().get("items", []):
                        login = (item.get("author") or {}).get("login")
                        if login and login not in commit_logins:
                            commit_logins[login] = item.get("html_url")
                    logins += [lg for lg in commit_logins if lg not in logins][:MAX_SEARCH_RESULTS]

        users = []
        for login in logins:
            resp = await ctx.http.get(f"{API}/users/{login}", headers=headers)
            if not check_status(resp, self.label):
                continue
            user = resp.json()
            repos: list[dict[str, Any]] = []
            r = await ctx.http.get(
                f"{API}/users/{login}/repos", params={"sort": "pushed", "per_page": MAX_REPOS, "type": "owner"},
                headers=headers,
            )
            if r.status_code == 200:
                repos = r.json()
            users.append({"user": user, "repos": repos})
        return {"mode": seed_type.value, "search_url": search_url, "users": users,
                "commit_url": commit_url, "commit_logins": commit_logins}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        pivots = []
        for item in raw.get("users", []):
            u = item["user"]
            linked = []
            if u.get("twitter_username"):
                linked.append(f"x:{u['twitter_username']}")
            blog = (u.get("blog") or "").strip() or None
            if blog and (social := parse_social_url(blog)):
                linked.append(social)
                blog = None
            profile = PublicProfile(
                platform="github",
                username=u["login"],
                url=u.get("html_url") or f"https://github.com/{u['login']}",
                name=u.get("name"),
                bio=u.get("bio"),
                location=u.get("location"),
                website=blog,
                email=u.get("email"),
                organization=(u.get("company") or "").lstrip("@").strip() or None,
                avatar=u.get("avatar_url"),
                created_at=parse_datetime(u.get("created_at")),
                updated_at=parse_datetime(u.get("updated_at")),
                linked_accounts=linked,
                stats={k: u.get(k) for k in ("public_repos", "followers", "following") if u.get(k) is not None},
            )
            ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                    source_url=f"{API}/users/{u['login']}")
            if seed_type == SeedType.EMAIL and u["login"] in (raw.get("commit_logins") or {}):
                commit_src = f.source(
                    name=self.label, category=SourceCategory.SEARCH, kind="commit_search", url=raw["commit_url"],
                    reliability=self.reliability, title=f"Public commits authored as {target}",
                )
                f.observe(ref, "email", target, commit_src, 0.85)
                if commit := raw["commit_logins"][u["login"]]:
                    f.mention(url=commit, title=f"Public commit by @{u['login']} with author email {target}",
                              snippet=None, category=SourceCategory.CODE, association="Commit author email",
                              source=commit_src, confidence=0.85, entity=ref)
            elif seed_type == SeedType.EMAIL and raw.get("search_url") and not u.get("email"):
                # GitHub's `in:email` search only matches publicly listed addresses.
                search_src = f.source(
                    name=self.label, category=SourceCategory.SEARCH, kind="api_search", url=raw["search_url"],
                    reliability=self.reliability, title=f"GitHub user search for {target}",
                )
                f.observe(ref, "email", target, search_src, 0.8)
            self._emit_repos(f, ref, src, item.get("repos", []))
            pivots += website_pivots(blog)
        status = RunStatus.FOUND if raw.get("users") else RunStatus.NOT_FOUND
        message = None if raw.get("users") else "No public GitHub account matched."
        return ConnectorResult(status, f, message, pivots)

    @staticmethod
    def _emit_repos(f: Findings, owner: EntityRef, src: int, repos: list[dict[str, Any]]) -> None:
        for repo in repos[:MAX_REPOS]:
            if repo.get("fork"):
                continue
            ref = f.entity(
                EntityKind.REPOSITORY, f"github:{repo['full_name'].lower()}", repo["full_name"],
                url=repo.get("html_url"), language=repo.get("language"), stars=repo.get("stargazers_count"),
                description=repo.get("description"),
            )
            f.relate(owner, ref, RelType.OWNS, src, 0.95)
            f.event(EventKind.REPOSITORY, f"Repository {repo['name']} created", parse_datetime(repo.get("created_at")),
                    src, entity=ref, detail=repo.get("description"))
            if repo.get("homepage"):
                f.observe(ref, "website", repo["homepage"], src, 0.8)
