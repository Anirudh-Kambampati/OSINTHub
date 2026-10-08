from enum import StrEnum


class SeedType(StrEnum):
    USERNAME = "username"
    EMAIL = "email"
    PERSON = "person"
    DOMAIN = "domain"
    URL = "url"


class InvestigationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"  # finished, but at least one connector errored / was rate limited
    FAILED = "failed"


class RunStatus(StrEnum):
    """Per-connector outcome. Errors are never collapsed into NOT_FOUND."""

    PENDING = "pending"
    RUNNING = "running"
    FOUND = "found"
    NOT_FOUND = "not_found"
    NOT_VERIFIED = "not_verified"  # source exists but cannot be legitimately queried
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    REQUIRES_AUTH = "requires_auth"
    SKIPPED = "skipped"


TERMINAL_RUN_STATUSES = {
    RunStatus.FOUND,
    RunStatus.NOT_FOUND,
    RunStatus.NOT_VERIFIED,
    RunStatus.ERROR,
    RunStatus.RATE_LIMITED,
    RunStatus.REQUIRES_AUTH,
    RunStatus.SKIPPED,
}
DEGRADED_RUN_STATUSES = {RunStatus.ERROR, RunStatus.RATE_LIMITED}


class SourceCategory(StrEnum):
    SOCIAL = "social"
    CODE = "code"
    WEB = "web"
    SEARCH = "search"
    DOMAIN = "domain"
    DNS = "dns"
    CERTIFICATE = "certificate"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    NEWS = "news"
    IDENTITY = "identity"


class Reliability(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


RELIABILITY_WEIGHT = {Reliability.LOW: 0.6, Reliability.MEDIUM: 0.8, Reliability.HIGH: 0.95}


class EntityKind(StrEnum):
    PERSON = "person"
    USERNAME = "username"
    EMAIL = "email"
    PHONE = "phone"
    PROFILE = "profile"
    ORGANIZATION = "organization"
    WEBSITE = "website"
    DOMAIN = "domain"
    REPOSITORY = "repository"
    DOCUMENT = "document"
    IMAGE = "image"
    IP = "ip"
    CERTIFICATE = "certificate"
    LOCATION = "location"


class RelType(StrEnum):
    OWNS = "OWNS"
    USES = "USES"
    MENTIONS = "MENTIONS"
    LINKS_TO = "LINKS_TO"
    WORKS_AT = "WORKS_AT"
    AUTHORED = "AUTHORED"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    FOUND_ON = "FOUND_ON"
    HOSTED_ON = "HOSTED_ON"
    LOCATED_IN = "LOCATED_IN"
    PART_OF = "PART_OF"


class EventKind(StrEnum):
    PROFILE = "profile"
    MENTION = "mention"
    REPOSITORY = "repository"
    DOCUMENT = "document"
    DOMAIN = "domain"
    ORGANIZATION = "organization"
    CERTIFICATE = "certificate"
    ARCHIVE = "archive"
