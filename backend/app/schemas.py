from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import SeedType


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClassifyIn(BaseModel):
    value: str = Field(max_length=512)


class ClassifyOut(BaseModel):
    valid: bool
    type: SeedType | None = None
    normalized: str | None = None
    alternatives: list[SeedType] = []
    error: str | None = None


class InvestigationCreate(BaseModel):
    seed: str = Field(min_length=1, max_length=512)
    seed_type: SeedType | None = None


class SourceOut(_Out):
    id: str
    connector: str
    name: str
    category: str
    kind: str
    url: str
    title: str | None
    reliability: str
    collected_at: datetime


class RunOut(_Out):
    id: str
    connector: str
    label: str
    category: str
    target: str
    phase: int
    status: str
    message: str | None
    manual_url: str | None
    result_count: int
    started_at: datetime | None
    finished_at: datetime | None


class Stats(BaseModel):
    profiles: int
    matched_profiles: int
    mentions: int
    sources: int
    relationships: int
    documents: int
    domains: int
    entities: int
    connectors_run: int
    connectors_total: int
    confidence: float | None
    level: str | None


class InvestigationOut(_Out):
    id: str
    seed: str
    seed_type: SeedType
    title: str
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    stats: Stats


class InvestigationDetail(InvestigationOut):
    runs: list[RunOut]


class FactorOut(BaseModel):
    code: str
    label: str
    weight: float
    related_entity_id: str | None = None


class MatchOut(BaseModel):
    score: float
    level: str
    label: str
    factors: list[FactorOut]


class EntityOut(BaseModel):
    id: str
    kind: str
    key: str
    label: str
    confidence: float
    level: str
    is_seed: bool
    data: dict[str, Any]
    match: MatchOut | None = None
    avatar_observation_id: str | None = None


class EntityRefOut(BaseModel):
    id: str
    kind: str
    label: str
    platform: str | None = None
    confidence: float | None = None


class EvidenceItem(BaseModel):
    observation_id: str
    value: str
    confidence: float
    weight: float
    observed_at: datetime
    source: SourceOut
    entity: EntityRefOut


class IdentityAttribute(BaseModel):
    attribute: str
    value: str
    normalized_value: str
    confidence: float
    level: str
    first_observed: datetime
    last_observed: datetime
    source_count: int
    evidence: list[EvidenceItem]


class ImageOut(BaseModel):
    observation_id: str
    original_url: str
    confidence: float
    level: str
    first_observed: datetime
    last_observed: datetime
    source: SourceOut
    entity: EntityRefOut


class PresenceOut(BaseModel):
    connector: str
    label: str
    category: str
    status: str
    message: str | None
    manual_url: str | None
    target: str
    profile: EntityOut | None = None


class ProfileView(BaseModel):
    subject: EntityOut
    seed_entity_id: str | None
    confidence: float | None
    level: str | None
    images: list[ImageOut]
    attributes: list[IdentityAttribute]
    presence: list[PresenceOut]
    profiles: list[EntityOut]


class MentionOut(BaseModel):
    id: str
    url: str
    title: str
    snippet: str | None
    category: str
    association: str
    published_at: datetime | None
    observed_at: datetime
    confidence: float
    level: str
    source: SourceOut
    entity: EntityRefOut | None


class MentionPage(BaseModel):
    total: int
    counts: dict[str, int]
    items: list[MentionOut]


class TimelineEventOut(BaseModel):
    id: str
    kind: str
    title: str
    detail: str | None
    occurred_at: datetime
    source: SourceOut
    entity: EntityRefOut | None


class GraphNode(BaseModel):
    id: str
    kind: str
    label: str
    confidence: float
    level: str
    is_seed: bool
    is_subject: bool
    data: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    confidence: float
    inferred: bool


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


class ObservationOut(BaseModel):
    id: str
    attribute: str
    value: str
    confidence: float
    observed_at: datetime
    source: SourceOut


class RelationshipOut(BaseModel):
    id: str
    type: str
    direction: str
    other: EntityRefOut
    confidence: float
    inferred: bool
    data: dict[str, Any]
    source: SourceOut | None


class EntityEvidence(BaseModel):
    entity: EntityOut
    observations: list[ObservationOut]
    relationships: list[RelationshipOut]
    mentions: int


class ConnectorInfo(BaseModel):
    name: str
    label: str
    category: str
    reliability: str
    supports: list[SeedType]
    accepts_pivots: list[str]
    description: str
    configured: bool
    requires: list[str]
