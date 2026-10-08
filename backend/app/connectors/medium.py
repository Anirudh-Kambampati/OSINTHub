"""Medium — the public per-author RSS feed, which Medium publishes for syndication."""

import re
from typing import Any

from defusedxml import ElementTree

from app.connectors._profile import PublicProfile, emit_profile
from app.connectors.base import Connector, ConnectorContext, ConnectorResult, Findings, NotVerifiable, check_status
from app.core.enums import EventKind, Reliability, RunStatus, SeedType, SourceCategory
from app.core.text import html_to_text, parse_datetime

FEED = "https://medium.com/feed/@{}"
TITLE_RE = re.compile(r"^Stories by (.+?) on Medium$")


class MediumConnector(Connector):
    name = "medium"
    label = "Medium"
    category = SourceCategory.SOCIAL
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.USERNAME})
    description = "Public Medium author feeds (RSS)."

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        return f"https://medium.com/@{target}"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> str | None:
        resp = await ctx.http.get(FEED.format(target), headers={"Accept": "application/rss+xml, application/xml"})
        if resp.status_code == 403:
            raise NotVerifiable("Medium blocked automated access to its public feed; not bypassed.")
        if not check_status(resp, self.label, not_found=(404, 410)):
            return None
        if "xml" not in resp.content_type and not resp.text.lstrip().startswith("<?xml"):
            raise NotVerifiable("Medium did not return a feed (likely an interstitial page); not bypassed.")
        return resp.text

    def normalize(self, raw: str | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No Medium author feed for this username.")
        channel = ElementTree.fromstring(raw.encode("utf-8")).find("channel")
        if channel is None:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Medium returned an empty feed.")
        m = TITLE_RE.match((channel.findtext("title") or "").strip())
        image = channel.find("image")
        profile = PublicProfile(
            platform="medium",
            username=target,
            url=f"https://medium.com/@{target}",
            name=m.group(1) if m else None,
            bio=channel.findtext("description"),
            avatar=image.findtext("url") if image is not None else None,
        )
        ref, src = emit_profile(f, profile, category=self.category, reliability=self.reliability,
                                source_url=FEED.format(target), confidence=0.85)
        for item in channel.findall("item")[:15]:
            link = (item.findtext("link") or "").split("?", 1)[0]
            title = item.findtext("title") or "Medium story"
            published = parse_datetime(item.findtext("pubDate"))
            if not link:
                continue
            # Only a short derived snippet is kept; full article content is never stored.
            body = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
            f.mention(url=link, title=title, snippet=html_to_text(body)[:200] or None,
                      category=SourceCategory.SOCIAL, association="Authored by profile", source=src,
                      confidence=0.9, entity=ref, published_at=published)
            f.event(EventKind.MENTION, f"Published on Medium: {title}", published, src, entity=ref)
        return ConnectorResult(RunStatus.FOUND, f)
