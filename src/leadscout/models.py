"""ORM models for the core entities in spec Section 6.1."""

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from leadscout.enums import (
    CampaignOutcome,
    CampaignStatus,
    Confidence,
    ContactStatus,
    DraftStatus,
    EmailStatus,
    EntityType,
    Jurisdiction,
    LeadStatus,
    McpCallStatus,
    OutreachChannel,
    PhoneStatus,
    ScoreStage,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Portable enum stored as VARCHAR with a CHECK constraint, persisted by value."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Campaign(Base):
    __tablename__ = "campaign"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200))
    radius_km: Mapped[float] = mapped_column(Float, default=10.0)
    target_roles: Mapped[list[str]] = mapped_column(JsonType, default=list)
    outcome: Mapped[CampaignOutcome] = mapped_column(str_enum(CampaignOutcome, "campaign_outcome"))
    rules_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        str_enum(Jurisdiction, "jurisdiction"), default=Jurisdiction.UK_EU
    )
    status: Mapped[CampaignStatus] = mapped_column(
        str_enum(CampaignStatus, "campaign_status"), default=CampaignStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    businesses: Mapped[list["Business"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class Business(Base):
    __tablename__ = "business"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaign.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(500))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    website: Mapped[str | None] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    domain_age_years: Mapped[float | None] = mapped_column(Float)
    company_number: Mapped[str | None] = mapped_column(String(32))
    company_status: Mapped[str | None] = mapped_column(String(32))
    incorporated_on: Mapped[date | None] = mapped_column(Date)
    entity_type: Mapped[EntityType] = mapped_column(
        str_enum(EntityType, "entity_type"), default=EntityType.UNKNOWN
    )
    categories: Mapped[list[str]] = mapped_column(JsonType, default=list)
    review_count: Mapped[int | None] = mapped_column(Integer)
    has_physical_location: Mapped[bool | None] = mapped_column(Boolean)
    website_live: Mapped[bool | None] = mapped_column(Boolean)
    is_chain: Mapped[bool | None] = mapped_column(Boolean)
    contact_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    social_links: Mapped[dict[str, str]] = mapped_column(JsonType, default=dict)
    sources: Mapped[list[str]] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="businesses")
    activity_signals: Mapped[list["ActivitySignal"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    lead_score: Mapped["LeadScore | None"] = relationship(
        back_populates="business", cascade="all, delete-orphan", uselist=False
    )


class ActivitySignal(Base):
    __tablename__ = "activity_signal"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(50))
    posts_ytd: Mapped[int | None] = mapped_column(Integer)
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "confidence"))

    business: Mapped[Business] = relationship(back_populates="activity_signals")


class Contact(Base):
    __tablename__ = "contact"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    email_status: Mapped[EmailStatus] = mapped_column(
        str_enum(EmailStatus, "email_status"), default=EmailStatus.UNVERIFIED
    )
    phone: Mapped[str | None] = mapped_column(String(32))
    phone_status: Mapped[PhoneStatus] = mapped_column(
        str_enum(PhoneStatus, "phone_status"), default=PhoneStatus.UNVERIFIED
    )
    source: Mapped[str] = mapped_column(String(100))
    provider_person_id: Mapped[str | None] = mapped_column(String(100), index=True)
    email_grade: Mapped[str | None] = mapped_column(String(20))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lawful_basis: Mapped[str] = mapped_column(String(200), default="legitimate_interests_b2b")
    status: Mapped[ContactStatus] = mapped_column(
        str_enum(ContactStatus, "contact_status"), default=ContactStatus.NEW
    )

    business: Mapped[Business] = relationship(back_populates="contacts")
    drafts: Mapped[list["OutreachDraft"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )


class LeadScore(Base):
    __tablename__ = "lead_score"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), unique=True
    )
    score: Mapped[int] = mapped_column(Integer)
    status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus, "lead_status"))
    reasons: Mapped[list[str]] = mapped_column(JsonType, default=list)
    stage: Mapped[ScoreStage] = mapped_column(
        str_enum(ScoreStage, "score_stage"), default=ScoreStage.FINAL, server_default="final"
    )
    lookup_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    rule_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, default=list, server_default="[]"
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="lead_score")


class OutreachDraft(Base):
    __tablename__ = "outreach_draft"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[OutreachChannel] = mapped_column(str_enum(OutreachChannel, "outreach_channel"))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[DraftStatus] = mapped_column(
        str_enum(DraftStatus, "draft_status"), default=DraftStatus.DRAFT
    )
    approved_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contact: Mapped[Contact] = relationship(back_populates="drafts")


class Suppression(Base):
    __tablename__ = "suppression"
    __table_args__ = (UniqueConstraint("email_or_domain"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email_or_domain: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    tool: Mapped[str] = mapped_column(String(100))
    provider_id: Mapped[str | None] = mapped_column(String(100))
    credits_used: Mapped[float] = mapped_column(Float, default=0)
    balance_after: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class McpCallLog(Base):
    """MCP call telemetry. Must never hold contact data (NFR-4)."""

    __tablename__ = "mcp_call_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    tool: Mapped[str] = mapped_column(String(100))
    status: Mapped[McpCallStatus] = mapped_column(str_enum(McpCallStatus, "mcp_call_status"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
