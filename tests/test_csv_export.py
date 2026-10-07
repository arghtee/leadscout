import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from leadscout.enums import ContactStatus, EmailStatus, LeadStatus, PhoneStatus
from leadscout.export.csv_export import (
    FULL_COLUMNS,
    MINIMUM_COLUMNS,
    ExportMode,
    ExportOptions,
    export_campaign_csv,
)
from leadscout.models import Suppression

from .factories import make_campaign, make_lead


def _parse(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.removeprefix("\ufeff"), newline="")))


def test_full_export_columns_and_values(session: Session) -> None:
    campaign = make_campaign(session, industry="Cafes")
    make_lead(
        session, campaign, score=82, reasons=["Established 5y", "11 posts YTD"], posts=[11, 3]
    )

    out = export_campaign_csv(session, campaign, ExportOptions())
    assert out.splitlines()[0] == ",".join(FULL_COLUMNS)
    [row] = _parse(out)
    assert row == {
        "name": "Jane Smith",
        "role": "Owner",
        "phone": "+441132496000",
        "email": "jane@beanthere.co.uk",
        "company": "Bean There",
        "website": "https://beanthere.co.uk",
        "address": "1 High St, Leeds",
        "industry": "Cafes",
        "posts_this_year": "11",
        "score": "82",
        "qualification_reason": "Established 5y; 11 posts YTD",
        "data_source": "rocketreach",
        "email_grade": "A",
        "retrieved_at": "2026-05-04",
        "status": "new",
    }


def test_minimum_mode_has_four_columns(session: Session) -> None:
    campaign = make_campaign(session)
    make_lead(session, campaign)
    out = export_campaign_csv(session, campaign, ExportOptions(mode=ExportMode.MINIMUM))
    assert out.splitlines()[0] == ",".join(MINIMUM_COLUMNS)
    assert _parse(out)[0]["email"] == "jane@beanthere.co.uk"


def test_missing_activity_exported_as_unknown(session: Session) -> None:
    campaign = make_campaign(session)
    make_lead(session, campaign, posts=[None])
    assert (
        _parse(export_campaign_csv(session, campaign, ExportOptions()))[0]["posts_this_year"]
        == "unknown"
    )


def test_ac12_hostile_db_values_are_escaped(session: Session) -> None:
    campaign = make_campaign(session, industry="=2+5")
    make_lead(
        session,
        campaign,
        business_name="@evil",
        contacts=[{"full_name": '=HYPERLINK("http://x","y")', "role": "-Owner"}],
    )
    [row] = _parse(export_campaign_csv(session, campaign, ExportOptions()))
    assert row["name"] == '\'=HYPERLINK("http://x","y")'
    assert row["role"] == "'-Owner"
    assert row["company"] == "'@evil"
    assert row["industry"] == "'=2+5"
    assert row["phone"] == "+441132496000"


def test_only_verified_contact_details_exported(session: Session) -> None:
    campaign = make_campaign(session)
    make_lead(
        session,
        campaign,
        contacts=[
            {"full_name": "Invalid", "email_status": EmailStatus.INVALID},
            {"full_name": "Inferred", "email_status": EmailStatus.INFERRED},
            {"full_name": "Risky", "email_status": EmailStatus.RISKY},
            {"full_name": "DNC", "phone_status": PhoneStatus.DO_NOT_CALL},
            {"full_name": "Unverified phone", "phone_status": PhoneStatus.UNVERIFIED},
        ],
    )
    rows = {r["name"]: r for r in _parse(export_campaign_csv(session, campaign, ExportOptions()))}
    assert rows["Invalid"]["email"] == ""
    assert rows["Inferred"]["email"] == ""
    assert rows["Risky"]["email"] == "jane@beanthere.co.uk"
    assert rows["DNC"]["phone"] == ""
    assert rows["Unverified phone"]["phone"] == ""

    opted_in = export_campaign_csv(session, campaign, ExportOptions(include_inferred_emails=True))
    assert {r["name"]: r for r in _parse(opted_in)}["Inferred"]["email"] == "jane@beanthere.co.uk"


def test_suppressed_and_opted_out_contacts_excluded(session: Session) -> None:
    campaign = make_campaign(session)
    make_lead(
        session,
        campaign,
        contacts=[
            {"full_name": "Keep", "email": "keep@ok.co.uk"},
            {"full_name": "By email", "email": "Gone@ok.co.uk"},
            {"full_name": "By domain", "email": "x@blocked.co.uk"},
            {"full_name": "Opted out", "email": "o@ok.co.uk", "status": ContactStatus.OPTED_OUT},
        ],
    )
    session.add_all(
        [
            Suppression(email_or_domain="gone@ok.co.uk", reason="opt-out"),
            Suppression(email_or_domain="BLOCKED.co.uk", reason="customer"),
        ]
    )
    session.flush()
    names = [r["name"] for r in _parse(export_campaign_csv(session, campaign, ExportOptions()))]
    assert names == ["Keep"]


def test_filters_by_status_score_and_campaign(session: Session) -> None:
    campaign = make_campaign(session)
    other = make_campaign(session, name="Other")
    make_lead(session, campaign, business_name="A", score=90, contacts=[{"full_name": "a"}])
    make_lead(session, campaign, business_name="B", score=65, contacts=[{"full_name": "b"}])
    make_lead(
        session,
        campaign,
        business_name="C",
        score=50,
        lead_status=LeadStatus.REVIEW,
        contacts=[{"full_name": "c"}],
    )
    make_lead(session, other, business_name="D", score=99, contacts=[{"full_name": "d"}])

    def names(opts: ExportOptions) -> list[str]:
        return [r["name"] for r in _parse(export_campaign_csv(session, campaign, opts))]

    assert names(ExportOptions()) == ["a", "b"]
    assert names(ExportOptions(min_score=70)) == ["a"]
    assert names(ExportOptions(max_score=70)) == ["b"]
    statuses = frozenset({LeadStatus.QUALIFIED, LeadStatus.REVIEW})
    assert names(ExportOptions(lead_statuses=statuses)) == ["a", "b", "c"]


def test_export_endpoint(client: TestClient, session: Session) -> None:
    campaign = make_campaign(session)
    make_lead(session, campaign, contacts=[{"full_name": "=1+1"}])

    resp = client.get(f"/campaigns/{campaign.id}/export.csv", params={"bom": "true"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"\xef\xbb\xbf")
    assert _parse(resp.content.decode("utf-8"))[0]["name"] == "'=1+1"

    resp = client.get(
        f"/campaigns/{campaign.id}/export.csv",
        params={"mode": "minimum", "status": ["review"]},
    )
    assert resp.status_code == 200
    assert resp.text.strip() == ",".join(MINIMUM_COLUMNS)


def test_export_endpoint_404_and_validation(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/campaigns/{missing}/export.csv").status_code == 404
    assert client.get(f"/campaigns/{missing}/export.csv?min_score=101").status_code == 422
