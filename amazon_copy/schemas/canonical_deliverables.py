"""Discriminated canonical deliverables for audit and generation workflows."""

from enum import StrEnum, unique
from typing import Annotated, Final, Literal, TypeAlias, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from amazon_copy.schemas.canonical_deliverable_rows import (
    AuditFinding,
    BaselineEntry,
    BilingualText,
    CompetitorTitleEntry,
    FrozenDeliverableRow,
    KeywordAuditEntry,
    KeywordCoverageEntry,
    ScoreEntry,
    StrategyEntry,
    ValidationMetric,
)
from amazon_copy.schemas.canonical_full_us_rows import (
    BulletPlanEntry,
    ComplianceCheck,
    DetailedBulletEntry,
    EvidenceHeader,
    FactStatus,
    FactTableEntry,
    KeywordAllocationEntry,
    KeywordClass,
    KeywordEvidenceLabel,
    PositioningAnalysis,
    QuestionFieldMapEntry,
    ShortFieldVariant,
    ShortFieldVariantLabel,
)
from amazon_copy.schemas.canonical_models import Asin, CanonicalMarketplace, NonBlankText

_BACKEND_BYTE_ERROR: Final = "backend_search_term_byte_mismatch"
_FULL_US_ALIGNMENT_ERROR: Final = "full_us_bullet_alignment"
_SHORT_FIELD_SET_ERROR: Final = "short_field_variant_set_invalid"
_EXPECTED_BULLET_POSITIONS: Final = (1, 2, 3, 4, 5)
_EXPECTED_SHORT_FIELD_LABELS: Final = (
    ShortFieldVariantLabel.A,
    ShortFieldVariantLabel.B,
    ShortFieldVariantLabel.C,
)


@unique
class DeliverableKind(StrEnum):
    """Closed set of canonical output contracts."""

    SCOPED_TITLE_AUDIT = "scoped_title_audit"
    FULL_STAGE_1 = "full_stage_1"
    NORMAL_STAGE_2 = "normal_stage_2"
    FULL_US = "full_us"
    KEYWORD_AUDIT = "keyword_audit"


class ScopedTitleAudit(FrozenDeliverableRow):
    """Title-only audit with scores and an approval gate."""

    kind: Literal[DeliverableKind.SCOPED_TITLE_AUDIT] = DeliverableKind.SCOPED_TITLE_AUDIT
    marketplace: CanonicalMarketplace
    asin: Asin | None = None
    current_title: NonBlankText
    findings: tuple[AuditFinding, ...] = Field(min_length=1)
    scores: tuple[ScoreEntry, ...] = Field(min_length=1)
    approval_question_code: Literal["stage_1_approval"] = "stage_1_approval"


class FullStage1Audit(FrozenDeliverableRow):
    """Complete Stage 1 diagnosis, benchmarks, scores, and priorities."""

    kind: Literal[DeliverableKind.FULL_STAGE_1] = DeliverableKind.FULL_STAGE_1
    marketplace: CanonicalMarketplace
    asin: Asin | None = None
    diagnosis_summary: NonBlankText
    baseline_table: tuple[BaselineEntry, ...] = Field(min_length=1)
    keyword_coverage: tuple[KeywordCoverageEntry, ...] = Field(min_length=1)
    competitor_title_benchmarks: tuple[CompetitorTitleEntry, ...] = ()
    scores: tuple[ScoreEntry, ...] = Field(min_length=1)
    priorities: tuple[NonBlankText, ...] = Field(min_length=1)
    approval_question_code: Literal["stage_1_approval"] = "stage_1_approval"


class NormalStage2Deliverable(FrozenDeliverableRow):
    """Bilingual upload-ready fields produced after authorization."""

    kind: Literal[DeliverableKind.NORMAL_STAGE_2] = DeliverableKind.NORMAL_STAGE_2
    marketplace: CanonicalMarketplace
    asin: Asin | None = None
    strategy: tuple[StrategyEntry, ...] = Field(min_length=1)
    title: BilingualText
    item_highlights: BilingualText
    bullets: tuple[BilingualText, ...] = Field(min_length=1, max_length=10)
    keyword_comparison: tuple[KeywordCoverageEntry, ...] = Field(min_length=1)
    approval_checklist: tuple[NonBlankText, ...] = Field(min_length=1)
    validation_metrics: tuple[ValidationMetric, ...] = Field(min_length=1)


class FullUsDeliverable(FrozenDeliverableRow):
    """Complete evidence-bound US optimization and upload package."""

    kind: Literal[DeliverableKind.FULL_US] = DeliverableKind.FULL_US
    marketplace: Literal[CanonicalMarketplace.US] = CanonicalMarketplace.US
    asin: Asin | None = None
    evidence_header: EvidenceHeader
    fact_table: tuple[FactTableEntry, ...] = Field(min_length=1)
    positioning: PositioningAnalysis
    keyword_allocation: tuple[KeywordAllocationEntry, ...] = Field(min_length=1)
    strategy: tuple[StrategyEntry, ...] = Field(min_length=1)
    short_field_variants: tuple[ShortFieldVariant, ...] = Field(min_length=3, max_length=3)
    bullet_plan: tuple[BulletPlanEntry, ...] = Field(min_length=5, max_length=5)
    detailed_bullets: tuple[DetailedBulletEntry, ...] = Field(min_length=5, max_length=5)
    product_description: BilingualText
    backend_search_terms: NonBlankText
    backend_search_term_bytes: int = Field(ge=1, le=249)
    question_to_field_map: tuple[QuestionFieldMapEntry, ...] = ()
    approval_checklist: tuple[NonBlankText, ...] = Field(min_length=1)
    compliance_checks: tuple[ComplianceCheck, ...] = Field(min_length=1)
    validation_metrics: tuple[ValidationMetric, ...] = Field(min_length=1)
    upload_only_bullets: tuple[NonBlankText, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def require_complete_short_field_set(self) -> "FullUsDeliverable":
        """Require ordered A/B/C pairs with exactly one recommendation."""
        labels = tuple(item.label for item in self.short_field_variants)
        recommended_count = sum(item.recommended for item in self.short_field_variants)
        if labels != _EXPECTED_SHORT_FIELD_LABELS or recommended_count != 1:
            raise PydanticCustomError(
                _SHORT_FIELD_SET_ERROR,
                "short-field variants must be ordered A/B/C with one recommendation",
            )
        return self

    @model_validator(mode="after")
    def require_aligned_bullet_sections(self) -> "FullUsDeliverable":
        """Keep planning, detailed copy, and upload-only bullets one-to-one."""
        plan_positions = tuple(item.position for item in self.bullet_plan)
        detailed_positions = tuple(item.position for item in self.detailed_bullets)
        detailed_copy = tuple(item.content.english for item in self.detailed_bullets)
        if (
            plan_positions != _EXPECTED_BULLET_POSITIONS
            or detailed_positions != _EXPECTED_BULLET_POSITIONS
            or self.upload_only_bullets != detailed_copy
        ):
            raise PydanticCustomError(
                _FULL_US_ALIGNMENT_ERROR,
                "bullet sections must align in positions 1 through 5",
            )
        return self

    @model_validator(mode="after")
    def require_exact_backend_byte_count(self) -> "FullUsDeliverable":
        """Keep the declared UTF-8 byte count synchronized with backend terms."""
        if self.backend_search_term_bytes != len(self.backend_search_terms.encode("utf-8")):
            raise PydanticCustomError(
                _BACKEND_BYTE_ERROR,
                "backend search-term byte count must match UTF-8 encoding",
            )
        return self


class KeywordAuditDeliverable(FrozenDeliverableRow):
    """Keyword-embedding audit with explicit missing roots."""

    kind: Literal[DeliverableKind.KEYWORD_AUDIT] = DeliverableKind.KEYWORD_AUDIT
    marketplace: CanonicalMarketplace
    asin: Asin | None = None
    rows: tuple[KeywordAuditEntry, ...] = Field(min_length=1)
    missing_keywords: tuple[NonBlankText, ...] = ()
    summary: NonBlankText


AuditDeliverable: TypeAlias = Annotated[
    ScopedTitleAudit | FullStage1Audit,
    Field(discriminator="kind"),
]
CanonicalDeliverable: TypeAlias = Annotated[
    ScopedTitleAudit
    | FullStage1Audit
    | NormalStage2Deliverable
    | FullUsDeliverable
    | KeywordAuditDeliverable,
    Field(discriminator="kind"),
]


def deliverable_kind(deliverable: CanonicalDeliverable) -> DeliverableKind:
    """Return the discriminator through an exhaustiveness-checked match."""
    match deliverable:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case ScopedTitleAudit(kind=kind):
            return kind
        case FullStage1Audit(kind=kind):
            return kind
        case NormalStage2Deliverable(kind=kind):
            return kind
        case FullUsDeliverable(kind=kind):
            return kind
        case KeywordAuditDeliverable(kind=kind):
            return kind
    assert_never(deliverable)


__all__ = [
    "AuditDeliverable",
    "AuditFinding",
    "BaselineEntry",
    "BilingualText",
    "BulletPlanEntry",
    "CanonicalDeliverable",
    "CompetitorTitleEntry",
    "ComplianceCheck",
    "DeliverableKind",
    "DetailedBulletEntry",
    "EvidenceHeader",
    "FactStatus",
    "FactTableEntry",
    "FullStage1Audit",
    "FullUsDeliverable",
    "KeywordAllocationEntry",
    "KeywordAuditDeliverable",
    "KeywordAuditEntry",
    "KeywordClass",
    "KeywordCoverageEntry",
    "KeywordEvidenceLabel",
    "NormalStage2Deliverable",
    "PositioningAnalysis",
    "QuestionFieldMapEntry",
    "ScopedTitleAudit",
    "ScoreEntry",
    "ShortFieldVariant",
    "ShortFieldVariantLabel",
    "StrategyEntry",
    "ValidationMetric",
    "deliverable_kind",
]
