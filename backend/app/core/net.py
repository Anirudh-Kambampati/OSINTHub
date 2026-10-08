"""Outbound HTTP with SSRF protection, size caps, per-host politeness and an access log.

Every connector goes through `SourceHttp`. It refuses non-public destinations
(loopback, RFC1918, link-local/metadata, reserved, multicast), re-validates every
redirect hop, caps response sizes, and records each request for the audit log.
"""

import asyncio
import base64
import ipaddress
import socket
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.config import Settings

ALLOWED_PORTS = {None, 80, 443}
MAX_REDIRECTS = 5
TRANSIENT_STATUSES = {502, 503, 504}
RETRY_DELAY = 1.5
CREDENTIAL_HEADERS = {"authorization", "x-subscription-token", "cookie"}


class UnsafeURLError(ValueError):
    pass


class ResponseTooLarge(Exception):
    pass


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def validate_public_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is http(s) on a standard port and resolves only to public IPs."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError(f"Malformed URL: {exc}") from exc
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http(s) URLs are allowed.")
    if parts.username or parts.password:
        raise UnsafeURLError("URLs with embedded credentials are not allowed.")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host.")
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError("Only ports 80 and 443 are allowed.")
    if host.endswith((".local", ".internal", ".localhost")) or host == "localhost":
        raise UnsafeURLError("Internal hostnames are not allowed.")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"Could not resolve host {host}.") from exc
        addresses = list({info[4][0] for info in infos})
    if not addresses or not all(_ip_is_public(a) for a in addresses):
        raise UnsafeURLError(f"Host {host} resolves to a non-public address.")


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import json

        return json.loads(self.content)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


@dataclass
class AccessRecord:
    connector: str
    method: str
    url: str
    status_code: int | None
    error: str | None
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


class HostLimiter:
    """At most N concurrent requests per host across the whole process."""

    def __init__(self, per_host: int = 2) -> None:
        self._sems: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(per_host))

    def for_url(self, url: str) -> asyncio.Semaphore:
        return self._sems[(urlsplit(url).hostname or "").lower()]


class SourceHttp:
    """HTTP facade handed to connectors. One per connector run."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        limiter: HostLimiter,
        connector: str,
        log: list[AccessRecord],
    ) -> None:
        self._client = client
        self._settings = settings
        self._limiter = limiter
        self._connector = connector
        self.log = log

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
        check_public: bool = True,
        timeout: float | None = None,
    ) -> FetchResult:
        return await self.request("GET", url, params=params, headers=headers, max_bytes=max_bytes,
                                  check_public=check_public, timeout=timeout)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: Any = None,
        auth: tuple[str, str] | None = None,
        max_bytes: int | None = None,
        check_public: bool = True,
        timeout: float | None = None,
    ) -> FetchResult:
        """Send a request; idempotent GETs get one polite retry on transient upstream 5xx (never on 429)."""
        kwargs = dict(params=params, headers=headers, data=data, auth=auth, max_bytes=max_bytes,
                      check_public=check_public, timeout=timeout)
        result = await self._request_once(method, url, **kwargs)
        if method == "GET" and result.status_code in TRANSIENT_STATUSES:
            await asyncio.sleep(RETRY_DELAY)
            result = await self._request_once(method, url, **kwargs)
        return result

    async def _request_once(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        data: Any,
        auth: tuple[str, str] | None,
        max_bytes: int | None,
        check_public: bool,
        timeout: float | None,
    ) -> FetchResult:
        limit = max_bytes or self._settings.max_html_bytes
        hdrs = {"User-Agent": self._settings.user_agent, **(headers or {})}
        if auth:
            hdrs["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if check_public:
                await validate_public_url(current)
            try:
                async with self._limiter.for_url(current):
                    req = self._client.build_request(
                        method, current, params=params, headers=hdrs, data=data,
                        timeout=timeout or self._settings.http_timeout,
                    )
                    resp = await self._client.send(req, stream=True, follow_redirects=False)
                    try:
                        if resp.is_redirect and "location" in resp.headers:
                            self._record(method, str(req.url), resp.status_code, None)
                            nxt = urljoin(str(req.url), resp.headers["location"])
                            if urlsplit(nxt).netloc.lower() != urlsplit(str(req.url)).netloc.lower():
                                # Never forward credentials to a different host.
                                hdrs = {k: v for k, v in hdrs.items() if k.lower() not in CREDENTIAL_HEADERS}
                            current = nxt
                            params = None
                            continue
                        declared = int(resp.headers.get("content-length") or 0)
                        if declared > limit:
                            raise ResponseTooLarge(f"Response exceeds {limit} bytes")
                        body = bytearray()
                        async for chunk in resp.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > limit:
                                raise ResponseTooLarge(f"Response exceeds {limit} bytes")
                    finally:
                        await resp.aclose()
            except (httpx.HTTPError, ResponseTooLarge) as exc:
                self._record(method, current, None, f"{type(exc).__name__}: {exc}"[:500])
                raise
            self._record(method, str(req.url), resp.status_code, None)
            return FetchResult(str(req.url), resp.status_code, resp.headers, bytes(body))
        raise UnsafeURLError("Too many redirects.")

    def _record(self, method: str, url: str, status: int | None, error: str | None) -> None:
        self.log.append(AccessRecord(self._connector, method, redact_url(url)[:2048], status, error))


SECRET_PARAMS = {"key", "api_key", "apikey", "token", "access_token", "client_secret", "secret"}


def redact_url(url: str) -> str:
    """Strip credential-like query parameters before a URL is logged or stored."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [
        (k, "REDACTED" if k.lower() in SECRET_PARAMS else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
