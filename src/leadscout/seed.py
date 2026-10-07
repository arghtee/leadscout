"""Seed the database with a fake campaign of local businesses (M1 demo/test data).

Usage: python -m leadscout.seed [--businesses 200] [--seed 42]
"""

import argparse
import random
import uuid
from datetime import UTC, date, datetime, timedelta

from faker import Faker
from sqlalchemy.orm import Session

from leadscout.db import get_sessionmaker
from leadscout.enums import (
    CampaignOutcome,
    CampaignStatus,
    Confidence,
    ContactStatus,
    EmailStatus,
    EntityType,
    Jurisdiction,
    LeadStatus,
    PhoneStatus,
)
from leadscout.models import ActivitySignal, Business, Campaign, Contact, LeadScore, Suppression

ROLES = ["Owner", "Founder", "Managing Director", "Director", "Marketing Manager", "Proprietor"]
INDUSTRY = "Independent cafes"
CATEGORIES = ["cafe", "coffee shop", "bakery", "tea room", "brunch"]
CHANNELS = ["facebook", "instagram"]

# Deliberately hostile values so the CSV-injection defence is visible in demo exports.
HOSTILE_NAMES = ['=HYPERLINK("http://evil.example","click")', "@SUM(1+1)*cmd|' /C calc'!A0"]


def _uk_e164(fake: Faker) -> str:
    return "+447" + "".join(str(fake.random_digit()) for _ in range(9))


def _status_for(score: int) -> LeadStatus:
    if score >= 60:
        return LeadStatus.QUALIFIED
    if score >= 40:
        return LeadStatus.REVIEW
    return LeadStatus.REJECTED


def seed(session: Session, n_businesses: int = 200, rng_seed: int = 42) -> Campaign:
    fake = Faker("en_GB")
    Faker.seed(rng_seed)
    rnd = random.Random(rng_seed)
    year_start = date(date.today().year, 1, 1)

    campaign = Campaign(
        id=uuid.UUID(int=rnd.getrandbits(128)),
        name=f"Seed: {INDUSTRY} in Manchester",
        industry=INDUSTRY,
        location="Manchester, UK",
        radius_km=15,
        target_roles=["owner", "founder", "managing director", "marketing manager"],
        outcome=CampaignOutcome.FREE_AUDIT,
        rules_json={
            "low_activity_max_posts": 12,
            "qualified_threshold": 60,
            "review_threshold": 40,
        },
        jurisdiction=Jurisdiction.UK_EU,
        status=CampaignStatus.COMPLETED,
    )
    session.add(campaign)

    suppressed_emails: list[str] = []
    for i in range(n_businesses):
        name = f"{fake.last_name()}'s {rnd.choice(['Cafe', 'Coffee House', 'Bakery', 'Kitchen'])}"
        domain = f"{fake.unique.domain_word()}-{i}.co.uk"
        has_site = rnd.random() < 0.85
        business = Business(
            id=uuid.UUID(int=rnd.getrandbits(128)),
            campaign=campaign,
            name=name,
            address=fake.address().replace("\n", ", "),
            lat=53.48 + rnd.uniform(-0.1, 0.1),
            lng=-2.24 + rnd.uniform(-0.1, 0.1),
            website=f"https://www.{domain}" if has_site else None,
            domain=domain if has_site else None,
            phone=_uk_e164(fake),
            domain_age_years=round(rnd.uniform(0.5, 15), 1) if has_site else None,
            company_number=f"{rnd.randint(1, 99999999):08d}" if rnd.random() < 0.7 else None,
            entity_type=rnd.choice(list(EntityType)),
            categories=rnd.sample(CATEGORIES, k=2),
            review_count=rnd.randint(0, 400),
            has_physical_location=rnd.random() < 0.9,
            social_links={c: f"https://www.{c}.com/{domain.split('.')[0]}" for c in CHANNELS},
            sources=["seed"],
        )
        session.add(business)

        if rnd.random() < 0.8:
            for channel in rnd.sample(CHANNELS, k=rnd.randint(1, 2)):
                session.add(
                    ActivitySignal(
                        business=business,
                        channel=channel,
                        posts_ytd=rnd.randint(0, 40),
                        as_of=year_start + timedelta(days=rnd.randint(0, 200)),
                        source="seed",
                        confidence=rnd.choice(list(Confidence)),
                    )
                )

        score = rnd.randint(10, 100)
        reasons = [
            "Established: incorporated 2+ years" if score > 30 else "Established: unverified",
            "Has live website" if has_site else "No website; physical location verified",
            f"Score {score} against threshold 60",
        ]
        session.add(
            LeadScore(business=business, score=score, status=_status_for(score), reasons=reasons)
        )

        for _ in range(rnd.randint(0, 2)):
            first, last = fake.first_name(), fake.last_name()
            email = f"{first}.{last}@{domain}".lower() if has_site else None
            contact = Contact(
                business=business,
                full_name=f"{first} {last}",
                role=rnd.choice(ROLES),
                email=email,
                email_status=rnd.choices(list(EmailStatus), weights=[1, 12, 3, 2, 2], k=1)[0]
                if email
                else EmailStatus.UNVERIFIED,
                phone=_uk_e164(fake),
                phone_status=rnd.choices(list(PhoneStatus), weights=[2, 12, 1, 1], k=1)[0],
                source="seed",
                provider_person_id=str(rnd.randint(10**6, 10**9)),
                email_grade=rnd.choice(["A", "A-", "B", None]),
                retrieved_at=datetime.now(UTC) - timedelta(days=rnd.randint(0, 30)),
                status=rnd.choices(list(ContactStatus), weights=[20, 3, 3, 1, 1, 1], k=1)[0],
            )
            if i < len(HOSTILE_NAMES):
                contact.full_name = HOSTILE_NAMES[i]
            session.add(contact)
            if email and rnd.random() < 0.03:
                suppressed_emails.append(email)

    for email in suppressed_emails:
        session.add(Suppression(email_or_domain=email, reason="seed: opted out"))

    session.commit()
    return campaign


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--businesses", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    with get_sessionmaker()() as session:
        campaign = seed(session, args.businesses, args.seed)
        print(f"Seeded campaign {campaign.id} with {args.businesses} businesses")


if __name__ == "__main__":
    main()
