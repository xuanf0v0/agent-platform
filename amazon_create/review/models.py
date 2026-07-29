"""Minimal ListingReviewReport stub for research_context type checks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = ""
    severity: str = "WARN"
    field: str = ""
    message_zh: str = ""


class _KeywordRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str = ""
    covered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


class _Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str = ""
    score: float = 0.0
    rationale_zh: str = ""


class ListingReviewReport(BaseModel):
    """Subset used only for build_review_summary typing."""

    model_config = ConfigDict(frozen=True)

    status: str = "PASS"
    format_status: str = "PASS"
    fact_status: str = "PASS"
    release_disposition: str = "release"
    findings: tuple[_Finding, ...] = ()
    keyword_coverage: tuple[_KeywordRow, ...] = ()
    scores: tuple[_Score, ...] = Field(default_factory=tuple)
