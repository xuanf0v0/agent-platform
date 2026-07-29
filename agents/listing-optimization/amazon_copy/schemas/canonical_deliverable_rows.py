"""Typed rows shared by canonical Amazon copy deliverables."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from amazon_copy.schemas.canonical_models import Asin, NonBlankText


class FrozenDeliverableRow(BaseModel):
    """Immutable strict base for deliverable section rows."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class BilingualText(FrozenDeliverableRow):
    """English copy paired with its Chinese translation."""

    english: NonBlankText
    chinese: NonBlankText


class AuditFinding(FrozenDeliverableRow):
    """Evidence-linked diagnosis item from Stage 1."""

    code: NonBlankText
    priority: int = Field(ge=1, le=5)
    summary: NonBlankText
    evidence_ids: tuple[NonBlankText, ...] = ()


class BaselineEntry(FrozenDeliverableRow):
    """One current-listing value and its baseline source."""

    field: NonBlankText
    current_value: str
    source_id: NonBlankText


class KeywordCoverageEntry(FrozenDeliverableRow):
    """One keyword intent mapped to current and proposed fields."""

    keyword: NonBlankText
    intent: NonBlankText
    current_fields: tuple[NonBlankText, ...]
    proposed_fields: tuple[NonBlankText, ...]


class CompetitorTitleEntry(FrozenDeliverableRow):
    """Sourced competitor title used for a Stage 1 benchmark."""

    asin: Asin
    title: NonBlankText
    source_id: NonBlankText


class ScoreEntry(FrozenDeliverableRow):
    """One bounded audit score with its reason."""

    dimension: NonBlankText
    score: int = Field(ge=0, le=100)
    reason: NonBlankText


class StrategyEntry(FrozenDeliverableRow):
    """One Stage 2 optimization action and rationale."""

    action: NonBlankText
    rationale: NonBlankText


class ValidationMetric(FrozenDeliverableRow):
    """Post-publish observation target for the validation window."""

    name: NonBlankText
    window: NonBlankText
    target: NonBlankText


class KeywordAuditEntry(FrozenDeliverableRow):
    """Required and observed embedding locations for one keyword."""

    keyword: NonBlankText
    required_locations: tuple[NonBlankText, ...] = Field(min_length=1)
    observed_locations: tuple[NonBlankText, ...] = ()
    embedded: bool


__all__ = [
    "AuditFinding",
    "BaselineEntry",
    "BilingualText",
    "CompetitorTitleEntry",
    "FrozenDeliverableRow",
    "KeywordAuditEntry",
    "KeywordCoverageEntry",
    "ScoreEntry",
    "StrategyEntry",
    "ValidationMetric",
]
