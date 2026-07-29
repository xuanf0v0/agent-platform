"""Typed section rows unique to the canonical full-US deliverable."""

from enum import StrEnum, unique
from typing import Final, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from amazon_copy.schemas.canonical_deliverable_rows import (
    BilingualText,
    FrozenDeliverableRow,
)
from amazon_copy.schemas.canonical_models import NonBlankText

_DETAILED_BULLET_COUNT_ERROR: Final = "detailed_bullet_count_mismatch"
_SHORT_FIELD_COUNT_ERROR: Final = "short_field_count_mismatch"


@unique
class FactStatus(StrEnum):
    """Evidence authority assigned to one product fact."""

    VERIFIED = "verified"
    OLD_COPY_CLAIM = "old_copy_claim"
    COMPETITOR_CLAIM = "competitor_claim"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RISK = "risk"


@unique
class KeywordClass(StrEnum):
    """Closed keyword taxonomy required by the full-US workflow."""

    CORE = "core"
    SECONDARY = "secondary"
    HIGH_INTENT = "high_intent"
    LONG_TAIL = "long_tail"
    ATTRIBUTE = "attribute"
    MATERIAL = "material"
    STRUCTURE = "structure"
    FUNCTION = "function"
    SCENARIO = "scenario"
    AUDIENCE = "audience"
    PAIN_POINT = "pain_point"
    COMPATIBILITY = "compatibility"
    SYNONYM = "synonym"
    COMPETITOR_LANGUAGE = "competitor_language"
    PROHIBITED = "prohibited"


@unique
class KeywordEvidenceLabel(StrEnum):
    """Permitted evidence labels for keyword claims."""

    SELLERSPRITE = "sellersprite"
    SIF = "sif"
    ABA = "aba"
    AUTOCOMPLETE = "autocomplete"
    PUBLIC_SERP = "public_serp"
    REPEATED_MARKET_LANGUAGE = "repeated_market_language"
    HIGH_INTENT_CANDIDATE = "high_intent_candidate"


@unique
class ShortFieldVariantLabel(StrEnum):
    """Required labels for the three paired short-field variants."""

    A = "A"
    B = "B"
    C = "C"


class EvidenceHeader(FrozenDeliverableRow):
    """Source identities and limitations governing a full-US package."""

    brand: NonBlankText | None = None
    product_type: NonBlankText
    pdp_source_id: NonBlankText
    pdp_snapshot_label: NonBlankText
    pdp_retrieved_at: AwareDatetime
    keyword_source_ids: tuple[NonBlankText, ...] = Field(min_length=1)
    competitor_source_ids: tuple[NonBlankText, ...] = ()
    limitations: tuple[NonBlankText, ...] = ()


class FactTableEntry(FrozenDeliverableRow):
    """One sourced fact with explicit authority and risk."""

    field: NonBlankText
    verified_value: str
    source_id: NonBlankText
    status: FactStatus
    risk: NonBlankText


class PositioningAnalysis(FrozenDeliverableRow):
    """Typed purchase-decision analysis for the full-US package."""

    core_positioning: NonBlankText
    target_users: tuple[NonBlankText, ...] = Field(min_length=1)
    contexts: tuple[NonBlankText, ...] = Field(min_length=1)
    purchase_decisions: tuple[NonBlankText, ...] = Field(min_length=1, max_length=5)
    buyer_concerns: tuple[NonBlankText, ...] = Field(min_length=1)
    advantages: tuple[NonBlankText, ...] = Field(min_length=1)
    limitations: tuple[NonBlankText, ...] = Field(min_length=1)


class KeywordAllocationEntry(FrozenDeliverableRow):
    """One evidence-labeled keyword allocated before drafting."""

    keyword: NonBlankText
    classification: KeywordClass
    evidence_label: KeywordEvidenceLabel
    allocated_fields: tuple[NonBlankText, ...] = Field(min_length=1)


class ShortFieldVariant(FrozenDeliverableRow):
    """One counted and paired Title plus Item Highlights variant."""

    label: ShortFieldVariantLabel
    title: BilingualText
    title_character_count: int = Field(ge=65, le=75)
    item_highlights: BilingualText
    item_highlights_character_count: int = Field(ge=1, le=125)
    main_keywords: tuple[NonBlankText, ...] = Field(min_length=1)
    recommended: bool = False

    @model_validator(mode="after")
    def require_exact_character_counts(self) -> Self:
        """Reject declared counts that do not match the English copy."""
        if self.title_character_count != len(self.title.english):
            raise PydanticCustomError(
                _SHORT_FIELD_COUNT_ERROR,
                "title character count must match the English title",
            )
        if self.item_highlights_character_count != len(self.item_highlights.english):
            raise PydanticCustomError(
                _SHORT_FIELD_COUNT_ERROR,
                "Item Highlights character count must match the English copy",
            )
        return self


class BulletPlanEntry(FrozenDeliverableRow):
    """One buyer-question allocation in the five-bullet plan."""

    position: int = Field(ge=1, le=5)
    buyer_question: NonBlankText
    core_information: NonBlankText
    keyword_theme: NonBlankText
    repetition_to_avoid: NonBlankText


class DetailedBulletEntry(FrozenDeliverableRow):
    """One bilingual detailed bullet with verified English counts."""

    position: int = Field(ge=1, le=5)
    content: BilingualText
    main_intent: NonBlankText
    covered_keywords: tuple[NonBlankText, ...] = Field(min_length=1)
    character_count: int = Field(ge=1)
    word_count: int = Field(ge=1)

    @model_validator(mode="after")
    def require_exact_copy_counts(self) -> Self:
        """Reject stale character or whitespace-delimited word counts."""
        copy = self.content.english
        if self.character_count != len(copy) or self.word_count != len(copy.split()):
            raise PydanticCustomError(
                _DETAILED_BULLET_COUNT_ERROR,
                "detailed bullet counts must match the English copy",
            )
        return self


class QuestionFieldMapEntry(FrozenDeliverableRow):
    """One COSMO or Rufus buyer question mapped to output fields."""

    question: NonBlankText
    intent: NonBlankText
    allocated_fields: tuple[NonBlankText, ...] = Field(min_length=1)


class ComplianceCheck(FrozenDeliverableRow):
    """One machine-readable full-US compliance result."""

    code: NonBlankText
    passed: bool
    detail: NonBlankText


__all__ = [
    "BulletPlanEntry",
    "ComplianceCheck",
    "DetailedBulletEntry",
    "EvidenceHeader",
    "FactStatus",
    "FactTableEntry",
    "KeywordAllocationEntry",
    "KeywordClass",
    "KeywordEvidenceLabel",
    "PositioningAnalysis",
    "QuestionFieldMapEntry",
    "ShortFieldVariant",
    "ShortFieldVariantLabel",
]
