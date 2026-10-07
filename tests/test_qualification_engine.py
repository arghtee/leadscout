from datetime import date

import pytest
from pydantic import ValidationError

from leadscout.enums import Confidence, LeadStatus, RuleOutcome, ScoreStage
from leadscout.qualification.engine import (
    BusinessFacts,
    ContactFacts,
    Rule,
    Signal,
    evaluate,
    industry_keywords,
)
from leadscout.qualification.rules import QualificationRules, ScoreWeights, load_rules

TODAY = date(2026, 10, 7)
ROLES = ["owner", "marketing manager"]


def facts(**kw: object) -> BusinessFacts:
    base: dict[str, object] = {
        "company_status": "active",
        "incorporated_on": date(2018, 3, 1),
        "domain": "beanthere.co.uk",
        "website": "https://beanthere.co.uk",
        "website_live": True,
        "categories": ("cafe",),
        "signals": (Signal("facebook", 5, date(2026, 9, 1), Confidence.HIGH),),
    }
    base.update(kw)
    return BusinessFacts(**base)  # type: ignore[arg-type]


def ev(f: BusinessFacts, rules: QualificationRules | None = None):  # type: ignore[no-untyped-def]
    return evaluate(
        f,
        rules or QualificationRules(),
        industry="Independent cafes",
        target_roles=ROLES,
        today=TODAY,
    )


SEARCHED = {
    "contacts_searched": True,
    "contacts": (ContactFacts(role="Owner", email_valid=True),),
}


# AC-1
@pytest.mark.parametrize(("posts", "outcome"), [(11, RuleOutcome.PASS), (12, RuleOutcome.FAIL)])
def test_ac1_low_activity_threshold(posts: int, outcome: RuleOutcome) -> None:
    f = facts(signals=(Signal("facebook", posts, date(2026, 6, 1)),))
    assert ev(f).result(Rule.LOW_ACTIVITY).outcome is outcome


# AC-2
def test_ac2_unknown_activity_goes_to_review_not_qualified() -> None:
    result = ev(facts(signals=(), **SEARCHED))
    assert result.result(Rule.LOW_ACTIVITY).outcome is RuleOutcome.UNKNOWN
    assert result.score >= 60
    assert result.status is LeadStatus.REVIEW
    assert not result.lookup_eligible
    assert any("Activity unknown" in r for r in result.reasons)


# AC-4
def test_ac4_dissolved_company_is_rejected() -> None:
    result = ev(facts(company_status="dissolved", review_count=300, **SEARCHED))
    assert result.status is LeadStatus.REJECTED
    assert "company dissolved" in [r.lower() for r in result.reasons]


def test_full_pass_pre_lookup_is_eligible_but_not_qualified() -> None:
    result = ev(facts())
    assert result.stage is ScoreStage.PRE_LOOKUP
    assert result.lookup_eligible
    assert result.status is LeadStatus.REVIEW
    assert result.score == 65
    assert "eligible for contact lookup" in result.reasons[-1]


def test_final_with_decision_maker_and_contact_is_qualified() -> None:
    result = ev(facts(**SEARCHED))
    assert result.stage is ScoreStage.FINAL
    assert result.score == 100
    assert result.status is LeadStatus.QUALIFIED
    assert "Decision maker found: Owner" in result.reasons[5]


def test_final_without_contacts_scores_free_signals_only() -> None:
    result = ev(facts(contacts_searched=True))
    assert result.result(Rule.DECISION_MAKER).outcome is RuleOutcome.FAIL
    assert result.result(Rule.CONTACTABILITY).outcome is RuleOutcome.FAIL
    assert result.score == 65
    assert result.status is LeadStatus.QUALIFIED


def test_failing_free_rule_blocks_lookup() -> None:
    result = ev(facts(signals=(Signal("facebook", 30, date(2026, 6, 1)),)))
    assert not result.lookup_eligible
    assert result.score == 40
    assert result.status is LeadStatus.REVIEW


def test_two_failures_pre_lookup_rejected() -> None:
    result = ev(
        facts(
            signals=(Signal("facebook", 30, date(2026, 6, 1)),),
            website_live=False,
            has_physical_location=False,
        )
    )
    assert result.status is LeadStatus.REJECTED


def test_phone_only_is_contactable() -> None:
    f = facts(contacts_searched=True, contacts=(ContactFacts(role="Founder", phone_valid=True),))
    assert ev(f).result(Rule.CONTACTABILITY).reason == "Contactable: valid phone"


def test_non_matching_role_fails_decision_maker() -> None:
    f = facts(contacts_searched=True, contacts=(ContactFacts(role="Barista", email_valid=True),))
    result = ev(f)
    assert result.result(Rule.DECISION_MAKER).outcome is RuleOutcome.FAIL
    assert result.result(Rule.CONTACTABILITY).outcome is RuleOutcome.PASS


@pytest.mark.parametrize(
    ("kw", "outcome", "fragment"),
    [
        ({}, RuleOutcome.PASS, "incorporated 2018"),
        (
            {"incorporated_on": date(2025, 6, 1), "domain_age_years": 3.0},
            RuleOutcome.PASS,
            "domain",
        ),
        ({"company_status": None, "review_count": 25}, RuleOutcome.PASS, "25 reviews"),
        ({"company_status": "liquidation", "review_count": 3}, RuleOutcome.FAIL, "Not established"),
        ({"company_status": None, "incorporated_on": None}, RuleOutcome.UNKNOWN, "unknown"),
    ],
)
def test_establishment(kw: dict[str, object], outcome: RuleOutcome, fragment: str) -> None:
    r = ev(facts(**kw)).result(Rule.ESTABLISHMENT)
    assert r.outcome is outcome
    assert fragment in r.reason


@pytest.mark.parametrize(
    ("kw", "outcome"),
    [
        ({}, RuleOutcome.PASS),
        ({"website_live": False, "has_physical_location": True}, RuleOutcome.PASS),
        ({"website": None, "has_physical_location": False}, RuleOutcome.FAIL),
        ({"website_live": None}, RuleOutcome.UNKNOWN),
    ],
)
def test_location_or_website(kw: dict[str, object], outcome: RuleOutcome) -> None:
    assert ev(facts(**kw)).result(Rule.LOCATION_OR_WEBSITE).outcome is outcome


def test_website_evidence_is_stored() -> None:
    assert ev(facts()).result(Rule.LOCATION_OR_WEBSITE).evidence == "https://beanthere.co.uk"


SIGNALS = (Signal("facebook", 4, date(2026, 5, 1)), Signal("instagram", 20, date(2026, 5, 1)))


@pytest.mark.parametrize(
    ("rules", "outcome"),
    [
        ({"activity_channel_mode": "all"}, RuleOutcome.FAIL),
        ({"activity_channel_mode": "any"}, RuleOutcome.PASS),
        (
            {"activity_channel_mode": "specific", "activity_channels": ["facebook"]},
            RuleOutcome.PASS,
        ),
        (
            {"activity_channel_mode": "specific", "activity_channels": ["tiktok"]},
            RuleOutcome.UNKNOWN,
        ),
    ],
)
def test_activity_channel_modes(rules: dict[str, object], outcome: RuleOutcome) -> None:
    r = ev(facts(signals=SIGNALS), load_rules(rules)).result(Rule.LOW_ACTIVITY)
    assert r.outcome is outcome


def test_last_years_signal_is_ignored_and_latest_wins() -> None:
    old = Signal("facebook", 1, date(2025, 12, 1))
    assert ev(facts(signals=(old,))).result(Rule.LOW_ACTIVITY).outcome is RuleOutcome.UNKNOWN
    newer = (Signal("facebook", 3, date(2026, 2, 1)), Signal("facebook", 15, date(2026, 9, 1)))
    assert ev(facts(signals=newer)).result(Rule.LOW_ACTIVITY).outcome is RuleOutcome.FAIL


@pytest.mark.parametrize(
    ("kw", "rules", "reason"),
    [
        ({"is_suppressed": True}, {}, "Excluded: on suppression list"),
        ({"is_chain": True}, {}, "Excluded: chain or franchise"),
        ({}, {"existing_customer_domains": ["BeanThere.co.uk"]}, "Excluded: already a customer"),
    ],
)
def test_exclusions_reject(kw: dict[str, object], rules: dict[str, object], reason: str) -> None:
    result = ev(facts(**kw, **SEARCHED), load_rules(rules))
    assert result.status is LeadStatus.REJECTED
    assert reason in result.reasons


def test_chains_allowed_when_configured() -> None:
    result = ev(facts(is_chain=True), load_rules({"exclude_chains": False}))
    assert result.result(Rule.NOT_EXCLUDED).outcome is RuleOutcome.PASS


def test_industry_fit() -> None:
    assert industry_keywords("Independent cafes", QualificationRules()) == ["cafe"]
    assert (
        ev(facts(categories=("Hair salon",))).result(Rule.INDUSTRY_FIT).outcome is RuleOutcome.FAIL
    )
    assert ev(facts(categories=())).result(Rule.INDUSTRY_FIT).outcome is RuleOutcome.UNKNOWN
    custom = load_rules({"industry_keywords": ["salon"]})
    assert ev(facts(categories=("Hair salon",)), custom).result(Rule.INDUSTRY_FIT).points == 5


def test_custom_weights_normalise_to_100() -> None:
    rules = load_rules({"weights": {**ScoreWeights().model_dump(), "low_activity": 50}})
    assert ev(facts(**SEARCHED), rules).score == 100
    assert ev(facts(), rules).score == round(90 * 100 / 125)


def test_rules_validation() -> None:
    with pytest.raises(ValidationError):
        load_rules({"review_threshold": 70, "qualified_threshold": 60})
    with pytest.raises(ValidationError):
        load_rules({"activity_channel_mode": "specific"})
    with pytest.raises(ValidationError):
        load_rules({"weights": dict.fromkeys(ScoreWeights().model_dump(), 0)})
    with pytest.raises(ValidationError):
        load_rules({"unknown_key": 1})
    assert load_rules(None) == QualificationRules()
