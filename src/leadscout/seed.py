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
    PhoneStatus,
)
from leadscout.models import ActivitySignal, Business, Campaign, Contact, Suppression
from leadscout.qualification.rules import load_rules
from leadscout.qualification.service import evaluate_business, qualify_business

ROLES = ["Owner", "Founder", "Managing Director", "Director", "Marketing Manager", "Proprietor"]
INDUSTRY = "Independent cafes"
CATEGORIES = ["cafe", "coffee shop", "bakery", "tea room", "brunch"]
CHANNELS = ["facebook", "instagram"]

# Deliberately hostile values so the CSV-injection defence is visible in demo exports.
HOSTILE_NAMES = ['=HYPERLINK("http://evil.example","click")', "@SUM(1+1)*cmd|' /C calc'!A0"]


def _uk_e164(fake: Faker) -> str:
    return "+447" + "".join(str(fake.random_digit()) for _ in range(9))


def seed(session: Session, n_businesses: int = 200, rng_seed: int = 42) -> Campaign:
    fake = Faker("en_GB")
    Faker.seed(rng_seed)
    rnd = random.Random(rng_seed)
    today = date.today()
    year_start = date(today.year, 1, 1)

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
            "industry_keywords": CATEGORIES,
        },
        jurisdiction=Jurisdiction.UK_EU,
        status=CampaignStatus.COMPLETED,
    )
    session.add(campaign)
    rules = load_rules(campaign.rules_json)

    suppressed_emails: list[str] = []
    contacts_made = 0
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
            company_status=rnd.choices(["active", "dissolved", None], weights=[80, 3, 17])[0],
            incorporated_on=today - timedelta(days=rnd.randint(150, 7000)),
            website_live=has_site and rnd.random() < 0.9,
            is_chain=rnd.random() < 0.05,
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
                        posts_ytd=int(rnd.expovariate(1 / 10)),
                        as_of=year_start + timedelta(days=rnd.randint(0, 200)),
                        source="seed",
                        confidence=rnd.choice(list(Confidence)),
                    )
                )

        # Mirror the pipeline: contacts are only searched for lookup-eligible businesses.
        n_contacts = 0
        if evaluate_business(business, campaign, rules, today=today).lookup_eligible:
            business.contact_search_at = datetime.now(UTC)
            n_contacts = rnd.choices([0, 1, 2], weights=[2, 5, 3])[0]

        for _ in range(n_contacts):
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
            if contacts_made < len(HOSTILE_NAMES):
                contact.full_name = HOSTILE_NAMES[contacts_made]
            contacts_made += 1
            session.add(contact)
            if email and rnd.random() < 0.03:
                suppressed_emails.append(email)

        qualify_business(session, business, campaign, rules, today=today)

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
