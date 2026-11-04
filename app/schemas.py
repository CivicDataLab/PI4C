"""API response/request models. These are the contract downstream consumers build against."""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")

ReportStatus = Literal["new", "acknowledged", "in_progress", "resolved", "rejected"]
Severity = Literal["low", "medium", "high", "critical"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    kind: str
    mime_type: str | None
    caption: str | None

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/v1/reports/{self.report_id}/media/{self.id}"


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ref: str
    interaction_id: str
    created_at: datetime
    updated_at: datetime
    channel: str
    language: str
    category: str
    subcategory: str
    barrier_type: str
    municipal_subject: str | None
    department_id: str | None
    severity: str | None
    confidence: float | None
    classifier: str | None
    classifier_model: str | None
    summary_en: str | None
    needs_review: bool
    pwd_marker: bool
    affected: str
    description_raw: str | None
    description_type: str
    description_en: str | None
    latitude: float
    longitude: float
    location_name: str | None
    location_address: str | None
    location_route: str
    ward: str | None
    cluster_id: int | None
    cluster_match: str | None
    readback_outcome: str
    edit_count: int
    status: str
    status_note: str | None
    media: list[MediaOut] = []


class ReportPatch(BaseModel):
    status: ReportStatus | None = None
    status_note: str | None = None
    department_id: str | None = None
    severity: Severity | None = None
    municipal_subject: str | None = None
    needs_review: bool | None = None


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    subcategory: str
    latitude: float
    longitude: float
    report_count: int
    status: str
    first_seen: datetime
    last_seen: datetime


class ClusterDetail(ClusterOut):
    report_ids: list[int] = Field(default_factory=list)


class LogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    direction: str
    payload: dict | None
    report_id: int | None
    created_at: datetime
