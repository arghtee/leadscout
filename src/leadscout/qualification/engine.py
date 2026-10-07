"""Pure qualification rules and scoring (spec Section 4). No I/O; callers build `BusinessFacts`.

Two stages (ASSUMPTIONS R1/R2):
- `pre_lookup`: free signals only. Decides `lookup_eligible`, the gate for spending person-search /
  lookup credits. A pre-lookup lead is never "qualified".
- `final`: after contact search, decision-maker and contactability are scored too.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from leadscout.enums import Confidence, LeadStatus, RuleOutcome, ScoreStage
from leadscout.qualification.roles import match_role
from leadscout.qualification.rules import ActivityChannelMode, QualificationRules


class Rule(StrEnum):
    ESTABLISHMENT = "establishment"
    LOCATION_OR_WEBSITE = "location_or_website"
    LOW_ACTIVITY = "low_activity"
    NOT_EXCLUDED = "not_excluded"
    INDUSTRY_FIT = "industry_fit"
    DECISION_MAKER = "decision_maker"
    CONTACTABILITY = "contactability"


GATE_RULES = (Rule.ESTABLISHMENT, Rule.LOCATION_OR_WEBSITE, Rule.LOW_ACTIVITY, Rule.NOT_EXCLUDED)
_INDUSTRY_STOPWORDS = frozenset(
    {"and", "the", "for", "independent", "local", "small", "shop", "shops", "service", "services"}
)


@dataclass(frozen=True)
class Signal:
    channel: str
    posts_ytd: int | None
    as_of: date
    confidence: Confidence = Confidence.MEDIUM


@dataclass(frozen=True)
class ContactFacts:
    role: str | None
    email_valid: bool = False
    phone_valid: bool = False


@dataclass(frozen=True)
class BusinessFacts:
    company_status: str | None = None
    incorporated_on: date | None = None
    domain: str | None = None
    domain_age_years: float | None = None
    review_count: int | None = None
    address: str | None = None
    has_physical_location: bool | None = None
    website: str | None = None
    website_live: bool | None = None
    categories: tuple[str, ...] = ()
    signals: tuple[Signal, ...] = ()
    is_chain: bool | None = None
    is_suppressed: bool = False
    contacts_searched: bool = False
    contacts: tuple[ContactFacts, ...] = ()


@dataclass(frozen=True)
class RuleResult:
    rule: Rule
    outcome: RuleOutcome
    reason: str
    points: int = 0
    evidence: str | None = None
    hard_reject: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.value,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "points": self.points,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Evaluation:
    score: int
    status: LeadStatus
    stage: ScoreStage
    lookup_eligible: bool
    results: tuple[RuleResult, ...]
    summary: str = ""
    reasons: list[str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", [r.reason for r in self.results] + [self.summary])

    def result(self, rule: Rule) -> RuleResult:
        return next(r for r in self.results if r.rule is rule)


def _years_between(start: date, end: date) -> float:
    return (end - start).days / 365.25


def check_establishment(facts: BusinessFacts, rules: QualificationRules, today: date) -> RuleResult:
    rule, min_age = Rule.ESTABLISHMENT, rules.min_business_age_years
    status = (facts.company_status or "").strip().lower()
    if status == "dissolved":
        return RuleResult(rule, RuleOutcome.FAIL, "Company dissolved", hard_reject=True)

    company_age = (
        _years_between(facts.incorporated_on, today)
        if facts.incorporated_on and status == "active"
        else None
    )
    if company_age is not None and company_age >= min_age:
        return RuleResult(
            rule,
            RuleOutcome.PASS,
            f"Established: active company incorporated {facts.incorporated_on:%Y} "
            f"({int(company_age)} years)",
        )
    if facts.domain_age_years is not None and facts.domain_age_years >= min_age:
        return RuleResult(
            rule,
            RuleOutcome.PASS,
            f"Established: domain registered {int(facts.domain_age_years)} years ago",
            evidence=facts.domain,
        )
    if facts.review_count is not None and facts.review_count >= rules.min_review_count:
        return RuleResult(
            rule, RuleOutcome.PASS, f"Established: {facts.review_count} reviews on map listing"
        )
    if company_age is None and facts.domain_age_years is None and facts.review_count is None:
        return RuleResult(
            rule, RuleOutcome.UNKNOWN, "Establishment unknown: no company, domain or review data"
        )
    return RuleResult(
        rule,
        RuleOutcome.FAIL,
        f"Not established: under {min_age:g} years old and fewer than "
        f"{rules.min_review_count} reviews",
    )


def check_location_or_website(facts: BusinessFacts) -> RuleResult:
    rule = Rule.LOCATION_OR_WEBSITE
    if facts.website and facts.website_live:
        return RuleResult(rule, RuleOutcome.PASS, "Has a live website", evidence=facts.website)
    if facts.has_physical_location:
        return RuleResult(
            rule, RuleOutcome.PASS, "Has a verified street address", evidence=facts.address
        )
    no_site = not facts.website or facts.website_live is False
    if facts.has_physical_location is False and no_site:
        return RuleResult(rule, RuleOutcome.FAIL, "No verified address and no live website")
    return RuleResult(rule, RuleOutcome.UNKNOWN, "Address and website not yet verified")


def check_low_activity(facts: BusinessFacts, rules: QualificationRules, today: date) -> RuleResult:
    rule, n = Rule.LOW_ACTIVITY, rules.low_activity_max_posts
    latest: dict[str, Signal] = {}
    for s in facts.signals:
        if s.posts_ytd is None or s.as_of.year != today.year:
            continue
        key = s.channel.lower()
        if key not in latest or s.as_of > latest[key].as_of:
            latest[key] = s

    if rules.activity_channel_mode is ActivityChannelMode.SPECIFIC:
        wanted = [c.lower() for c in rules.activity_channels]
        missing = [c for c in wanted if c not in latest]
        if missing:
            return RuleResult(
                rule,
                RuleOutcome.UNKNOWN,
                f"Activity unknown: no posting data this year for {', '.join(missing)}",
            )
        latest = {c: latest[c] for c in wanted}
    if not latest:
        return RuleResult(rule, RuleOutcome.UNKNOWN, "Activity unknown: no posting data this year")

    pick = min if rules.activity_channel_mode is ActivityChannelMode.ANY else max
    deciding = pick(latest.values(), key=lambda s: s.posts_ytd or 0)
    posts = deciding.posts_ytd or 0
    detail = f"{posts} posts this year on {deciding.channel} ({deciding.confidence} confidence)"
    if posts < n:
        return RuleResult(
            rule, RuleOutcome.PASS, f"Low activity: {detail}", points=rules.weights.low_activity
        )
    return RuleResult(rule, RuleOutcome.FAIL, f"Active on social: {detail}, limit is under {n}")


def check_not_excluded(facts: BusinessFacts, rules: QualificationRules) -> RuleResult:
    rule = Rule.NOT_EXCLUDED
    customers = {d.lower() for d in rules.existing_customer_domains}
    if facts.is_suppressed:
        return RuleResult(rule, RuleOutcome.FAIL, "Excluded: on suppression list", hard_reject=True)
    if facts.domain and facts.domain.lower() in customers:
        return RuleResult(rule, RuleOutcome.FAIL, "Excluded: already a customer", hard_reject=True)
    if rules.exclude_chains and facts.is_chain:
        return RuleResult(rule, RuleOutcome.FAIL, "Excluded: chain or franchise", hard_reject=True)
    return RuleResult(rule, RuleOutcome.PASS, "Not excluded")


def industry_keywords(industry: str, rules: QualificationRules) -> list[str]:
    if rules.industry_keywords:
        return [k.lower() for k in rules.industry_keywords]
    words = [w for w in industry.lower().replace(",", " ").split() if len(w) >= 3]
    return [w.removesuffix("s") for w in words if w not in _INDUSTRY_STOPWORDS]


def check_industry_fit(facts: BusinessFacts, keywords: Sequence[str]) -> RuleResult:
    rule = Rule.INDUSTRY_FIT
    if not facts.categories:
        return RuleResult(rule, RuleOutcome.UNKNOWN, "Industry fit unknown: no categories")
    for category in facts.categories:
        if any(k in category.lower() for k in keywords):
            return RuleResult(rule, RuleOutcome.PASS, f"Fits industry: {category}")
    return RuleResult(rule, RuleOutcome.FAIL, "Categories do not match the campaign industry")


def check_decision_maker(facts: BusinessFacts, target_roles: Sequence[str]) -> RuleResult:
    rule = Rule.DECISION_MAKER
    if not facts.contacts_searched:
        return RuleResult(rule, RuleOutcome.UNKNOWN, "Decision maker not searched yet")
    for contact in facts.contacts:
        match = match_role(contact.role, target_roles)
        if match:
            return RuleResult(
                rule,
                RuleOutcome.PASS,
                f"Decision maker found: {contact.role} (matches {match.target!r})",
            )
    return RuleResult(rule, RuleOutcome.FAIL, "No contact matching the target roles")


def check_contactability(facts: BusinessFacts) -> RuleResult:
    rule = Rule.CONTACTABILITY
    if not facts.contacts_searched:
        return RuleResult(rule, RuleOutcome.UNKNOWN, "Contact details not retrieved yet")
    if any(c.email_valid for c in facts.contacts):
        return RuleResult(rule, RuleOutcome.PASS, "Contactable: valid business email")
    if any(c.phone_valid for c in facts.contacts):
        return RuleResult(rule, RuleOutcome.PASS, "Contactable: valid phone")
    return RuleResult(rule, RuleOutcome.FAIL, "No valid business email or phone")


def _with_points(result: RuleResult, weight: int) -> RuleResult:
    points = weight if result.outcome is RuleOutcome.PASS else 0
    return RuleResult(
        result.rule, result.outcome, result.reason, points, result.evidence, result.hard_reject
    )


def evaluate(
    facts: BusinessFacts,
    rules: QualificationRules,
    *,
    industry: str,
    target_roles: Sequence[str],
    today: date,
) -> Evaluation:
    w = rules.weights
    results = (
        _with_points(check_establishment(facts, rules, today), w.establishment),
        _with_points(check_location_or_website(facts), w.location_or_website),
        _with_points(check_low_activity(facts, rules, today), w.low_activity),
        check_not_excluded(facts, rules),
        _with_points(check_industry_fit(facts, industry_keywords(industry, rules)), w.industry_fit),
        _with_points(check_decision_maker(facts, target_roles), w.decision_maker),
        _with_points(check_contactability(facts), w.contactability),
    )
    by_rule = {r.rule: r for r in results}
    raw = sum(r.points for r in results)
    score = round(raw * 100 / w.total)

    free_points = sum(
        by_rule[r].points
        for r in (
            Rule.ESTABLISHMENT,
            Rule.LOCATION_OR_WEBSITE,
            Rule.LOW_ACTIVITY,
            Rule.INDUSTRY_FIT,
        )
    )
    gates_pass = all(by_rule[r].outcome is RuleOutcome.PASS for r in GATE_RULES)
    # Pre-lookup threshold scaled to the weights available before any person search (R1).
    lookup_eligible = (
        gates_pass and free_points * 100 >= rules.qualified_threshold * w.free_signal_total
    )

    stage = ScoreStage.FINAL if facts.contacts_searched else ScoreStage.PRE_LOOKUP
    activity_unknown = by_rule[Rule.LOW_ACTIVITY].outcome is RuleOutcome.UNKNOWN
    if any(r.hard_reject for r in results):
        status = LeadStatus.REJECTED
    elif activity_unknown:
        status = LeadStatus.REVIEW
    elif stage is ScoreStage.PRE_LOOKUP:
        eligible_or_band = lookup_eligible or score >= rules.review_threshold
        status = LeadStatus.REVIEW if eligible_or_band else LeadStatus.REJECTED
    elif score >= rules.qualified_threshold:
        status = LeadStatus.QUALIFIED
    elif score >= rules.review_threshold:
        status = LeadStatus.REVIEW
    else:
        status = LeadStatus.REJECTED

    summary = f"Score {score} (qualified at {rules.qualified_threshold})"
    if stage is ScoreStage.PRE_LOOKUP and lookup_eligible and status is not LeadStatus.REJECTED:
        summary += "; eligible for contact lookup"
    return Evaluation(score, status, stage, lookup_eligible, results, summary)
