from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from leadscout.enums import (
    CampaignOutcome,
    Confidence,
    ContactStatus,
    EmailStatus,
    LeadStatus,
    PhoneStatus,
)
from leadscout.models import ActivitySignal, Business, Campaign, Contact, LeadScore


def make_campaign(session: Session, **kw: Any) -> Campaign:
    campaign = Campaign(
        name=kw.pop("name", "Test campaign"),
        industry=kw.pop("industry", "Cafes"),
        location=kw.pop("location", "Leeds"),
        outcome=kw.pop("outcome", CampaignOutcome.BOOK_CALL),
        target_roles=kw.pop("target_roles", ["owner"]),
        **kw,
    )
    session.add(campaign)
    session.flush()
    return campaign


def make_lead(
    session: Session,
    campaign: Campaign,
    *,
    business_name: str = "Bean There",
    score: int = 80,
    lead_status: LeadStatus = LeadStatus.QUALIFIED,
    reasons: list[str] | None = None,
    posts: list[int | None] | None = None,
    contacts: list[dict[str, Any]] | None = None,
) -> Business:
    business = Business(
        campaign=campaign,
        name=business_name,
        address="1 High St, Leeds",
        website="https://beanthere.co.uk",
        domain="beanthere.co.uk",
    )
    session.add(business)
    session.add(
        LeadScore(
            business=business,
            score=score,
            status=lead_status,
            reasons=reasons if reasons is not None else ["Established", "Low activity"],
        )
    )
    for p in posts or []:
        session.add(
            ActivitySignal(
                business=business,
                channel="facebook",
                posts_ytd=p,
                as_of=date(2026, 6, 1),
                source="manual",
                confidence=Confidence.HIGH,
            )
        )
    for c in contacts if contacts is not None else [{}]:
        session.add(
            Contact(
                business=business,
                full_name=c.get("full_name", "Jane Smith"),
                role=c.get("role", "Owner"),
                email=c.get("email", "jane@beanthere.co.uk"),
                email_status=c.get("email_status", EmailStatus.VALID),
                phone=c.get("phone", "+441132496000"),
                phone_status=c.get("phone_status", PhoneStatus.VALID),
                source=c.get("source", "rocketreach"),
                email_grade=c.get("email_grade", "A"),
                retrieved_at=c.get("retrieved_at", datetime(2026, 5, 4, 10, 30, tzinfo=UTC)),
                status=c.get("status", ContactStatus.NEW),
            )
        )
    session.flush()
    return business
