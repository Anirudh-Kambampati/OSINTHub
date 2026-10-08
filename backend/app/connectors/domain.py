"""Domain intelligence from public infrastructure records: DNS, RDAP, CT logs, web archive."""

from typing import Any

from app.connectors.base import (
    Connector, ConnectorContext, ConnectorError, ConnectorResult, EntityRef, Findings, check_status, domain_of_seed,
)
from app.core.classify import Classification
from app.core.enums import EntityKind, EventKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.normalize import normalize_domain, normalize_url, registrable_domain
from app.core.net import ResponseTooLarge
from app.core.text import parse_datetime

DOMAIN_SEEDS = frozenset({SeedType.DOMAIN, SeedType.URL, SeedType.EMAIL})


def domain_ref(f: Findings, domain: str) -> EntityRef:
    d = normalize_domain(domain)
    return f.entity(EntityKind.DOMAIN, d, d)


class _DomainConnector(Connector):
    supports = DOMAIN_SEEDS

    def targets(self, seed: Classification) -> list[str]:
        domain = domain_of_seed(seed)
        return [domain] if domain else []


class DnsConnector(_DomainConnector):
    name = "dns"
    label = "DNS"
    category = SourceCategory.DNS
    reliability = Reliability.HIGH
    description = "Public DNS records (A, AAAA, MX, NS, SPF/DMARC) via DNS-over-HTTPS."
    RESOLVER = "https://cloudflare-dns.com/dns-query"
    TYPES = ("A", "AAAA", "MX", "NS", "TXT")

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for rtype, name in [*((t, target) for t in self.TYPES), ("TXT", f"_dmarc.{target}")]:
            resp = await ctx.http.get(self.RESOLVER, params={"name": name, "type": rtype},
                                      headers={"Accept": "application/dns-json"})
            check_status(resp, self.label)
            out[f"{rtype}:{name}"] = resp.json()
        return out

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if raw.get(f"A:{target}", {}).get("Status") == 3:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Domain does not exist (NXDOMAIN).")
        dom = domain_ref(f, target)
        src = f.source(name="DNS (DoH)", category=self.category, kind="dns_records",
                       url=f"{self.RESOLVER}?name={target}", reliability=self.reliability,
                       title=f"DNS records for {target}")
        count = 0
        for key, body in raw.items():
            rtype, name = key.split(":", 1)
            for ans in body.get("Answer") or []:
                data = str(ans.get("data", "")).strip().strip('"')
                if not data:
                    continue
                count += 1
                if rtype in ("A", "AAAA") and ans.get("type") in (1, 28):
                    f.observe(dom, "ip_address", data, src, 0.95)
                elif rtype == "MX" and ans.get("type") == 15:
                    f.observe(dom, "mail_server", data.split()[-1].rstrip("."), src, 0.95)
                elif rtype == "NS" and ans.get("type") == 2:
                    f.observe(dom, "nameserver", data.rstrip("."), src, 0.95)
                elif rtype == "TXT" and data.startswith("v=spf1"):
                    f.observe(dom, "spf", data, src, 0.95)
                elif rtype == "TXT" and name.startswith("_dmarc.") and data.startswith("v=DMARC1"):
                    f.observe(dom, "dmarc", data, src, 0.95)
        if not count:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public DNS records returned.")
        return ConnectorResult(RunStatus.FOUND, f)


class RdapConnector(_DomainConnector):
    """Registration metadata. Registrant contact details are deliberately NOT collected."""

    name = "rdap"
    label = "RDAP"
    category = SourceCategory.DOMAIN
    reliability = Reliability.HIGH
    description = "Domain registration dates, registrar and status via RDAP (registrant contacts excluded)."

    def targets(self, seed: Classification) -> list[str]:
        return [registrable_domain(t) for t in super().targets(seed)]

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any] | None:
        resp = await ctx.http.get(f"https://rdap.org/domain/{target}", headers={"Accept": "application/rdap+json"})
        if not check_status(resp, self.label):
            return None
        return {"url": resp.url, "data": resp.json()}

    def normalize(self, raw: dict[str, Any] | None, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No RDAP registration record found.")
        d = raw["data"]
        dom = domain_ref(f, target)
        src = f.source(name="RDAP", category=self.category, kind="registration_record", url=raw["url"],
                       reliability=self.reliability, title=f"RDAP record for {target}")
        for ev in d.get("events") or []:
            action, when = ev.get("eventAction"), parse_datetime(ev.get("eventDate"))
            if not when:
                continue
            if action == "registration":
                f.observe(dom, "registered_at", when.date().isoformat(), src, 0.97)
                f.event(EventKind.DOMAIN, f"Domain {target} registered", when, src, entity=dom)
            elif action == "expiration":
                f.observe(dom, "expires_at", when.date().isoformat(), src, 0.97)
            elif action == "last changed":
                f.event(EventKind.DOMAIN, f"Domain {target} registration updated", when, src, entity=dom)
        for ent in d.get("entities") or []:
            if "registrar" in (ent.get("roles") or []):
                name = _vcard_fn(ent.get("vcardArray"))
                if name:
                    f.observe(dom, "registrar", name, src, 0.95)
        for ns in d.get("nameservers") or []:
            if ns.get("ldhName"):
                f.observe(dom, "nameserver", ns["ldhName"].lower(), src, 0.9)
        for status in d.get("status") or []:
            f.observe(dom, "registry_status", status, src, 0.9)
        return ConnectorResult(RunStatus.FOUND, f)


def _vcard_fn(vcard: Any) -> str | None:
    try:
        for prop in vcard[1]:
            if prop[0] == "fn":
                return str(prop[3]) or None
    except (TypeError, IndexError):
        pass
    return None


class CertificatesConnector(_DomainConnector):
    name = "certificates"
    label = "Certificate Transparency"
    category = SourceCategory.CERTIFICATE
    reliability = Reliability.HIGH
    description = "Certificates and subdomains from public Certificate Transparency logs (crt.sh)."
    timeout = 60.0
    MAX_SUBDOMAINS = 40
    MAX_CERTS = 5

    def targets(self, seed: Classification) -> list[str]:
        return [registrable_domain(t) for t in super().targets(seed)]

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> list[dict[str, Any]]:
        try:
            resp = await ctx.http.get("https://crt.sh/", params={"q": f"%.{target}", "output": "json"},
                                      max_bytes=8_000_000, timeout=55.0)
        except ResponseTooLarge as exc:
            raise ConnectorError("Too many certificates to process for this domain.") from exc
        check_status(resp, self.label)
        return resp.json() if resp.content.strip() else []

    def normalize(self, raw: list[dict[str, Any]], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No certificates found in CT logs.")
        dom = domain_ref(f, target)
        src = f.source(name="crt.sh", category=self.category, kind="ct_log_search",
                       url=f"https://crt.sh/?q=%25.{target}", reliability=self.reliability,
                       title=f"Certificate Transparency search for {target}")
        names: set[str] = set()
        issuers: set[str] = set()
        for cert in raw:
            for n in str(cert.get("name_value", "")).splitlines():
                n = n.strip().lower().lstrip("*.")
                if n.endswith(target) and n != target and "@" not in n:
                    names.add(n)
            if cert.get("issuer_name"):
                issuers.add(_issuer_org(cert["issuer_name"]))
        for name in sorted(names)[: self.MAX_SUBDOMAINS]:
            sub = domain_ref(f, name)
            f.relate(sub, dom, RelType.PART_OF, src, 0.9)
        for issuer in sorted(issuers)[:10]:
            f.observe(dom, "certificate_issuer", issuer, src, 0.9)
        dated = sorted((c for c in raw if parse_datetime(c.get("not_before"))),
                       key=lambda c: parse_datetime(c["not_before"]))
        if dated:
            first = dated[0]
            f.event(EventKind.CERTIFICATE, f"Earliest logged certificate for {target}",
                    parse_datetime(first["not_before"]), src, entity=dom, detail=_issuer_org(first.get("issuer_name", "")))
        for cert in dated[-self.MAX_CERTS:]:
            cref = f.entity(EntityKind.CERTIFICATE, f"crtsh:{cert['id']}", cert.get("common_name") or f"Certificate {cert['id']}",
                            url=f"https://crt.sh/?id={cert['id']}", issuer=_issuer_org(cert.get("issuer_name", "")),
                            not_before=cert.get("not_before"), not_after=cert.get("not_after"))
            f.relate(dom, cref, RelType.ASSOCIATED_WITH, src, 0.95)
        f.observe(dom, "subdomain_count", str(len(names)), src, 0.85, link=False)
        return ConnectorResult(RunStatus.FOUND, f)


def _issuer_org(issuer: str) -> str:
    for part in issuer.split(","):
        k, _, v = part.strip().partition("=")
        if k == "O":
            return v.strip('"')
    return issuer[:120]


class WaybackConnector(Connector):
    name = "wayback"
    label = "Wayback Machine"
    category = SourceCategory.ARCHIVE
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.DOMAIN, SeedType.URL})
    accepts_pivots = frozenset({"website"})
    description = "First and latest public captures from the Internet Archive (CDX API)."
    timeout = 75.0
    CDX = "https://web.archive.org/cdx/search/cdx"

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        key = normalize_url(target)
        out = {}
        for label, limit in (("first", 1), ("last", -1)):
            resp = await ctx.http.get(self.CDX, params={
                "url": key, "output": "json", "limit": limit, "fl": "timestamp,original,statuscode",
                "filter": "statuscode:200",
            }, timeout=35.0)
            check_status(resp, self.label)
            rows = resp.json() if resp.content.strip() else []
            out[label] = rows[1] if len(rows) > 1 else None
        return out

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw.get("first"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No archived captures found.")
        key = normalize_url(target)
        # Domain seeds attach to the domain; URL seeds and website pivots attach to the website.
        ent = domain_ref(f, key) if seed_type == SeedType.DOMAIN else f.entity(EntityKind.WEBSITE, key, key)
        src = f.source(name=self.label, category=self.category, kind="archive_index",
                       url=f"https://web.archive.org/web/*/{key}", reliability=self.reliability,
                       title=f"Wayback Machine captures of {key}")
        for label, row in raw.items():
            if not row:
                continue
            ts = parse_datetime(f"{row[0][:4]}-{row[0][4:6]}-{row[0][6:8]}T{row[0][8:10]}:{row[0][10:12]}:00+00:00")
            f.observe(ent, f"{label}_archived", ts.date().isoformat() if ts else row[0], src, 0.95)
            title = f"{key} first archived" if label == "first" else f"{key} most recently archived"
            f.event(EventKind.ARCHIVE, title, ts, src, entity=ent)
        return ConnectorResult(RunStatus.FOUND, f)
