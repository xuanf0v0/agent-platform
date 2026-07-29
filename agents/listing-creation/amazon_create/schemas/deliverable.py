"""Final creation deliverable."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BulletDeliverable(BaseModel):
    """One bilingual bullet."""

    model_config = ConfigDict(frozen=True)

    text: str
    text_zh: str = ""
    purchase_intent_zh: str = ""
    covered_keywords: tuple[str, ...] = ()
    chars: int = 0


class TitleVariant(BaseModel):
    """One compliant Title and Item Highlights direction."""

    model_config = ConfigDict(frozen=True)

    code: Literal["A", "B", "C"]
    strategy_zh: str
    title: str
    title_zh: str = ""
    title_chars: int = 0
    primary_keywords: tuple[str, ...] = ()
    item_highlights: str
    item_highlights_zh: str = ""
    item_highlights_chars: int = 0


class ShoppingQuestion(BaseModel):
    """Evidence-grounded shopping question coverage, not fabricated customer Q&A."""

    model_config = ConfigDict(frozen=True)

    question: str
    answer_basis: str = ""
    answer_zh: str = ""
    listing_answered: bool = False
    location: str = ""
    clarity: str = "待确认"
    missing_information: str = ""


class RiskItem(BaseModel):
    """One compliance or return-risk finding."""

    model_config = ConfigDict(frozen=True)

    risk_type: str
    issue: str
    level: Literal["低", "中", "高", "BLOCK"] = "中"
    recommended_location: str = "Product Description"
    needs_confirmation: bool = False


class UploadReadyCopy(BaseModel):
    """Only fields that can be copied to Seller Central."""

    model_config = ConfigDict(frozen=True)

    title: str = ""
    item_highlights: str = ""
    bullets: tuple[str, ...] = ()
    product_description: str = ""
    search_terms: str = ""


class PlusModule(BaseModel):
    """One suggested A+ / EBC module."""

    model_config = ConfigDict(frozen=True)

    module: str
    purpose: str = ""
    content: str = ""


class CategoryRecommendation(BaseModel):
    """Browse-node candidate with explicit verification status."""

    model_config = ConfigDict(frozen=True)

    path: str
    node_id_path: str = ""
    basis: str = ""
    verification: str = "manual_validation_required"


class ClaimEvidenceMap(BaseModel):
    """Customer-facing claim mapped to an evidence source or unresolved status."""

    model_config = ConfigDict(frozen=True)

    claim: str
    source: str = ""
    status: str = "unresolved"


class ImageBriefItem(BaseModel):
    """One main or secondary image design instruction."""

    model_config = ConfigDict(frozen=True)

    image: str
    selling_point: str = ""
    color_palette: str = ""
    product_angle: str = ""
    background: str = ""
    layout: str = ""
    detail_treatment: str = ""
    image_copy: str = ""


class ImageDesignPlan(BaseModel):
    """ASIN-aware main image plus seven secondary image plan."""

    model_config = ConfigDict(frozen=True)

    task_type: str = "image_design"
    research_basis: tuple[str, ...] = ()
    source_analysis: tuple[str, ...] = ()
    image_scores: dict[str, float] = Field(default_factory=dict)
    images: list[ImageBriefItem] = Field(default_factory=list, min_length=8, max_length=8)
    upload_requests: tuple[str, ...] = ()
    compliance_notes: tuple[str, ...] = ()


class CreationDeliverable(BaseModel):
    """Upload-oriented core fields for a new listing."""

    model_config = ConfigDict(frozen=True)

    title: str
    title_zh: str = ""
    title_chars: int = 0
    item_highlights: str
    item_highlights_zh: str = ""
    item_highlights_chars: int = 0
    title_variants: list[TitleVariant] = Field(default_factory=list, min_length=1, max_length=3)
    recommended_variant: Literal["A", "B", "C"] = "A"
    bullets: list[BulletDeliverable] = Field(min_length=1, max_length=5)
    search_terms: str = ""
    search_terms_chars: int = 0
    search_terms_bytes: int = 0
    product_description: str = ""
    product_description_zh: str = ""
    product_description_chars: int = 0
    shopping_questions: list[ShoppingQuestion] = Field(default_factory=list)
    compliance_risks: list[RiskItem] = Field(default_factory=list)
    return_risks: list[RiskItem] = Field(default_factory=list)
    creation_logic_zh: str = ""
    final_report: dict[str, Any] = Field(default_factory=dict)
    upload_ready: UploadReadyCopy = Field(default_factory=UploadReadyCopy)
    a_plus_modules: list[PlusModule] = Field(default_factory=list)
    keyword_intent_map: dict[str, list[str]] = Field(default_factory=dict)
    category_recommendations: list[CategoryRecommendation] = Field(default_factory=list)
    claim_evidence_map: list[ClaimEvidenceMap] = Field(default_factory=list)
    attribute_checklist: tuple[str, ...] = ()
    compliance_notes: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    policy_status: Literal["PASS", "WARN", "BLOCK"] = "PASS"
    policy_issues: tuple[str, ...] = ()
    notes_zh: str = ""
