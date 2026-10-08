"""Value normalization: one canonical form per attribute, regardless of which source said it."""

import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

import tldextract

# Bundled public-suffix snapshot only: never fetch the list over the network at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

_ORG_SUFFIXES = re.compile(
    r"[,.]?\s+(inc|inc\.|llc|ltd|ltd\.|limited|corp|corp\.|corporation|gmbh|co|co\.|plc|pvt|s\.a\.)$", re.I
)
_WS = re.compile(r"\s+")


def collapse_ws(value: str) -> str:
    return _WS.sub(" ", value).strip()


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


@lru_cache(maxsize=4096)
def public_suffix_known(host: str) -> bool:
    parts = _extract(host.lower().rstrip("."))
    return bool(parts.suffix and parts.domain)


def registrable_domain(host: str) -> str:
    parts = _extract(host.lower().rstrip("."))
    if not parts.suffix or not parts.domain:
        return host.lower()
    return f"{parts.domain}.{parts.suffix}"


def normalize_domain(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if "://" in host:
        host = urlsplit(host).hostname or ""
    host = host.split("/", 1)[0].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return host


def normalize_url(value: str, *, keep_scheme: bool = False) -> str:
    """Canonical URL. Default form drops scheme/www/trailing slash for equality checks."""
    raw = value.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower() if parts.scheme in ("http", "https") else "https"
    host = normalize_domain(parts.hostname or "")
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = parts.path.rstrip("/")
    if keep_scheme:
        netloc = (parts.hostname or "").lower() + port
        return urlunsplit((scheme, netloc, path or "/", parts.query, ""))
    return f"{host}{port}{path}" + (f"?{parts.query}" if parts.query else "")


def normalize_email(value: str) -> str:
    v = value.strip()
    if v.lower().startswith("mailto:"):
        v = v[7:]
    return v.split("?", 1)[0].strip().lower()


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def normalize_name(value: str) -> str:
    return collapse_ws(strip_accents(value)).casefold()


def normalize_org(value: str) -> str:
    v = collapse_ws(value).lstrip("@")
    v = _ORG_SUFFIXES.sub("", v)
    return strip_accents(v).casefold().strip(" ,.")


def normalize_value(attribute: str, value: str) -> str:
    match attribute:
        case "email":
            return normalize_email(value)
        case "website" | "url" | "avatar":
            return normalize_url(value)
        case "domain" | "nameserver" | "mail_server":
            return normalize_domain(value)
        case "username" | "alias":
            return normalize_username(value)
        case "name":
            return normalize_name(value)
        case "organization":
            return normalize_org(value)
        case "linked_account":
            platform, _, handle = value.partition(":")
            return f"{platform.strip().lower()}:{normalize_username(handle)}"
        case _:
            return collapse_ws(value).casefold()
