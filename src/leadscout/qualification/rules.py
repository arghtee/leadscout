"""Editable qualification configuration (spec Section 4, FR-2), stored in `Campaign.rules_json`."""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivityChannelMode(StrEnum):
    """How per-channel post counts combine for the low-activity rule."""

    ALL = "all"  # every channel with data is below N
    ANY = "any"  # at least one channel is below N
    SPECIFIC = "specific"  # every channel in `activity_channels` has data and is below N


class ScoreWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    establishment: int = Field(default=20, ge=0)
    location_or_website: int = Field(default=15, ge=0)
    low_activity: int = Field(default=25, ge=0)
    decision_maker: int = Field(default=20, ge=0)
    contactability: int = Field(default=15, ge=0)
    industry_fit: int = Field(default=5, ge=0)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())

    @property
    def free_signal_total(self) -> int:
        """Weights earnable before any RocketReach person search."""
        return self.establishment + self.location_or_website + self.low_activity + self.industry_fit

    @model_validator(mode="after")
    def _non_zero(self) -> Self:
        if self.total == 0:
            raise ValueError("at least one score weight must be greater than zero")
        return self


class QualificationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_activity_max_posts: int = Field(
        default=12, ge=1, description="Passes when posts this year < N"
    )
    activity_channel_mode: ActivityChannelMode = ActivityChannelMode.ALL
    activity_channels: list[str] = Field(default_factory=list)
    min_business_age_years: float = Field(default=2, ge=0)
    min_review_count: int = Field(default=20, ge=0)
    weights: ScoreWeights = Field(default_factory=lambda: ScoreWeights())
    qualified_threshold: int = Field(default=60, ge=0, le=100)
    review_threshold: int = Field(default=40, ge=0, le=100)
    exclude_chains: bool = True
    existing_customer_domains: list[str] = Field(default_factory=list)
    industry_keywords: list[str] = Field(
        default_factory=list, description="Defaults to words from the campaign industry"
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.review_threshold > self.qualified_threshold:
            raise ValueError("review_threshold must not exceed qualified_threshold")
        if (
            self.activity_channel_mode is ActivityChannelMode.SPECIFIC
            and not self.activity_channels
        ):
            raise ValueError("activity_channels is required when activity_channel_mode is specific")
        return self


def load_rules(raw: dict[str, Any] | None) -> QualificationRules:
    return QualificationRules.model_validate(raw or {})
