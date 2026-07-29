"""Typed multi-agent artifacts for the studio pipeline."""
from __future__ import annotations
from enum import StrEnum
from typing import Final
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCORE_DIMS: Final[tuple[str, ...]] = (
    "compliance", "seo", "grammar", "readability", "selling_points",
    "localization", "professionalism", "emotion", "cta",
)

class WriterLane(StrEnum):
    SEO = "seo"
    DIFFERENTIATION = "differentiation"
    CLARITY = "clarity"

class CandidateArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str = Field(min_length=1)
    lane: WriterLane
    titles: list[str] = Field(min_length=3, max_length=3)
    bullets: list[str] = Field(min_length=5, max_length=5)
    claim_ids: list[str] = Field(default_factory=list)

class GateFinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: str
    message: str
    passed: bool

class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    findings: list[GateFinding]
    eligible: bool

    @model_validator(mode="after")
    def _eligible_requires_pass(self) -> GateResult:
        hard_fails = [f for f in self.findings if f.severity == "error" and not f.passed]
        if hard_fails and self.eligible:
            raise ValueError("eligible cannot be True when hard gate findings failed")
        return self


class CritiqueFinding(BaseModel):
    """A single critique finding from a reviewer agent."""
    model_config = ConfigDict(frozen=True)
    category: str
    finding: str
    recommendation: str


class CritiqueArtifact(BaseModel):
    """Collection of critique findings targeting a single candidate."""
    model_config = ConfigDict(frozen=True)
    target_candidate_id: str
    findings: list[CritiqueFinding]


class RevisionArtifact(BaseModel):
    """A revised candidate derived from a parent candidate."""
    model_config = ConfigDict(frozen=True)
    parent_candidate_id: str = Field(min_length=1)
    candidate: CandidateArtifact


class Ballot(BaseModel):
    """A judge's scored ballot ranking multiple candidates."""
    judge_alias: str
    scores: dict[str, float]
    ranked_aliases: list[str]

    @model_validator(mode="after")
    def _validate_scores(self) -> Ballot:
        expected = set(SCORE_DIMS)
        actual = set(self.scores.keys())
        if actual != expected:
            raise ValueError(
                f"scores keys must match {expected}, got {actual}"
            )
        for k, v in self.scores.items():
            if not (0 <= v <= 10):
                raise ValueError(
                    f"score for {k} must be between 0 and 10, got {v}"
                )
        return self


class RankingResult(BaseModel):
    """Aggregated ranking across judges."""
    ordered_candidate_ids: list[str]
    scores: dict[str, float]
    tie_break_notes: str = ""


class IntegrationTrace(BaseModel):
    """Trace metadata for the integration step."""
    winner_id: str
    used_claim_ids: list[str]
    fallback_used: bool = False


class AgentSummary(BaseModel):
    """Redacted execution summary for an agent lane."""
    agent_role: str
    status: str
    redacted_notes: str = ""


class LaneResult(BaseModel):
    """Outcome of a single writer lane."""
    lane: WriterLane
    candidate: CandidateArtifact | None = None
    error: str | None = None
