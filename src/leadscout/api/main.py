import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from leadscout import __version__
from leadscout.db import get_session
from leadscout.enums import CampaignOutcome, CampaignStatus, Jurisdiction, LeadStatus
from leadscout.export.csv_export import ExportMode, ExportOptions, export_campaign_csv
from leadscout.models import Campaign
from leadscout.qualification.rules import QualificationRules, load_rules
from leadscout.qualification.service import qualify_campaign

app = FastAPI(title="LeadScout", version=__version__)

SessionDep = Annotated[Session, Depends(get_session)]


class HealthOut(BaseModel):
    status: str
    version: str
    database: str


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str
    location: str
    radius_km: float
    target_roles: list[str]
    outcome: CampaignOutcome
    jurisdiction: Jurisdiction
    status: CampaignStatus


@app.get("/health", response_model=HealthOut)
def health(session: SessionDep, response: Response) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception:
        db_state = "unavailable"
        response.status_code = 503
    return HealthOut(
        status="ok" if db_state == "ok" else "degraded", version=__version__, database=db_state
    )


@app.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(session: SessionDep) -> list[Campaign]:
    return list(session.scalars(select(Campaign).order_by(Campaign.created_at.desc())))


class QualifyOut(BaseModel):
    scored: int
    qualified: int
    review: int
    rejected: int
    lookup_eligible: int


def _campaign_or_404(session: Session, campaign_id: uuid.UUID) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@app.get("/campaigns/{campaign_id}/rules", response_model=QualificationRules)
def get_rules(campaign_id: uuid.UUID, session: SessionDep) -> QualificationRules:
    return load_rules(_campaign_or_404(session, campaign_id).rules_json)


@app.put("/campaigns/{campaign_id}/rules", response_model=QualificationRules)
def put_rules(
    campaign_id: uuid.UUID, rules: QualificationRules, session: SessionDep
) -> QualificationRules:
    campaign = _campaign_or_404(session, campaign_id)
    campaign.rules_json = rules.model_dump(mode="json")
    session.commit()
    return rules


@app.post("/campaigns/{campaign_id}/qualify", response_model=QualifyOut)
def qualify(campaign_id: uuid.UUID, session: SessionDep) -> QualifyOut:
    summary = qualify_campaign(session, _campaign_or_404(session, campaign_id))
    return QualifyOut(**vars(summary))


@app.get(
    "/campaigns/{campaign_id}/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_csv(
    campaign_id: uuid.UUID,
    session: SessionDep,
    mode: ExportMode = ExportMode.FULL,
    bom: bool = False,
    status: Annotated[list[LeadStatus] | None, Query()] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    max_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    include_inferred: bool = False,
) -> Response:
    campaign = _campaign_or_404(session, campaign_id)
    options = ExportOptions(
        mode=mode,
        include_bom=bom,
        lead_statuses=frozenset(status or [LeadStatus.QUALIFIED]),
        min_score=min_score,
        max_score=max_score,
        include_inferred_emails=include_inferred,
    )
    body = export_campaign_csv(session, campaign, options)
    filename = f"leadscout-{campaign_id}.csv"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
