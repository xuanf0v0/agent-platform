"""Enums and fixed scorecard dimension tables for amazon_copy."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class TitleMode(StrEnum):
    """Title length policy (R4)."""

    SOP_SEO = "sop_seo"
    STRICT_AMAZON = "strict_amazon"


class PipelineMode(StrEnum):
    """CLI / pipeline entry mode."""

    RUN = "run"
    WRITE = "write"
    OPTIMIZE = "optimize"
    SEO = "seo"
    ANALYZE = "analyze"


class PipelineStage(StrEnum):
    """Orchestration stage the pipeline is currently in."""

    RESEARCH = "research"
    SELLING_POINTS = "selling_points"
    TITLE = "title"
    BP_WRITE = "bp_write"
    SEO_CHECK = "seo_check"
    BP_OPTIMIZE = "bp_optimize"
    SEO_CHECK2 = "seo_check2"
    SCORECARD = "scorecard"
    EXPORT = "export"
    COMPLETED = "completed"
    FAILED = "failed"


class ScoreDimKey(StrEnum):
    """Nine scorecard dimensions in fixed order (R11)."""

    COMPLIANCE = "compliance"
    SEO = "seo"
    GRAMMAR = "grammar"
    READABILITY = "readability"
    SELLING_POINTS = "selling_points"
    LOCALIZATION = "localization"
    PROFESSIONALISM = "professionalism"
    EMOTION = "emotion"
    CTA = "cta"


SCORE_DIMENSIONS: Final[tuple[ScoreDimKey, ...]] = (
    ScoreDimKey.COMPLIANCE,
    ScoreDimKey.SEO,
    ScoreDimKey.GRAMMAR,
    ScoreDimKey.READABILITY,
    ScoreDimKey.SELLING_POINTS,
    ScoreDimKey.LOCALIZATION,
    ScoreDimKey.PROFESSIONALISM,
    ScoreDimKey.EMOTION,
    ScoreDimKey.CTA,
)

SCORE_LABELS_ZH: Final[dict[ScoreDimKey, str]] = {
    ScoreDimKey.COMPLIANCE: "合规性",
    ScoreDimKey.SEO: "SEO",
    ScoreDimKey.GRAMMAR: "语法拼写",
    ScoreDimKey.READABILITY: "可读性",
    ScoreDimKey.SELLING_POINTS: "卖点",
    ScoreDimKey.LOCALIZATION: "语言本土化",
    ScoreDimKey.PROFESSIONALISM: "专业性",
    ScoreDimKey.EMOTION: "情感表达",
    ScoreDimKey.CTA: "号召性",
}
