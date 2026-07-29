"""Typed editorial diagnosis report for the automatic workbench sidebar."""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Severity = Literal["PASS", "WARN", "BLOCK"]
PriorityLevel = Literal["P0", "P1"]
ScoreDimension = Literal[
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

DIMENSION_LABELS_ZH: dict[ScoreDimension, str] = {
    "compliance": "合规",
    "a9_seo": "A9 SEO",
    "semantic_coverage": "语义覆盖",
    "grammar": "语法拼写",
    "readability": "可读性",
    "selling_points": "卖点完整性",
    "localization": "美国本地化",
    "technical_accuracy": "专业准确性",
    "emotional_appeal": "情绪与顾虑处理",
    "purchase_motivation": "购买推动力",
}


class FieldCheckRow(BaseModel):
    """One listing field row in the diagnosis field-check table."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    field: NonBlank
    metric: NonBlank
    status: Severity
    note_zh: NonBlank


class PriorityIssue(BaseModel):
    """One prioritized editorial issue."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    level: PriorityLevel
    title: NonBlank
    detail_zh: NonBlank


class BackendTermsDiagnosis(BaseModel):
    """Backend search-terms budget, duplication, and candidate notes."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    terms: str = ""
    bytes_used: int = Field(ge=0)
    max_bytes: int = Field(default=250, ge=1)
    token_count: int = Field(ge=0)
    duplication_pct: float = Field(ge=0, le=100)
    repeated_roots: tuple[str, ...] = ()
    incremental_roots: tuple[str, ...] = ()
    uncovered_candidates: tuple[str, ...] = ()
    risk_notes_zh: tuple[str, ...] = ()
    summary_zh: NonBlank


class EditorialScore(BaseModel):
    """One ten-dimension editorial score with Chinese rationale."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    dimension: ScoreDimension
    label_zh: NonBlank
    score: float = Field(ge=0, le=10)
    rationale_zh: NonBlank


class ListingDiagnosisReport(BaseModel):
    """Structured Chinese diagnosis aligned to the workbench sample format."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    field_checks: tuple[FieldCheckRow, ...] = Field(min_length=1)
    issues: tuple[PriorityIssue, ...] = ()
    backend: BackendTermsDiagnosis
    scores: tuple[EditorialScore, ...] = Field(min_length=10, max_length=10)
    average_score: float = Field(ge=0, le=10)
    fix_order: tuple[NonBlank, ...] = ()
    scoring_source: Literal["llm", "rules"] = "rules"
    disclaimer_zh: NonBlank = (
        "编辑评分仅供参考；发布以优化后审核门禁为准，BLOCK 不会被高分抵消。"
    )


__all__ = [
    "DIMENSION_LABELS_ZH",
    "BackendTermsDiagnosis",
    "EditorialScore",
    "FieldCheckRow",
    "ListingDiagnosisReport",
    "PriorityIssue",
    "ScoreDimension",
]
