"""Infrastructure intelligence: email domains, IP addresses, security.txt."""

from typing import Any

from app.connectors.base import (
    FREEMAIL_DOMAINS, Connector, ConnectorContext, ConnectorError, ConnectorResult, EntityRef, Findings, check_status,
    domain_of_seed,
)
from app.connectors.domain import DOMAIN_SEEDS, vcard_fn, domain_ref
from app.core.classify import Classification
from app.core.enums import EntityKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.net import UnsafeURLError

DOH = "https://cloudflare-dns.com/dns-query"
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "getnada.com", "sharklasers.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
})


class EmailIntelConnector(Connector):
    """Facts about an email address that don't require contacting its owner: provider type and
    whether the domain accepts mail (MX). No SMTP probing, no breach lookups."""

    name = "email_intel"
    label = "Email domain"
    category = SourceCategory.DNS
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.EMAIL})
    description = "Email provider classification and MX/SPF/DMARC of the address's domain (no mailbox probing)."

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        domain = target.rsplit("@", 1)[1]
        out: dict[str, Any] = {"domain": domain}
        for rtype, name in (("MX", domain), ("TXT", domain), ("TXT", f"_dmarc.{domain}")):
            resp = await ctx.http.get(DOH, params={"name": name, "type": rtype}, headers={"Accept": "application/dns-json"})
            check_status(resp, self.label)
            out[f"{rtype}:{name}"] = resp.json()
        return out

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        domain = raw["domain"]
        email = f.entity(EntityKind.EMAIL, target, target)
        src = f.source(name="DNS (DoH)", category=self.category, kind="dns_records", url=f"{DOH}?name={domain}&type=MX",
                       reliability=self.reliability, title=f"Mail configuration for {domain}")
        provider = ("disposable" if domain in DISPOSABLE_DOMAINS else
                    "free webmail" if domain in FREEMAIL_DOMAINS else "custom domain")
        f.observe(email, "email_provider", provider, src, 0.95)
        f.observe(email, "domain", domain, src, 0.99)
        if provider == "custom domain":
            f.relate(email, domain_ref(f, domain), RelType.PART_OF, src, 0.99)
        mx = [a.get("data", "") for a in raw.get(f"MX:{domain}", {}).get("Answer") or [] if a.get("type") == 15]
        f.observe(email, "domain_accepts_mail", "yes" if mx else "no (no MX records)", src, 0.95)
        for rec in mx[:5]:
            f.observe(email, "mail_server", rec.split()[-1].rstrip("."), src, 0.95, link=False)
        for a in raw.get(f"TXT:{domain}", {}).get("Answer") or []:
            data = str(a.get("data", "")).strip('"')
            if data.startswith("v=spf1"):
                f.observe(email, "spf", data, src, 0.9)
        for a in raw.get(f"TXT:_dmarc.{domain}", {}).get("Answer") or []:
            data = str(a.get("data", "")).strip('"')
            if data.startswith("v=DMARC1"):
                f.observe(email, "dmarc", data, src, 0.9)
        return ConnectorResult(RunStatus.FOUND, f)


class IpIntelConnector(Connector):
    """Network ownership (RDAP) and passively-collected exposure (Shodan InternetDB) for IPs the
    DNS connector resolved. Nothing is scanned by us."""

    name = "ip_intel"
    label = "IP intelligence"
    category = SourceCategory.DNS
    reliability = Reliability.HIGH
    supports = frozenset()
    accepts_pivots = frozenset({"ip"})
    description = "Network owner, ASN range and country (RDAP) plus publicly indexed open ports (Shodan InternetDB)."

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        out: dict[str, Any] = {"ip": target}
        rdap = await ctx.http.get(f"https://rdap.org/ip/{target}", headers={"Accept": "application/rdap+json"})
        if check_status(rdap, "RDAP"):
            out["rdap"] = rdap.json()
            out["rdap_url"] = rdap.url
        idb = await ctx.http.get(f"https://internetdb.shodan.io/{target}")
        if idb.status_code == 200:
            out["internetdb"] = idb.json()
        elif idb.status_code not in (404,):
            check_status(idb, "Shodan InternetDB")
        return out

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        ip = f.entity(EntityKind.IP, target, target)
        if rd := raw.get("rdap"):
            src = f.source(name="RDAP", category=SourceCategory.DOMAIN, kind="ip_registration", url=raw["rdap_url"],
                           reliability=self.reliability, title=f"IP registration for {target}")
            f.observe(ip, "network_name", rd.get("name"), src, 0.95)
            f.observe(ip, "country", rd.get("country"), src, 0.9)
            if rd.get("startAddress") and rd.get("endAddress"):
                f.observe(ip, "network_range", f"{rd['startAddress']} – {rd['endAddress']}", src, 0.95)
            for ent in rd.get("entities") or []:
                if "registrant" in (ent.get("roles") or []):
                    name = vcard_fn(ent.get("vcardArray"))
                    if name:
                        org = f.entity(EntityKind.ORGANIZATION, name.lower(), name)
                        f.relate(ip, org, RelType.OWNS, src, 0.9)
                        f.observe(ip, "network_owner", name, src, 0.9)
        if idb := raw.get("internetdb"):
            src = f.source(name="Shodan InternetDB", category=SourceCategory.DNS, kind="passive_scan_index",
                           url=f"https://internetdb.shodan.io/{target}", reliability=Reliability.MEDIUM,
                           title=f"Publicly indexed services on {target}")
            for port in (idb.get("ports") or [])[:30]:
                f.observe(ip, "open_port", str(port), src, 0.8)
            for host in (idb.get("hostnames") or [])[:20]:
                f.observe(ip, "reverse_hostname", host, src, 0.8)
            for cpe in (idb.get("cpes") or [])[:20]:
                f.observe(ip, "technology", cpe, src, 0.7)
            for tag in (idb.get("tags") or [])[:10]:
                f.observe(ip, "tag", tag, src, 0.7)
            for vuln in (idb.get("vulns") or [])[:20]:
                f.observe(ip, "known_vulnerability", vuln, src, 0.6)
        if f.is_empty or not f.observations:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No public registration or exposure data.")
        return ConnectorResult(RunStatus.FOUND, f)


class SecurityTxtConnector(Connector):
    """RFC 9116 security.txt: contacts an organization publishes specifically to be contacted."""

    name = "security_txt"
    label = "security.txt"
    category = SourceCategory.DOMAIN
    reliability = Reliability.HIGH
    supports = DOMAIN_SEEDS
    description = "Security contacts and disclosure policy published via RFC 9116 security.txt."

    def targets(self, seed: Classification) -> list[str]:
        domain = domain_of_seed(seed)
        return [domain] if domain else []

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> dict[str, Any]:
        for url in (f"https://{target}/.well-known/security.txt", f"https://{target}/security.txt"):
            try:
                resp = await ctx.http.get(url, max_bytes=100_000)
            except UnsafeURLError as exc:
                raise ConnectorError(f"Refused: {exc}") from exc
            if resp.status_code == 200 and "text/plain" in resp.content_type:
                return {"url": resp.url, "text": resp.text}
        return {"text": None}

    def normalize(self, raw: dict[str, Any], target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if not raw.get("text"):
            return ConnectorResult(RunStatus.NOT_FOUND, f, "No security.txt published.")
        dom: EntityRef = domain_ref(f, target)
        src = f.source(name="security.txt", category=self.category, kind="security_txt", url=raw["url"],
                       reliability=self.reliability, title=f"security.txt for {target}")
        fields = {"contact": "security_contact", "policy": "security_policy", "expires": "security_txt_expires",
                  "hiring": "security_hiring", "acknowledgments": "security_acknowledgments"}
        for line in raw["text"].splitlines():
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key in fields and value and not line.lstrip().startswith("#"):
                if key == "contact" and value.lower().startswith("mailto:"):
                    f.observe(dom, "email", value[7:], src, 0.95)
                f.observe(dom, fields[key], value, src, 0.95, link=False)
        if not f.observations:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "security.txt had no recognised fields.")
        return ConnectorResult(RunStatus.FOUND, f)
