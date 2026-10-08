"""Bluesky — public AppView XRPC API (no authentication required for public profiles)."""

import re
from typing import Any

from app.connectors._profile import PublicProfile, emit_profile
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, check_status
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import parse_datetime

API = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class BlueskyConnector(Connector):
    name = "bluesky"
    label = "Bluesky"
    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})
    description = "Public Bluesky profiles via the official public AppView API."

    @staticmethod
    def _handle(target: str) -> str | None:
        t = target.lower()
        handle = t if "." in t else f"{t}.bsky.social"
        return handle if all(LABEL_RE.match(p) for p in handle.split(".")) else None

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        handle = self._handle(target)
        return f"https://bsky.app/profile/{handle}" if handle else None

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        handle = self._handle(target)
        if not handle:
            return {"invalid": True}
        resp = await ctx.http.get(API, params={"actor": handle})
        if resp.status_code == 400:  # XRPC returns 400 "Profile not found"
            return None
        if not check_status(resp, self.label):
            return None
        return resp.json()

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if raw and raw.get("invalid"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Not a valid Bluesky handle (underscores are not allowed).")
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Bluesky profile with this handle.")
        handle = raw["handle"]
        short = handle.removesuffix(".bsky.social")
        profile = PublicProfile(
            platform="bluesky",
            username=short,
            url=f"https://bsky.app/profile/{handle}",
            name=raw.get("displayName") or None,
            bio=raw.get("description") or None,
            avatar=raw.get("avatar"),
            created_at=parse_datetime(raw.get("createdAt")),
            stats={k: raw.get(k) for k in ("followersCount", "postsCount") if raw.get(k) is not None},
        )
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                source_url=f"{API}?actor={handle}")
        if "." in short:  # custom-domain handles are DNS-verified by Bluesky
            f.observe(ref, "website", short, src, 0.9)
        return ConnectorResult(RunStatus.FOUND, f)
