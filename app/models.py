from datetime import datetime, timezone

import hashlib

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    """Naive UTC; SQLite drops tzinfo, so we keep everything naive and UTC (Postgres: timestamp without time zone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# JSONB on Postgres (indexable, queryable); plain JSON text on SQLite
JsonDoc = JSON().with_variant(JSONB(), "postgresql")


class ChatSession(Base):
    """Per-resident conversation state. The only table that holds the raw chat/phone ID."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # "tg:<chat id>" / "wa:<phone>"
    interaction_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(32), default="START")
    language: Mapped[str | None] = mapped_column(String(8))  # remembered across reports
    data: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InboundMessage(Base):
    """Seen delivery keys (Telegram update_id / WhatsApp message id), so retries are processed once."""

    __tablename__ = "inbound_messages"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Cluster(Base):
    """A distinct physical problem; every report belongs to exactly one."""

    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    subcategory: Mapped[str] = mapped_column(String(64), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="open")
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    reports: Mapped[list["Report"]] = relationship(back_populates="cluster")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="telegram")
    language: Mapped[str] = mapped_column(String(8), default="te")

    # What the resident chose in the menu
    category: Mapped[str] = mapped_column(String(32), index=True)
    subcategory: Mapped[str] = mapped_column(String(64))

    # Two labels (work plan constraint 2): project barrier type + municipal subject
    barrier_type: Mapped[str] = mapped_column(String(64), index=True)
    municipal_subject: Mapped[str | None] = mapped_column(String(128))
    department_id: Mapped[str | None] = mapped_column(String(64), index=True)
    severity: Mapped[str | None] = mapped_column(String(16), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    classifier: Mapped[str | None] = mapped_column(String(16))
    classifier_model: Mapped[str | None] = mapped_column(String(128))
    summary_en: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Disability marker that travels with the record (constraint 3)
    pwd_marker: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    affected: Mapped[str] = mapped_column(String(16))  # self | caregiver | none

    description_raw: Mapped[str | None] = mapped_column(Text)
    description_type: Mapped[str] = mapped_column(String(8), default="text")  # always "text" (no voice input)
    description_en: Mapped[str | None] = mapped_column(Text)

    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(256))
    location_address: Mapped[str | None] = mapped_column(String(512))
    location_route: Mapped[str] = mapped_column(String(32), default="shared_location")
    ward: Mapped[str | None] = mapped_column(String(64), index=True)

    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("clusters.id"), index=True)
    cluster_match: Mapped[str | None] = mapped_column(String(16))  # new | strict | possible

    readback_outcome: Mapped[str] = mapped_column(String(16))  # confirmed | edited
    edit_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    status_note: Mapped[str | None] = mapped_column(Text)

    # HMAC of the phone number: lets us count repeat reporters without storing the number
    reporter_hash: Mapped[str] = mapped_column(String(64), index=True)

    cluster: Mapped[Cluster | None] = relationship(back_populates="reports")
    media: Mapped[list["Media"]] = relationship(back_populates="report", cascade="all, delete-orphan")

    @property
    def ref(self) -> str:
        return f"PI4C-{self.id:06d}"


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # image
    file_id: Mapped[str | None] = mapped_column(String(256))  # channel's media/file ID
    mime_type: Mapped[str | None] = mapped_column(String(64))
    path: Mapped[str | None] = mapped_column(String(512))
    caption: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    report: Mapped[Report] = relationship(back_populates="media")
    file: Mapped["MediaFile | None"] = relationship(back_populates="media", cascade="all, delete-orphan")


class MediaFile(Base):
    """The photo bytes (BYTEA on Postgres). Kept apart from `media` so listing reports
    never loads file contents; only GET /reports/{id}/media/{media_id} reads them."""

    __tablename__ = "media_files"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    media: Mapped[Media] = relationship(back_populates="file")

    @classmethod
    def from_bytes(cls, data: bytes) -> "MediaFile":
        return cls(data=data, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


class InteractionLog(Base):
    """Stage-wise log keyed by interaction ID (one per conversation)."""

    __tablename__ = "interaction_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(36), index=True)
    report_id: Mapped[int | None] = mapped_column(Integer, index=True)
    stage: Mapped[str] = mapped_column(String(48), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # in | out | system
    payload: Mapped[dict | None] = mapped_column(JsonDoc)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
