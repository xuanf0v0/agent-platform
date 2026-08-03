"""Public request and result models for the research API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ResearchMode(StrEnum):
    DISCOVER = "discover"
    VALIDATE = "validate"
    COMPARE = "compare"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class Decision(StrEnum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"


class ResearchConstraints(BaseModel):
    budget_usd: float | None = Field(default=None, ge=0)
    price_min_usd: float = Field(default=18, ge=0)
    price_max_usd: float = Field(default=60, ge=0)
    min_margin_pct: float = Field(default=20, ge=0, le=100)
    target_margin_pct: float = Field(default=25, ge=0, le=100)
    min_roi_pct: float = Field(default=50, ge=0)
    max_reviews: int | None = Field(default=500, ge=0)
    allowed_categories: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)

    @field_validator("price_max_usd")
    @classmethod
    def price_range_is_valid(cls, value: float, info: Any) -> float:
        minimum = info.data.get("price_min_usd", 0)
        if value < minimum:
            raise ValueError("price_max_usd must be greater than or equal to price_min_usd")
        return value


class ResearchRequest(BaseModel):
    mode: ResearchMode = ResearchMode.DISCOVER
    prompt: str = Field(min_length=2, max_length=16000)
    marketplace: str = Field(default="US", min_length=2, max_length=8)
    constraints: ResearchConstraints = Field(default_factory=ResearchConstraints)
    candidate_refs: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("marketplace")
    @classmethod
    def normalize_marketplace(cls, value: str) -> str:
        return value.strip().upper()


class Evidence(BaseModel):
    evidence_id: str
    provider: str
    tool: str
    claim: str
    value: Any = None
    retrieved_at: str


class ScoreBreakdown(BaseModel):
    demand: float = Field(ge=0, le=100)
    competition: float = Field(ge=0, le=100)
    profitability: float = Field(ge=0, le=100)
    trend: float = Field(ge=0, le=100)
    differentiation: float = Field(ge=0, le=100)
    supply: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)
    overall: float = Field(ge=0, le=100)
    rationale: dict[str, str] = Field(default_factory=dict)


class Candidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    asin: str = ""
    title: str
    category: str = ""
    price_usd: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    monthly_search_volume: float | None = Field(default=None, ge=0)
    monthly_sales: float | None = Field(default=None, ge=0)
    review_count: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    trend_pct: float | None = None
    top3_share_pct: float | None = Field(default=None, ge=0, le=100)
    supplier_count: int | None = Field(default=None, ge=0)
    moq: int | None = Field(default=None, ge=0)
    estimated_margin_pct: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    score: ScoreBreakdown | None = None


class ResearchResult(BaseModel):
    decision: Decision | None = None
    executive_summary: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    constraints: ResearchConstraints = Field(default_factory=ResearchConstraints)
    report_markdown: str = ""


class ResearchRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "新建选品研究"
    source_text: str
    mode: ResearchMode
    marketplace: str = "US"
    status: RunStatus = RunStatus.QUEUED
    result: ResearchResult | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    replies: list[str] = Field(default_factory=list)
    error: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()
