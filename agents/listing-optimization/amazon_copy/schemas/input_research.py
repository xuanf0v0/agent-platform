"""Product input and research-pack domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from amazon_copy.schemas.metrics import parse_csv_terms


class ProductInput(BaseModel):
    """User-facing product brief for a listing run."""

    model_config = ConfigDict(frozen=True)

    product: str = Field(min_length=1, description="Product name / core description")
    seller_name: str | None = Field(
        default=None,
        description="Optional known seller identity used only for deterministic title exclusion",
    )
    market: str = Field(min_length=1, description="Target marketplace (US, UK, ...)")
    instruction: str = Field(
        default="",
        description="Extra writing instruction; empty -> instruction_missing",
    )
    asin1: str | None = Field(default=None, description="Competitor ASIN block 1")
    asin2: str | None = Field(default=None, description="Competitor ASIN block 2")
    asin3: str | None = Field(default=None, description="Competitor ASIN block 3")
    asin4: str | None = Field(default=None, description="Competitor ASIN block 4")
    rootwords: list[str] = Field(min_length=1, description="Root words (min 1)")
    keywords: list[str] = Field(min_length=1, description="Keywords (min 1)")
    locale: str | None = Field(default=None, description="Target locale override")

    @field_validator("seller_name", mode="before")
    @classmethod
    def _normalize_seller_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("asin1", "asin2", "asin3", "asin4", mode="before")
    @classmethod
    def _empty_asin_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("rootwords", "keywords", mode="before")
    @classmethod
    def _coerce_csv(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            return parse_csv_terms(value)
        return value

    @computed_field
    def instruction_missing(self) -> bool:
        """True when instruction is blank (soft flag; pipeline still runs)."""
        return not self.instruction.strip()


class AudienceProfile(BaseModel):
    """Target audience summary from research."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    segments: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)


class MotiveItem(BaseModel):
    """Purchase motive with optional evidence."""

    model_config = ConfigDict(frozen=True)

    motive: str = Field(min_length=1)
    evidence: str = ""
    weight: float = Field(default=1.0, ge=0)


class FeedbackPack(BaseModel):
    """Aggregated voice-of-customer style feedback."""

    model_config = ConfigDict(frozen=True)

    positives: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)


class CompetitorAnalysis(BaseModel):
    """Optional competitor synthesis; empty pack is valid when no ASINs."""

    model_config = ConfigDict(frozen=True)

    parameters: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    copy_notes: list[str] = Field(default_factory=list)
    raw_blocks: list[str] = Field(default_factory=list)


class ResearchPack(BaseModel):
    """Assembled research output before selling-point generation."""

    model_config = ConfigDict(frozen=True)

    audience: AudienceProfile
    motives: list[MotiveItem] = Field(default_factory=list)
    feedback: FeedbackPack = Field(default_factory=FeedbackPack)
    product_intro: str = ""
    instruction_decode: str = ""
    competitor: CompetitorAnalysis = Field(default_factory=CompetitorAnalysis)


class SellingPoint(BaseModel):
    """Ranked bilingual selling point."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1, le=5)
    text_en: str = Field(min_length=1)
    text_zh: str = Field(min_length=1)
    rationale: str = ""
