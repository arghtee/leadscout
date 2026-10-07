from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadscout.export.csv_export import ExportOptions, export_campaign_csv
from leadscout.models import Business, Campaign, LeadScore
from leadscout.seed import seed


def test_seed_creates_200_businesses_each_scored(session: Session) -> None:
    campaign = seed(session, 200, rng_seed=1)
    count = session.scalar(
        select(func.count()).select_from(Business).where(Business.campaign_id == campaign.id)
    )
    scored = session.scalar(
        select(func.count())
        .select_from(LeadScore)
        .join(Business)
        .where(Business.campaign_id == campaign.id)
    )
    assert count == 200
    assert scored == 200


def test_seed_is_deterministic(session: Session) -> None:
    a = seed(session, 5, rng_seed=7)
    session.delete(a)
    session.flush()
    b = seed(session, 5, rng_seed=7)
    assert a.id == b.id


def test_seeded_export_has_no_unescaped_formulas(session: Session, client: TestClient) -> None:
    campaign = seed(session, 200, rng_seed=42)
    out = export_campaign_csv(session, campaign, ExportOptions())
    lines = out.splitlines()
    assert len(lines) > 1
    for line in lines[1:]:
        assert not line.startswith(("=", "+", "-", "@"))
    listed = client.get("/campaigns").json()
    assert any(c["id"] == str(campaign.id) for c in listed)
    assert session.get(Campaign, campaign.id) is not None
