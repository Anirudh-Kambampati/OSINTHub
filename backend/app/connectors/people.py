"""Name searches against public directories of people who publish professionally.

Name matches are weak evidence on their own: the resolver scores them as name matches, and
each candidate stays a separate profile until corroborated.
"""

from typing import Any
from urllib.parse import quote

from app.connectors._profile import PublicProfile, emit_profile, website_pivots
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, RateLimited, check_status
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

MAX_CANDIDATES = 5


class OrcidConnector(Connector):
    name = "orcid"
    label = "ORCID"
    category = SourceCategory.IDENTITY
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.PERSON, SeedType.EMAIL})
    description = "Researcher identities from the ORCID public registry (name or public email)."
    API = "https://pub.orcid.org/v3.0/expanded-search/"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        if seed_type == SeedType.EMAIL:
            q = f'email:"{target}"'
        else:
            parts = target.split()
            q = f'given-names:"{parts[0]}" AND family-name:"{parts[-1]}"'
        resp = await ctx.http.get(self.API, params={"q": q, "rows": MAX_CANDIDATES},
                                  headers={"Accept": "application/json"})
        check_status(resp, self.label)
        return {"results": resp.json().get("expanded-result") or [], "url": str(resp.url)}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        results = raw.get("results") or []
        if not results:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public ORCID record matched.")
        for r in results[:MAX_CANDIDATES]:
            oid = r["orcid-id"]
            name = " ".join(x for x in (r.get("given-names"), r.get("family-names")) if x) or r.get("credit-name")
            ref, src = emit_profile(f, PublicProfile(
                platform="orcid", username=oid, url=f"https://orcid.org/{oid}", name=name,
                organization=(r.get("institution-name") or [None])[0],
            ), category=self.category, reliability=self.reliability, source_url=f"https://pub.orcid.org/v3.0/{oid}")
            for email in (r.get("email") or [])[:3]:
                f.observe(ref, "email", email, src, 0.9)
            for inst in (r.get("institution-name") or [])[1:4]:
                f.observe(ref, "organization", inst, src, 0.8)
            for alias in (r.get("other-name") or [])[:3]:
                f.observe(ref, "alias", alias, src, 0.7)
        return ConnectorResult(RunStatus.FOUND, f)


class WikidataConnector(Connector):
    """Notable public figures only: Wikidata items describe people with encyclopedic notability."""

    name = "wikidata"
    label = "Wikidata"
    category = SourceCategory.IDENTITY
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.PERSON})
    description = "Notable public figures in Wikidata (label, description, official website, social links)."
    # Wikimedia's robot policy requires contact details in the User-Agent.
    requires = ("operator_contact",)
    API = "https://www.wikidata.org/w/api.php"
    # Properties: P31 instance of, P856 official website, P2002 X, P2037 GitHub, P4033 Mastodon, P569 born.
    HUMAN = "Q5"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        search = await ctx.http.get(self.API, params={
            "action": "wbsearchentities", "search": target, "language": "en", "type": "item",
            "limit": MAX_CANDIDATES, "format": "json"})
        check_status(search, self.label)
        ids = [x["id"] for x in search.json().get("search", [])]
        if not ids:
            return {"entities": {}}
        detail = await ctx.http.get(self.API, params={
            "action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims",
            "languages": "en", "format": "json"})
        check_status(detail, self.label)
        return {"entities": detail.json().get("entities", {}), "order": ids}

    @staticmethod
    def _claim(entity: dict, prop: str) -> list[Any]:
        out = []
        for c in (entity.get("claims") or {}).get(prop, []):
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if v is not None:
                out.append(v)
        return out

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        pivots = []
        for qid in raw.get("order", []):
            e = raw["entities"].get(qid) or {}
            if not any(isinstance(v, dict) and v.get("id") == self.HUMAN for v in self._claim(e, "P31")):
                continue  # only people
            label = ((e.get("labels") or {}).get("en") or {}).get("value")
            desc = ((e.get("descriptions") or {}).get("en") or {}).get("value")
            websites = [v for v in self._claim(e, "P856") if isinstance(v, str)]
            linked = [f"x:{v}" for v in self._claim(e, "P2002") if isinstance(v, str)]
            linked += [f"github:{v}" for v in self._claim(e, "P2037") if isinstance(v, str)]
            profile = PublicProfile(
                platform="wikidata", username=qid, url=f"https://www.wikidata.org/wiki/{qid}", name=label,
                occupation=desc, website=websites[0] if websites else None, linked_accounts=linked,
            )
            emit_profile(f, profile, category=self.category, reliability=self.reliability,
                         source_url=f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
            pivots += website_pivots(*websites[:1])
        if f.is_empty:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No notable person with this name in Wikidata.")
        return ConnectorResult(RunStatus.FOUND, f, pivots=pivots)


class StackExchangeConnector(Connector):
    name = "stackoverflow"
    label = "Stack Overflow"
    category = SourceCategory.CODE
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.PERSON, SeedType.USERNAME})
    description = "Stack Overflow users whose display name matches exactly (Stack Exchange API)."
    API = "https://api.stackexchange.com/2.3/users"

    def manual_url(self, target, seed_type):
        return f"https://stackoverflow.com/users?tab=Reputation&filter=all&search={quote(target)}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        resp = await ctx.http.get(self.API, params={"inname": target, "site": "stackoverflow", "pagesize": 20,
                                                     "order": "desc", "sort": "reputation"})
        check_status(resp, self.label)
        body = resp.json()
        if body.get("error_id") == 502:
            raise RateLimited("Stack Exchange API quota exhausted.")
        return {"items": body.get("items", [])}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        # `inname` is a substring search; only exact display-name matches are kept.
        exact = [u for u in raw.get("items", []) if (u.get("display_name") or "").lower() == target.lower()]
        if not exact:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Stack Overflow user with exactly this display name.")
        pivots = []
        for u in exact[:MAX_CANDIDATES]:
            site = u.get("website_url") or None
            emit_profile(f, PublicProfile(
                platform="stackoverflow", username=str(u["user_id"]), url=u.get("link") or "",
                name=u.get("display_name"), location=u.get("location"), website=site,
                avatar=u.get("profile_image"), created_at=parse_datetime(u.get("creation_date")),
                stats={"reputation": u.get("reputation")},
            ), category=self.category, reliability=self.reliability,
                source_url=f"https://api.stackexchange.com/2.3/users/{u['user_id']}?site=stackoverflow")
            pivots += website_pivots(site)
        return ConnectorResult(RunStatus.FOUND, f, pivots=pivots)
