"""SEO tables, scorecard, final package, and pipeline state (R11)."""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from amazon_copy.schemas.enums import (
    SCORE_DIMENSIONS,
    SCORE_LABELS_ZH,
    PipelineMode,
    PipelineStage,
    ScoreDimKey,
)
from amazon_copy.schemas.input_research import (  # noqa: TC001 - Pydantic resolves runtime types
    ProductInput,
    ResearchPack,
    SellingPoint,
)
from amazon_copy.schemas.listing import ListingDraft  # noqa: TC001 - Pydantic runtime type

_SCORE_DIM_COUNT: Final[int] = 9


class EmbedRow(BaseModel):
    """Presence row for intent / rootword / keyword tables."""

    model_config = ConfigDict(frozen=True)

    item: str = Field(min_length=1)
    present: bool

    @computed_field
    def mark(self) -> Literal["V", "X"]:
        """Human-readable V/X mark derived only from deterministic presence."""
        return "V" if self.present else "X"


class SEOCheck(BaseModel):
    """Deterministic V/X tables plus optional non-authoritative prose."""

    model_config = ConfigDict(frozen=True)

    intent_rows: list[EmbedRow] = Field(default_factory=list)
    rootword_rows: list[EmbedRow] = Field(default_factory=list)
    keyword_rows: list[EmbedRow] = Field(default_factory=list)
    title_intent_rows: list[EmbedRow] = Field(default_factory=list)
    title_rootword_rows: list[EmbedRow] = Field(default_factory=list)
    title_keyword_rows: list[EmbedRow] = Field(default_factory=list)
    bullet_intent_rows: list[EmbedRow] = Field(default_factory=list)
    bullet_rootword_rows: list[EmbedRow] = Field(default_factory=list)
    bullet_keyword_rows: list[EmbedRow] = Field(default_factory=list)
    narrative: str | None = None

    @staticmethod
    def _present_count(rows: list[EmbedRow]) -> int:
        return sum(row.present for row in rows)

    @computed_field
    def intent_count(self) -> int:
        """Unique intents found across the full listing."""
        return self._present_count(self.intent_rows)

    @computed_field
    def rootword_count(self) -> int:
        """Unique rootwords found across the full listing."""
        return self._present_count(self.rootword_rows)

    @computed_field
    def keyword_count(self) -> int:
        """Unique keywords found across the full listing."""
        return self._present_count(self.keyword_rows)

    @computed_field
    def title_intent_count(self) -> int:
        """Unique intents found in the title."""
        return self._present_count(self.title_intent_rows)

    @computed_field
    def title_rootword_count(self) -> int:
        """Unique rootwords found in the title."""
        return self._present_count(self.title_rootword_rows)

    @computed_field
    def title_keyword_count(self) -> int:
        """Unique keywords found in the title."""
        return self._present_count(self.title_keyword_rows)

    @computed_field
    def bullet_intent_count(self) -> int:
        """Unique intents found across all bullets."""
        return self._present_count(self.bullet_intent_rows)

    @computed_field
    def bullet_rootword_count(self) -> int:
        """Unique rootwords found across all bullets."""
        return self._present_count(self.bullet_rootword_rows)

    @computed_field
    def bullet_keyword_count(self) -> int:
        """Unique keywords found across all bullets."""
        return self._present_count(self.bullet_keyword_rows)


class ScoreDimension(BaseModel):
    """One of nine quality dimensions (0-10)."""

    model_config = ConfigDict(frozen=True)

    key: ScoreDimKey
    score: float = Field(ge=0, le=10)
    rationale: str = ""

    @computed_field
    def label_zh(self) -> str:
        """Stable Chinese label owned by R11, never by model output."""
        return SCORE_LABELS_ZH[self.key]


class Scorecard(BaseModel):
    """Nine-dimension scorecard; overall is mean of 9 rounded to 1 decimal (R11)."""

    model_config = ConfigDict(frozen=True)

    dimensions: list[ScoreDimension] = Field(min_length=9, max_length=9)
    overall: float = Field(ge=0, le=10)

    @model_validator(mode="after")
    def _check_dims_and_overall(self) -> Self:
        keys = [dim.key for dim in self.dimensions]
        expected = list(SCORE_DIMENSIONS)
        if keys != expected:
            msg = f"dimensions must be exactly {expected} in order, got {keys}"
            raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary
        mean = round(sum(dim.score for dim in self.dimensions) / _SCORE_DIM_COUNT, 1)
        if self.overall != mean:
            msg = f"overall {self.overall} != mean of dimensions {mean}"
            raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary
        return self


class SelectionTrace(BaseModel):
    """Why a title candidate won."""

    model_config = ConfigDict(frozen=True)

    winner_index: int = Field(ge=0)
    rationale: str = ""
    hard_ban_passed: list[bool] = Field(default_factory=list)
    seo_v_counts: list[int] = Field(default_factory=list)


class FinalPackage(BaseModel):
    """Complete export payload for listing.json."""

    model_config = ConfigDict(frozen=True)

    product_input: ProductInput
    research: ResearchPack | None = None
    selling_points: list[SellingPoint] = Field(default_factory=list)
    listing: ListingDraft | None = None
    seo: SEOCheck | None = None
    seo2: SEOCheck | None = None
    scorecard: Scorecard | None = None
    selection: SelectionTrace | None = None
    warnings: list[str] = Field(default_factory=list)
    stage: PipelineStage = PipelineStage.COMPLETED
    stage_history: list[PipelineStage] = Field(default_factory=list)
    error: str | None = None


class PipelineState(BaseModel):
    """Mutable orchestration bag; mutation is the documented purpose.

    noqa: MUTABLE_OK — pipeline accumulator updated stage-by-stage.
    """

    model_config = ConfigDict(frozen=False)

    stage: PipelineStage = PipelineStage.RESEARCH
    mode: PipelineMode = PipelineMode.RUN
    product_input: ProductInput
    research: ResearchPack | None = None
    selling_points: list[SellingPoint] = Field(default_factory=list)
    listing: ListingDraft | None = None
    seo: SEOCheck | None = None
    seo2: SEOCheck | None = None
    scorecard: Scorecard | None = None
    selection: SelectionTrace | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
