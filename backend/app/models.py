"""Persistence model.

The schema is deliberately observation-centric: nothing stores "the truth" about a
subject. Entities are thin anchors (a profile, an email, a domain...). Everything we
believe about them is an Observation that points to the Source it came from, so every
displayed fact can be traced back to provenance.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class TZDateTime(TypeDecorator):
    """Timezone-aware datetime that round-trips as UTC on SQLite too."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="analyst")  # "admin" | "analyst"
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AuthSession(Base):
    """Server-side session. Only a SHA-256 of the cookie token is stored."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime(), index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    seed: Mapped[str] = mapped_column(String(512))
    seed_normalized: Mapped[str] = mapped_column(String(512), index=True)
    seed_type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    # Completion time of the run before the latest one: anything created after it is "new".
    previous_completed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Job queue: a worker claims a pending investigation and heartbeats while running.
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    # Monitoring: re-run automatically every N hours when set.
    monitor_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, index=True)

    runs: Mapped[list["ConnectorRun"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="ConnectorRun.created_at"
    )


class ConnectorRun(Base):
    """One execution of one connector against one target. Failures are stored, not raised."""

    __tablename__ = "connector_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    connector: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(512))
    phase: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    investigation: Mapped[Investigation] = relationship(back_populates="runs")


class Source(Base):
    """A concrete retrieval: which URL/API was queried, when, and how reliable it is."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("connector_runs.id", ondelete="SET NULL"), nullable=True)
    connector: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reliability: Mapped[str] = mapped_column(String(16))
    collected_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("investigation_id", "kind", "key", name="uq_entity_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(512))
    # Display hints only (platform name, profile URL). Never facts — facts are observations.
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_seed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Observation(Base):
    """'Source S said attribute A of entity E has value V, at time T, with confidence C.'"""

    __tablename__ = "observations"
    __table_args__ = (Index("ix_obs_entity_attr", "entity_id", "attribute"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    attribute: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("src_entity_id", "dst_entity_id", "type", name="uq_relationship"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    src_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    dst_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    # Null only for relationships inferred by the resolver (those carry factors in `data`).
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class EntityMatch(Base):
    """Resolver output: how strongly a discovered profile is linked to the investigation subject."""

    __tablename__ = "entity_matches"
    __table_args__ = (UniqueConstraint("investigation_id", "entity_id", name="uq_entity_match"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(32))
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Profiles connected by strong mutual evidence share a cluster; 0 is the subject's cluster.
    cluster: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Mention(Base):
    """A public reference. Stores metadata + a short snippet only, never full content."""

    __tablename__ = "mentions"
    __table_args__ = (UniqueConstraint("investigation_id", "url", name="uq_mention_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(512))
    snippet: Mapped[str | None] = mapped_column(String(400), nullable=True)
    association: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (UniqueConstraint("investigation_id", "dedupe_key", name="uq_timeline_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(512))
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime(), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(1024))


class AccessLog(Base):
    """Audit trail of every outbound source access."""

    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    connector: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(8))
    url: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class AnalystDecision(Base):
    """A human verdict on whether a profile belongs to the subject. Overrides the resolver."""

    __tablename__ = "analyst_decisions"
    __table_args__ = (UniqueConstraint("entity_id", name="uq_decision_entity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    decision: Mapped[str] = mapped_column(String(16))  # "confirmed" | "rejected"
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class InvestigationNote(Base):
    __tablename__ = "investigation_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class AuditEvent(Base):
    """Who did what in the console (logins, investigations created/deleted, decisions)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)


class BootstrapLock(Base):
    """Singleton settings row (key='bootstrap').

    Its creation serializes first-admin registration: `INSERT ... ON CONFLICT DO NOTHING` takes
    a write lock that concurrent bootstrap requests queue behind, so two racing registrations
    can't both observe zero users and both mint an admin. The 'allow_registration' value mirrors
    the OSINT_ALLOW_REGISTRATION setting and can be flipped at runtime by an admin.
    """

    __tablename__ = "bootstrap_lock"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    allow_registration: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
