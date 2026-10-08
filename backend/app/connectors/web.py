"""Public websites and public documents. Both honour robots.txt and the SSRF guard."""

import io
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from app.connectors.base import (
    Connector, ConnectorContext, ConnectorError, ConnectorResult, Findings, NotVerifiable, Pivot, check_status,
)
from app.connectors.domain import domain_ref
from app.connectors.social import parse_social_url
from app.core.classify import Classification
from app.core.enums import EntityKind, EventKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.normalize import normalize_email, normalize_url, registrable_domain
from app.core.net import ResponseTooLarge, UnsafeURLError
from app.core.text import clean_text, parse_datetime

MAX_EMAILS = 5
MAX_LINKED = 20


async def ensure_robots_allowed(url: str, ctx: ConnectorContext) -> None:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        resp = await ctx.http.get(robots_url, max_bytes=500_000)
    except UnsafeURLError:
        raise
    except Exception:  # unreachable robots.txt -> treat as no restrictions (RFC 9309 §2.3.1.3)
        return
    if resp.status_code in (401, 403):
        raise NotVerifiable("robots.txt is access-restricted; treating the site as disallowed.")
    if resp.status_code != 200:
        return
    parser = RobotFileParser()
    parser.parse(resp.text.splitlines())
    if not parser.can_fetch(ctx.settings.user_agent, url):
        raise NotVerifiable("The site's robots.txt disallows automated access to this page.")


class WebsiteConnector(Connector):
    name = "website"
    label = "Website"
    category = SourceCategory.WEB
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.URL, SeedType.DOMAIN})
    accepts_pivots = frozenset({"website"})
    description = "Public website metadata, rel=me profile links, published contact emails and documents."

    def targets(self, seed: Classification) -> list[str]:
        if seed.type == SeedType.DOMAIN:
            return [f"https://{seed.normalized}/"]
        return super().targets(seed)

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        url = target if "://" in target else f"https://{target}"
        try:
            await ensure_robots_allowed(url, ctx)
            resp = await ctx.http.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        except UnsafeURLError as exc:
            raise ConnectorError(f"Refused: {exc}") from exc
        except ResponseTooLarge as exc:
            raise ConnectorError("Page is too large to process.") from exc
        if not check_status(resp, self.label, not_found=(404, 410)):
            return {"url": url, "html": None}
        if "html" not in resp.content_type:
            raise ConnectorError(f"Not an HTML page ({resp.content_type or 'unknown type'}).")
        return {"url": resp.url, "html": resp.text}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw.get("html"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Page not found.")
        url = raw["url"]
        soup = BeautifulSoup(raw["html"], "html.parser")
        host = urlsplit(url).hostname or ""
        key = normalize_url(target if "://" in target else f"https://{target}")
        site = f.entity(EntityKind.WEBSITE, key, key, url=url)
        title = clean_text(soup.title.string if soup.title else None, 300)
        src = f.source(name=host, category=self.category, kind="web_page", url=url,
                       reliability=self.reliability, title=title or url)
        f.relate(site, domain_ref(f, host), RelType.PART_OF, src, 0.99)

        f.observe(site, "title", title, src, 0.9)
        f.observe(site, "description", _meta(soup, "description") or _meta(soup, "og:description"), src, 0.85)
        author = _meta(soup, "author")
        f.observe(site, "name", author, src, 0.6)
        if og := _meta(soup, "og:image"):
            f.observe(site, "image", urljoin(url, og), src, 0.6)

        linked: dict[str, float] = {}
        emails: list[str] = []
        documents: list[str] = []
        site_domain = registrable_domain(host)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                email = normalize_email(href)
                if "@" in email and email not in emails and len(emails) < MAX_EMAILS:
                    emails.append(email)
                continue
            absolute = urljoin(url, href)
            if absolute.split("?", 1)[0].lower().endswith(".pdf"):
                if registrable_domain(urlsplit(absolute).hostname or "") == site_domain and absolute not in documents:
                    documents.append(absolute)
                continue
            if social := parse_social_url(absolute):
                rel = {r.lower() for r in (a.get("rel") or [])}
                # rel="me" is an explicit, machine-readable claim of identity.
                linked[social] = max(linked.get(social, 0), 0.9 if "me" in rel else 0.7)
        for link in soup.find_all("link", rel=True, href=True):
            if "me" in [r.lower() for r in link["rel"]] and (social := parse_social_url(urljoin(url, link["href"]))):
                linked[social] = 0.9
        for social, conf in list(linked.items())[:MAX_LINKED]:
            f.observe(site, "linked_account", social, src, conf)
        for email in emails:
            # Only addresses the site owner explicitly published as mailto: links.
            f.observe(site, "email", email, src, 0.8)
        pivots = [Pivot("document", d) for d in documents]
        return ConnectorResult(RunStatus.FOUND, f, pivots=pivots)


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
    return clean_text(tag.get("content"), 400) if tag and tag.get("content") else None


class DocumentConnector(Connector):
    """Extracts document-level metadata from public PDFs linked by a site. Body text is never parsed."""

    name = "documents"
    label = "Documents"
    category = SourceCategory.DOCUMENT
    reliability = Reliability.MEDIUM
    supports = frozenset({SeedType.URL})
    accepts_pivots = frozenset({"document"})
    description = "Metadata (title, author, creator tool, dates) of public PDF documents linked from discovered sites."
    FIELDS = {"/Title": "title", "/Author": "author", "/Creator": "creator_tool", "/Producer": "producer"}

    def targets(self, seed: Classification) -> list[str]:
        return [seed.normalized] if seed.type == SeedType.URL and seed.normalized.lower().endswith(".pdf") else []

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        try:
            await ensure_robots_allowed(target, ctx)
            resp = await ctx.http.get(target, max_bytes=ctx.settings.max_document_bytes)
        except UnsafeURLError as exc:
            raise ConnectorError(f"Refused: {exc}") from exc
        except ResponseTooLarge as exc:
            raise ConnectorError("Document exceeds the size limit.") from exc
        if not check_status(resp, self.label, not_found=(404, 410)):
            return {"url": target, "content": None}
        if not resp.content.startswith(b"%PDF"):
            raise ConnectorError("Linked file is not a PDF.")
        return {"url": resp.url, "content": resp.content}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        f = Findings(self.name)
        if not raw.get("content"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Document not found.")
        try:
            reader = PdfReader(io.BytesIO(raw["content"]))
            meta = reader.metadata or {}
            pages = len(reader.pages)
        except (PdfReadError, ValueError, KeyError) as exc:
            raise ConnectorError(f"Could not read PDF metadata: {type(exc).__name__}") from exc
        url = raw["url"]
        filename = urlsplit(url).path.rsplit("/", 1)[-1] or url
        doc = f.entity(EntityKind.DOCUMENT, normalize_url(url), filename, url=url, pages=pages)
        src = f.source(name=urlsplit(url).hostname or "document", category=self.category, kind="public_document",
                       url=url, reliability=self.reliability, title=filename)
        f.relate(doc, domain_ref(f, urlsplit(url).hostname or ""), RelType.FOUND_ON, src, 0.95)
        for key, attr in self.FIELDS.items():
            f.observe(doc, attr, meta.get(key), src, 0.8)
        created = _pdf_date(meta.get("/CreationDate"))
        modified = _pdf_date(meta.get("/ModDate"))
        if created:
            f.observe(doc, "created_at", created.date().isoformat(), src, 0.75)
        if modified:
            f.observe(doc, "modified_at", modified.date().isoformat(), src, 0.75)
        label = clean_text(meta.get("/Title"), 200) or filename
        f.event(EventKind.DOCUMENT, f"Document created: {label}", created, src, entity=doc,
                detail=clean_text(meta.get("/Author"), 200))
        return ConnectorResult(RunStatus.FOUND, f)


def _pdf_date(value: Any):
    if not value:
        return None
    s = str(value)
    if s.startswith("D:"):
        s = s[2:]
    digits = s[:14]
    if len(digits) >= 8 and digits[:8].isdigit():
        d = digits.ljust(14, "0")
        return parse_datetime(f"{d[:4]}-{d[4:6]}-{d[6:8]}T{d[8:10]}:{d[10:12]}:{d[12:14]}+00:00")
    return parse_datetime(s)
