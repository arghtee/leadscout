from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from leadscout.enums import LeadStatus, ScoreStage
from leadscout.models import Suppression
from tests.factories import make_campaign, make_lead


def test_rules_get_defaults_and_put_roundtrip(session: Session, client: TestClient) -> None:
    campaign = make_campaign(session)
    url = f"/campaigns/{campaign.id}/rules"
    got = client.get(url).json()
    assert got["low_activity_max_posts"] == 12
    assert got["weights"]["low_activity"] == 25

    got["low_activity_max_posts"] = 6
    assert client.put(url, json=got).status_code == 200
    assert client.get(url).json()["low_activity_max_posts"] == 6
    assert campaign.rules_json["low_activity_max_posts"] == 6


def test_rules_put_rejects_invalid(session: Session, client: TestClient) -> None:
    campaign = make_campaign(session)
    resp = client.put(
        f"/campaigns/{campaign.id}/rules", json={"review_threshold": 90, "qualified_threshold": 60}
    )
    assert resp.status_code == 422


def test_unknown_campaign_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/campaigns/{missing}/rules").status_code == 404
    assert client.post(f"/campaigns/{missing}/qualify").status_code == 404


def test_qualify_scores_and_persists(session: Session, client: TestClient) -> None:
    campaign = make_campaign(session, industry="Cafes")
    good = make_lead(session, campaign, business_name="Good", posts=[3])
    good.website_live = True
    good.company_status, good.incorporated_on = "active", date(2015, 1, 1)
    good.categories = ["cafe"]
    good.contact_search_at = good.lead_score.scored_at  # type: ignore[union-attr]
    unknown = make_lead(session, campaign, business_name="Quiet", posts=[])
    unknown.website_live = True
    suppressed = make_lead(session, campaign, business_name="Blocked", posts=[1])
    suppressed.domain = "blocked.example"
    session.add(Suppression(email_or_domain="blocked.example", reason="test"))
    session.flush()

    body = client.post(f"/campaigns/{campaign.id}/qualify").json()
    assert body == {"scored": 3, "qualified": 1, "review": 1, "rejected": 1, "lookup_eligible": 1}

    session.refresh(good)
    score = good.lead_score
    assert score is not None
    assert (score.status, score.stage, score.score) == (LeadStatus.QUALIFIED, ScoreStage.FINAL, 100)
    assert {r["rule"] for r in score.rule_results} >= {"establishment", "low_activity"}
    assert score.reasons[-1].startswith("Score 100")
    session.refresh(unknown)
    assert unknown.lead_score is not None
    assert unknown.lead_score.status is LeadStatus.REVIEW
