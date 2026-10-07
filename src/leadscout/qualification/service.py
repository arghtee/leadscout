"""Bridges ORM rows and the pure engine; persists `LeadScore`."""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from leadscout.enums import EmailStatus, PhoneStatus
from leadscout.models import Business, Campaign, LeadScore, Suppression, utcnow
from leadscout.qualification.engine import BusinessFacts, ContactFacts, Evaluation, Signal, evaluate
from leadscout.qualification.rules import QualificationRules, load_rules


@dataclass(frozen=True)
class QualifySummary:
    scored: int
    qualified: int
    review: int
    rejected: int
    lookup_eligible: int


def load_suppressed(session: Session) -> frozenset[str]:
    return frozenset(v.lower() for v in session.scalars(select(Suppression.email_or_domain)))


def business_facts(business: Business, suppressed: frozenset[str] = frozenset()) -> BusinessFacts:
    domain = (business.domain or "").lower() or None
    return BusinessFacts(
        company_status=business.company_status,
        incorporated_on=business.incorporated_on,
        domain=domain,
        domain_age_years=business.domain_age_years,
        review_count=business.review_count,
        address=business.address,
        has_physical_location=business.has_physical_location,
        website=business.website,
        website_live=business.website_live,
        categories=tuple(business.categories or ()),
        signals=tuple(
            Signal(s.channel, s.posts_ytd, s.as_of, s.confidence) for s in business.activity_signals
        ),
        is_chain=business.is_chain,
        is_suppressed=domain is not None and domain in suppressed,
        contacts_searched=business.contact_search_at is not None,
        contacts=tuple(
            ContactFacts(
                role=c.role,
                email_valid=bool(c.email) and c.email_status is EmailStatus.VALID,
                phone_valid=bool(c.phone) and c.phone_status is PhoneStatus.VALID,
            )
            for c in business.contacts
        ),
    )


def evaluate_business(
    business: Business,
    campaign: Campaign,
    rules: QualificationRules,
    *,
    suppressed: frozenset[str] = frozenset(),
    today: date | None = None,
) -> Evaluation:
    return evaluate(
        business_facts(business, suppressed),
        rules,
        industry=campaign.industry,
        target_roles=campaign.target_roles,
        today=today or date.today(),
    )


def qualify_business(
    session: Session,
    business: Business,
    campaign: Campaign,
    rules: QualificationRules,
    *,
    suppressed: frozenset[str] = frozenset(),
    today: date | None = None,
) -> LeadScore:
    ev = evaluate_business(business, campaign, rules, suppressed=suppressed, today=today)
    score = business.lead_score or LeadScore(business=business)
    score.score = ev.score
    score.status = ev.status
    score.stage = ev.stage
    score.lookup_eligible = ev.lookup_eligible
    score.reasons = ev.reasons
    score.rule_results = [r.to_dict() for r in ev.results]
    score.scored_at = utcnow()
    session.add(score)
    return score


def qualify_campaign(
    session: Session, campaign: Campaign, *, today: date | None = None
) -> QualifySummary:
    rules = load_rules(campaign.rules_json)
    suppressed = load_suppressed(session)
    businesses = session.scalars(
        select(Business)
        .where(Business.campaign_id == campaign.id)
        .options(
            selectinload(Business.activity_signals),
            selectinload(Business.contacts),
            selectinload(Business.lead_score),
        )
    ).all()
    scores = [
        qualify_business(session, b, campaign, rules, suppressed=suppressed, today=today)
        for b in businesses
    ]
    session.commit()
    counts = Counter(s.status.value for s in scores)
    return QualifySummary(
        scored=len(scores),
        qualified=counts["qualified"],
        review=counts["review"],
        rejected=counts["rejected"],
        lookup_eligible=sum(s.lookup_eligible for s in scores),
    )
