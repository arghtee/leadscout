from enum import StrEnum


class CampaignOutcome(StrEnum):
    BOOK_CALL = "book_call"
    FREE_AUDIT = "free_audit"
    REQUEST_INTRO = "request_intro"
    LANDING_PAGE = "landing_page"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Jurisdiction(StrEnum):
    UK_EU = "uk_eu"
    US = "us"
    CANADA = "canada"
    OTHER = "other"


class EntityType(StrEnum):
    LIMITED_COMPANY = "limited_company"
    LLP = "llp"
    PLC = "plc"
    SOLE_TRADER = "sole_trader"
    PARTNERSHIP = "partnership"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EmailStatus(StrEnum):
    UNVERIFIED = "unverified"
    VALID = "valid"
    RISKY = "risky"
    INVALID = "invalid"
    INFERRED = "inferred"


class PhoneStatus(StrEnum):
    UNVERIFIED = "unverified"
    VALID = "valid"
    INVALID = "invalid"
    DO_NOT_CALL = "do_not_call"


class LeadStatus(StrEnum):
    QUALIFIED = "qualified"
    REVIEW = "review"
    REJECTED = "rejected"


class ScoreStage(StrEnum):
    """`pre_lookup`: free signals only (decides lookup eligibility). `final`: after search."""

    PRE_LOOKUP = "pre_lookup"
    FINAL = "final"


class RuleOutcome(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    UNKNOWN = "unknown"


class ContactStatus(StrEnum):
    """Outreach lifecycle of a contact; matches the export `status` column (spec 6.2)."""

    NEW = "new"
    APPROVED = "approved"
    CONTACTED = "contacted"
    REPLIED = "replied"
    BOUNCED = "bounced"
    OPTED_OUT = "opted_out"


class OutreachChannel(StrEnum):
    EMAIL = "email"
    LINKEDIN_NOTE = "linkedin_note"
    CALL_SCRIPT = "call_script"


class DraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    REPLIED = "replied"
    BOUNCED = "bounced"


class McpCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"
