"""Typed boundaries for evidence-first listing review."""

from enum import IntEnum, StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Severity = Literal["PASS", "WARN", "BLOCK"]


class EvidenceSource(IntEnum):
    """Conflict priority; lower values have stronger authority."""

    AMAZON_PRODUCT_TYPE_RULE = 1
    CATEGORY_TEMPLATE_VALIDATOR = 2
    LEGAL_SAFETY = 3
    PACKAGING_BOM_USER = 4
    AMAZON_FIRST_PARTY_DATA = 5
    THIRD_PARTY_PUBLIC_DATA = 6
    COMPETITOR_LANGUAGE = 7
    WRITING_HYPOTHESIS = 8


class VariationRole(StrEnum):
    """Listing variation scope used by title checks."""

    STANDALONE = "standalone"
    PARENT = "parent"
    CHILD = "child"


class ReviewPhase(StrEnum):
    """Deterministic review position in the automatic workflow."""

    SOURCE = "source"
    POSTFLIGHT = "postflight"


class FactCategory(StrEnum):
    """Closed product-fact classes used by deterministic authorization."""

    BOM = "bom"
    COUNT = "count"
    DIMENSION = "dimension"
    MATERIAL = "material"
    COMPATIBILITY = "compatibility"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    CERTIFICATION = "certification"
    VARIATION = "variation"
    EXCLUSION = "exclusion"


ReviewDisposition = Literal["auto_repair", "ask_user", "terminal"]


class MarketplaceRules(BaseModel):
    """Resolved field limits for one marketplace and product type."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: NonBlank = "US"
    product_type: NonBlank
    title_max: int = Field(default=75, ge=1)
    item_highlights_max: int = Field(default=125, ge=1)
    backend_search_terms_max_bytes: int = Field(default=250, ge=1)
    supported_bullet_count: int = Field(default=5, ge=1, le=10)


class FactClaim(BaseModel):
    """One product or policy fact with provenance and SKU scope."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    key: NonBlank
    value: NonBlank
    source: EvidenceSource
    sku_scope: NonBlank


class FactRequirement(BaseModel):
    """One closed claim matcher that requires structured product evidence."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: NonBlank
    category: FactCategory
    fact_key: NonBlank
    key_aliases: tuple[NonBlank, ...] = ()
    claim_patterns: tuple[NonBlank, ...]
    evidence_needed: NonBlank
    authorization_mode: Literal["affirmative", "matching_value"] = "matching_value"


class ListingReviewRequest(BaseModel):
    """Complete input for deterministic preflight or postflight review."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    title: NonBlank
    item_highlights: str = ""
    bullets: tuple[NonBlank, ...] = Field(min_length=1, max_length=10)
    backend_search_terms: str = ""
    rules: MarketplaceRules
    variation_role: VariationRole = VariationRole.STANDALONE
    child_only_terms: tuple[NonBlank, ...] = ()
    claims: tuple[FactClaim, ...] = ()
    fact_requirements: tuple[FactRequirement, ...] = ()
    baseline_fact_signatures: tuple[NonBlank, ...] = ()
    primary_terms: tuple[NonBlank, ...] = ()
    secondary_terms: tuple[NonBlank, ...] = ()
    phase: ReviewPhase = ReviewPhase.SOURCE


class ReviewFormInput(BaseModel):
    """Raw but typed values submitted by the Streamlit review form."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: NonBlank
    product_type: NonBlank
    variation_role: VariationRole
    child_only_terms: str = ""
    backend_search_terms: str = ""
    primary_terms: str = ""
    secondary_terms: str = ""
    evidence_text: str = ""
    title_max: int = Field(default=75, ge=1)
    highlights_max: int = Field(default=125, ge=1)
    search_terms_max_bytes: int = Field(default=250, ge=1)
    supported_bullet_count: int = Field(default=5, ge=1, le=10)


class ReviewFinding(BaseModel):
    """One located decision with a stable machine-readable code."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    code: NonBlank
    severity: Severity
    field: NonBlank
    message_zh: NonBlank
    evidence_required: str = ""
    claim_terms: tuple[NonBlank, ...] = ()
    fact_key: str = ""
    question_code: str = ""


class ClarificationQuestion(BaseModel):
    """One located seller question required to resolve a core fact."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: NonBlank
    finding_code: NonBlank
    fact_key: NonBlank
    question_zh: NonBlank
    evidence_needed: NonBlank
    claim_terms: tuple[NonBlank, ...] = ()


class ResolvedFact(BaseModel):
    """Highest-authority non-conflicting fact selected for generation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    key: NonBlank
    value: NonBlank
    source: EvidenceSource
    sku_scope: NonBlank


class KeywordCoverage(BaseModel):
    """Text-relevance coverage for one listing field."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    field: Literal["title", "item_highlights", "bullets", "backend_search_terms"]
    covered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


class ReviewScore(BaseModel):
    """One non-compensating review dimension score."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    dimension: Literal[
        "compliance",
        "a9_seo",
        "semantic_coverage",
        "grammar",
        "readability",
        "selling_points",
        "localization",
        "technical_accuracy",
        "emotional_appeal",
        "purchase_motivation",
    ]
    score: float = Field(ge=0, le=10)
    rationale_zh: NonBlank


class ListingReviewReport(BaseModel):
    """Review result; blocking findings always disable optimization."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: Severity
    format_status: Severity = "PASS"
    fact_status: Severity = "PASS"
    release_disposition: Literal["release", "clarify", "block"] = "release"
    can_optimize: bool
    findings: tuple[ReviewFinding, ...]
    resolved_facts: tuple[ResolvedFact, ...]
    keyword_coverage: tuple[KeywordCoverage, ...]
    keyword_basis: Literal["text_relevance_only", "first_party_data", "third_party_data"]
    scores: tuple[ReviewScore, ...] = Field(min_length=10, max_length=10)
    overall_score: None = None
    disposition: ReviewDisposition = "auto_repair"
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
