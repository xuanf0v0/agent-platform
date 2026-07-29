"""Minimal diagnosis stub for research_context type checks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _FieldCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str = ""
    metric: str = ""
    status: str = "PASS"
    note_zh: str = ""


class _Issue(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: str = "info"
    title: str = ""
    detail_zh: str = ""


class _Backend(BaseModel):
    model_config = ConfigDict(frozen=True)

    notes_zh: str = ""


class _Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str = ""
    label_zh: str = ""
    score: float = 0.0
    rationale_zh: str = ""


class ListingDiagnosisReport(BaseModel):
    """Subset used only for build_diagnosis_summary typing."""

    model_config = ConfigDict(frozen=True)

    scoring_source: str = "stub"
    average_score: float = 0.0
    field_checks: tuple[_FieldCheck, ...] = ()
    issues: tuple[_Issue, ...] = ()
    backend: _Backend = Field(default_factory=_Backend)
    scores: tuple[_Score, ...] = ()
    form_order: tuple[str, ...] = ()
    disclaimer_zh: str = ""
