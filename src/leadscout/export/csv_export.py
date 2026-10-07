"""CSV export per spec Section 6.2."""

import csv
import io
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from leadscout.enums import ContactStatus, EmailStatus, LeadStatus, PhoneStatus
from leadscout.models import Business, Campaign, Contact, LeadScore, Suppression

FULL_COLUMNS: tuple[str, ...] = (
    "name",
    "role",
    "phone",
    "email",
    "company",
    "website",
    "address",
    "industry",
    "posts_this_year",
    "score",
    "qualification_reason",
    "data_source",
    "email_grade",
    "retrieved_at",
    "status",
)
MINIMUM_COLUMNS: tuple[str, ...] = ("name", "role", "phone", "email")

UTF8_BOM = "\ufeff"

# Leading characters that spreadsheet apps may interpret as a formula (OWASP CSV injection).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_E164 = re.compile(r"^\+[1-9]\d{1,14}$")

EXPORTABLE_EMAIL_STATUSES = frozenset({EmailStatus.VALID, EmailStatus.RISKY})
EXPORTABLE_PHONE_STATUSES = frozenset({PhoneStatus.VALID})


class ExportMode(StrEnum):
    FULL = "full"
    MINIMUM = "minimum"


@dataclass(frozen=True)
class ExportOptions:
    mode: ExportMode = ExportMode.FULL
    include_bom: bool = False
    lead_statuses: frozenset[LeadStatus] = field(
        default_factory=lambda: frozenset({LeadStatus.QUALIFIED})
    )
    min_score: int | None = None
    max_score: int | None = None
    include_inferred_emails: bool = False

    @property
    def columns(self) -> tuple[str, ...]:
        return MINIMUM_COLUMNS if self.mode is ExportMode.MINIMUM else FULL_COLUMNS


def escape_cell(value: str, *, column: str | None = None) -> str:
    """Neutralise values a spreadsheet could execute as a formula.

    Strict E.164 numbers in the phone column are left intact: they contain only
    a leading '+' and digits, so cannot carry a payload.
    """
    if column == "phone" and _E164.match(value):
        return value
    if value.startswith(_FORMULA_TRIGGERS):
        return "'" + value
    return value


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def _posts_this_year(business: Business) -> int | str:
    counts = [s.posts_ytd for s in business.activity_signals if s.posts_ytd is not None]
    return max(counts) if counts else "unknown"


def _export_email(contact: Contact, options: ExportOptions) -> str | None:
    allowed = set(EXPORTABLE_EMAIL_STATUSES)
    if options.include_inferred_emails:
        allowed.add(EmailStatus.INFERRED)
    return contact.email if contact.email_status in allowed else None


def _export_phone(contact: Contact) -> str | None:
    return contact.phone if contact.phone_status in EXPORTABLE_PHONE_STATUSES else None


def _is_suppressed(contact: Contact, suppressed: frozenset[str]) -> bool:
    if contact.status is ContactStatus.OPTED_OUT:
        return True
    if not contact.email:
        return False
    email = contact.email.strip().lower()
    domain = email.rpartition("@")[2]
    return email in suppressed or domain in suppressed


def build_rows(
    businesses: Iterable[Business],
    campaign: Campaign,
    suppressed: frozenset[str],
    options: ExportOptions,
) -> Iterator[dict[str, Any]]:
    """One row per contact. Suppressed / opted-out contacts are excluded entirely."""
    for business in businesses:
        score = business.lead_score
        for contact in business.contacts:
            if _is_suppressed(contact, suppressed):
                continue
            yield {
                "name": contact.full_name,
                "role": contact.role,
                "phone": _export_phone(contact),
                "email": _export_email(contact, options),
                "company": business.name,
                "website": business.website,
                "address": business.address,
                "industry": campaign.industry,
                "posts_this_year": _posts_this_year(business),
                "score": score.score if score else None,
                "qualification_reason": "; ".join(score.reasons) if score else None,
                "data_source": contact.source,
                "email_grade": contact.email_grade,
                "retrieved_at": contact.retrieved_at,
                "status": contact.status,
            }


def write_csv(rows: Iterable[dict[str, Any]], columns: Sequence[str], *, bom: bool = False) -> str:
    buf = io.StringIO(newline="")
    if bom:
        buf.write(UTF8_BOM)
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([escape_cell(_format(row.get(col)), column=col) for col in columns])
    return buf.getvalue()


def _business_query(campaign_id: Any, options: ExportOptions) -> Select[Business]:
    stmt = (
        select(Business)
        .join(LeadScore, LeadScore.business_id == Business.id)
        .where(Business.campaign_id == campaign_id)
        .where(LeadScore.status.in_(options.lead_statuses))
        .options(
            selectinload(Business.contacts),
            selectinload(Business.activity_signals),
            selectinload(Business.lead_score),
        )
        .order_by(LeadScore.score.desc(), Business.name)
    )
    if options.min_score is not None:
        stmt = stmt.where(LeadScore.score >= options.min_score)
    if options.max_score is not None:
        stmt = stmt.where(LeadScore.score <= options.max_score)
    return stmt


def export_campaign_csv(session: Session, campaign: Campaign, options: ExportOptions) -> str:
    suppressed = frozenset(
        v.strip().lower() for v in session.scalars(select(Suppression.email_or_domain))
    )
    businesses = session.scalars(_business_query(campaign.id, options)).all()
    rows = build_rows(businesses, campaign, suppressed, options)
    return write_csv(rows, options.columns, bom=options.include_bom)
