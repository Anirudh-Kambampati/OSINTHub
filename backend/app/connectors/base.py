"""Connector contract.

A connector turns one target (username, email, domain...) into normalized `Findings`:
sources it actually queried, entities, observations, relationships, mentions and
timeline events. Connectors never touch the database; the store persists findings.

To add a source: subclass `Connector`, implement `fetch` (network) and `normalize`
(pure; unit-testable with fixtures), and register it in `registry.py`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from app.config import Settings
from app.core.enums import EntityKind, EventKind, Reliability, RelType, RunStatus, SeedType, SourceCategory
from app.core.net import SourceHttp
from app.core.classify import Classification
from app.core.normalize import normalize_domain, normalize_value
from app.core.text import clean_text


class ConnectorError(Exception):
    status = RunStatus.ERROR


class RateLimited(ConnectorError):
    status = RunStatus.RATE_LIMITED


class AuthRequired(ConnectorError):
    status = RunStatus.REQUIRES_AUTH


class NotVerifiable(ConnectorError):
    status = RunStatus.NOT_VERIFIED


@dataclass(frozen=True)
class EntityRef:
    kind: EntityKind
    key: str


@dataclass
class EntityRecord:
    ref: EntityRef
    label: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceRecord:
    ref: int
    name: str
    category: SourceCategory
    kind: str
    url: str
    reliability: Reliability
    title: str | None = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ObservationRecord:
    entity: EntityRef
    attribute: str
    value: str
    normalized_value: str
    source: int
    confidence: float


@dataclass
class RelationshipRecord:
    src: EntityRef
    dst: EntityRef
    type: RelType
    source: int
    confidence: float


@dataclass
class MentionRecord:
    url: str
    title: str
    snippet: str | None
    category: SourceCategory
    association: str
    source: int
    confidence: float
    entity: EntityRef | None = None
    published_at: datetime | None = None


@dataclass
class EventRecord:
    kind: EventKind
    title: str
    occurred_at: datetime
    source: int
    entity: EntityRef | None = None
    detail: str | None = None


def profile_ref(platform: str, username: str) -> EntityRef:
    return EntityRef(EntityKind.PROFILE, f"{platform}:{username.strip().lstrip('@').lower()}")


# Attributes whose values are themselves identifiers become graph entities automatically.
IDENTIFIER_ATTRIBUTES: dict[str, tuple[EntityKind, RelType]] = {
    "email": (EntityKind.EMAIL, RelType.USES),
    "username": (EntityKind.USERNAME, RelType.USES),
    "website": (EntityKind.WEBSITE, RelType.LINKS_TO),
    "organization": (EntityKind.ORGANIZATION, RelType.WORKS_AT),
    "ip_address": (EntityKind.IP, RelType.HOSTED_ON),
}


class Findings:
    """Accumulator connectors write into. Handles value normalization in one place."""

    def __init__(self, connector: str) -> None:
        self.connector = connector
        self.sources: list[SourceRecord] = []
        self.entities: dict[EntityRef, EntityRecord] = {}
        self.observations: list[ObservationRecord] = []
        self.relationships: list[RelationshipRecord] = []
        self.mentions: list[MentionRecord] = []
        self.events: list[EventRecord] = []

    # -- builders -------------------------------------------------------
    def source(
        self, *, name: str, category: SourceCategory, kind: str, url: str,
        reliability: Reliability, title: str | None = None,
    ) -> int:
        ref = len(self.sources)
        self.sources.append(SourceRecord(ref, name, category, kind, url, reliability, clean_text(title, 500)))
        return ref

    def entity(self, kind: EntityKind, key: str, label: str, **data: Any) -> EntityRef:
        ref = EntityRef(kind, key)
        existing = self.entities.get(ref)
        if existing:
            existing.data.update({k: v for k, v in data.items() if v is not None})
        else:
            self.entities[ref] = EntityRecord(ref, clean_text(label, 500) or key, {k: v for k, v in data.items() if v is not None})
        return ref

    def observe(
        self, entity: EntityRef, attribute: str, value: Any, source: int, confidence: float,
        *, link: bool = True,
    ) -> None:
        """Record an attribute observation. Identifier-valued attributes also become linked entities."""
        if value is None:
            return
        text = clean_text(str(value), 1000)
        if not text:
            return
        normalized = normalize_value(attribute, text)
        if not normalized:
            return
        self.observations.append(ObservationRecord(entity, attribute, text, normalized, source, _clamp(confidence)))
        if link and attribute in IDENTIFIER_ATTRIBUTES and entity.kind != IDENTIFIER_ATTRIBUTES[attribute][0]:
            kind, rel = IDENTIFIER_ATTRIBUTES[attribute]
            target = self.entity(kind, normalized, text)
            self.relate(entity, target, rel, source, confidence)

    def relate(self, src: EntityRef, dst: EntityRef, type: RelType, source: int, confidence: float) -> None:
        if src != dst:
            self.relationships.append(RelationshipRecord(src, dst, type, source, _clamp(confidence)))

    def mention(
        self, *, url: str, title: str, snippet: str | None, category: SourceCategory, association: str,
        source: int, confidence: float, entity: EntityRef | None = None, published_at: datetime | None = None,
    ) -> None:
        self.mentions.append(MentionRecord(
            url=url, title=clean_text(title, 500) or url, snippet=clean_text(snippet, 280),
            category=category, association=association, source=source, confidence=_clamp(confidence),
            entity=entity, published_at=published_at,
        ))

    def event(
        self, kind: EventKind, title: str, occurred_at: datetime | None, source: int,
        *, entity: EntityRef | None = None, detail: str | None = None,
    ) -> None:
        if occurred_at is not None:
            self.events.append(EventRecord(kind, clean_text(title, 500) or "", occurred_at, source, entity, clean_text(detail, 500)))

    @property
    def is_empty(self) -> bool:
        return not (self.entities or self.observations or self.mentions)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class ConnectorContext:
    http: SourceHttp
    settings: Settings


@dataclass(frozen=True)
class Pivot:
    """Something discovered that another connector can follow up on (e.g. a website, a PDF)."""

    kind: str  # "website" | "document"
    value: str


@dataclass
class ConnectorResult:
    status: RunStatus
    findings: Findings
    message: str | None = None
    pivots: list[Pivot] = field(default_factory=list)


FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com",
    "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "pm.me", "aol.com", "gmx.com",
    "gmx.net", "yandex.com", "yandex.ru", "mail.com", "zoho.com", "fastmail.com", "hey.com", "qq.com",
    "163.com", "web.de", "tutanota.com", "rediffmail.com",
})


def domain_of_seed(seed: Classification) -> str | None:
    """The domain a domain-level connector should examine for this seed, if any."""
    if seed.type == SeedType.DOMAIN:
        return seed.normalized
    if seed.type == SeedType.URL:
        return normalize_domain(seed.normalized)
    if seed.type == SeedType.EMAIL:
        domain = seed.normalized.rsplit("@", 1)[1]
        return None if domain in FREEMAIL_DOMAINS else domain
    return None


class Connector(ABC):
    name: ClassVar[str]
    label: ClassVar[str]
    category: ClassVar[SourceCategory]
    reliability: ClassVar[Reliability] = Reliability.MEDIUM
    supports: ClassVar[frozenset[SeedType]]
    description: ClassVar[str] = ""
    # Phase 1 connectors run on the seed. Phase 2 connectors run on pivots (websites/documents).
    phase: ClassVar[int] = 1
    # Names of settings fields required for this connector to query anything.
    requires: ClassVar[tuple[str, ...]] = ()
    # Pivot kinds this connector can follow up on in later phases.
    accepts_pivots: ClassVar[frozenset[str]] = frozenset()
    timeout: ClassVar[float | None] = None

    def targets(self, seed: Classification) -> list[str]:
        """Targets to run against for a seed. Empty list means 'not applicable'."""
        return [seed.normalized] if seed.type in self.supports else []

    def is_configured(self, settings: Settings) -> bool:
        return all(getattr(settings, field_name, None) for field_name in self.requires)

    def manual_url(self, target: str, seed_type: SeedType) -> str | None:
        """Public URL a human can open to check manually. Not evidence."""
        return None

    async def run(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> ConnectorResult:
        if not self.is_configured(ctx.settings):
            raise AuthRequired(
                f"{self.label} requires official API credentials ({', '.join(self.requires)}); "
                "configure them server-side to enable this source."
            )
        raw = await self.fetch(target, seed_type, ctx)
        return self.normalize(raw, target, seed_type)

    @abstractmethod
    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> Any:
        """Network access only. Raise ConnectorError subclasses for non-success states."""

    @abstractmethod
    def normalize(self, raw: Any, target: str, seed_type: SeedType) -> ConnectorResult:
        """Pure transformation of `raw` into findings."""


def check_status(resp, label: str, *, not_found: tuple[int, ...] = (404,)) -> bool:
    """Map HTTP status to connector states. Returns False for 'not found'."""
    if resp.status_code in not_found:
        return False
    if resp.status_code == 429:
        retry = resp.headers.get("retry-after")
        raise RateLimited(f"{label} rate limit reached" + (f"; retry after {retry}s." if retry else "."))
    if resp.status_code in (401, 403):
        if resp.headers.get("x-ratelimit-remaining") == "0":
            raise RateLimited(f"{label} rate limit reached.")
        raise AuthRequired(f"{label} refused anonymous access (HTTP {resp.status_code}).")
    if resp.status_code >= 400:
        raise ConnectorError(f"{label} returned HTTP {resp.status_code}.")
    return True
