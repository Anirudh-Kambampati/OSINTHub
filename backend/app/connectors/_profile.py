"""Shared emitter for 'public profile on platform X' connectors, so every platform
normalizes into the same attribute vocabulary."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.connectors.base import EntityRef, Findings, Pivot, profile_ref
from app.connectors.social import PLATFORM_LABELS
from app.core.enums import EventKind, Reliability, SourceCategory


@dataclass
class PublicProfile:
    platform: str
    username: str
    url: str
    name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    email: str | None = None
    organization: str | None = None
    occupation: str | None = None
    avatar: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Accounts this profile itself claims/links, as "platform:handle".
    linked_accounts: list[str] = field(default_factory=list)
    # Accounts verified by the platform (e.g. Keybase cryptographic proofs).
    verified_accounts: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def emit_profile(
    f: Findings,
    p: PublicProfile,
    *,
    category: SourceCategory,
    reliability: Reliability,
    source_url: str | None = None,
    confidence: float = 0.9,
) -> tuple[EntityRef, int]:
    label = PLATFORM_LABELS.get(p.platform, p.platform)
    src = f.source(
        name=label, category=category, kind="public_profile", url=source_url or p.url,
        reliability=reliability, title=f"{label} public profile @{p.username}",
    )
    key = profile_ref(p.platform, p.username)
    ref = f.entity(
        key.kind, key.key, f"@{p.username}",
        platform=p.platform, platform_label=label, url=p.url, stats=p.stats or None,
    )
    f.observe(ref, "username", p.username, src, min(0.99, confidence + 0.09))
    f.observe(ref, "name", p.name, src, confidence)
    f.observe(ref, "email", p.email, src, confidence)
    f.observe(ref, "website", p.website, src, confidence)
    f.observe(ref, "organization", p.organization, src, confidence - 0.05)
    f.observe(ref, "occupation", p.occupation, src, confidence - 0.1)
    f.observe(ref, "location", p.location, src, confidence - 0.1)
    f.observe(ref, "bio", p.bio, src, confidence - 0.1)
    f.observe(ref, "avatar", p.avatar, src, confidence)
    for account in dict.fromkeys(p.verified_accounts):
        f.observe(ref, "linked_account", account, src, 0.97)
    for account in dict.fromkeys(p.linked_accounts):
        if account not in p.verified_accounts:
            f.observe(ref, "linked_account", account, src, confidence - 0.05)
    f.event(EventKind.PROFILE, f"{label} account created", p.created_at, src, entity=ref, detail=f"@{p.username}")
    f.event(EventKind.PROFILE, f"{label} profile updated", p.updated_at, src, entity=ref, detail=f"@{p.username}")
    return ref, src


def website_pivots(*urls: str | None) -> list[Pivot]:
    return [Pivot("website", u if "://" in u else "https://" + u) for u in urls if u]
