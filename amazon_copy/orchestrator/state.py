"""Typed studio pipeline state — frozen snapshot of one run.

``StudioState`` is the single carrier object through all six pipeline stages.
Every field is immutable (``frozen=True`` / ``@dataclass(frozen=True)``) so
stages never mutate in-place; the pipeline produces a new state per step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast

from amazon_copy.schemas import (
    BulletPoint,
    FinalPackage,
    ListingDraft,
    PipelineStage,
    ProductInput,
    TitleCandidate,
)


@dataclass(frozen=True)
class StudioState:
    """Immutable snapshot of one studio pipeline execution.

    Attributes:
        request_text: The raw user request that started this run.
        run_id: Opaque workflow identifier (UUID) for this run.
        research: The ``ResearchBundle`` from MCP research lanes, or ``None``.
        candidates: Raw candidates from the writer stage.
        revised: Candidates after the critique-and-revise ring.
        eligible: Candidates that passed hard-gate filtering.
        ranking: ``RankingResult`` from the dual-judge stage, or ``None``.
        winner: The elected ``CandidateArtifact``, or ``None``.
        trace: ``IntegrationTrace`` from the integrator stage, or ``None``.
        outcome: Overall run outcome.
        errors: Accumulated error messages from any stage.
        llm_calls: Total LLM calls made during this run.
        mcp_calls: Total MCP calls made during this run.
    """

    request_text: str
    run_id: str = ""
    research: object | None = None
    candidates: list = field(default_factory=list)
    revised: list = field(default_factory=list)
    eligible: list = field(default_factory=list)
    ranking: object | None = None
    winner: object | None = None
    trace: object | None = None
    outcome: Literal["success", "degraded", "no_winner", "failure"] = "failure"
    errors: list[str] = field(default_factory=list)
    llm_calls: int = 0
    mcp_calls: int = 0


def package_from_studio_state(
    state: StudioState,
    product_input: ProductInput | None = None,
) -> FinalPackage | None:
    """Map a successful StudioState into a FinalPackage for legacy export.

    Returns ``None`` when there is no winner (``state.outcome != "success"``).
    """
    if state.outcome != "success" or state.winner is None:
        return None

    winner = state.winner
    # Runtime winner is CandidateArtifact; StudioState may type it loosely.
    titles = [str(t) for t in cast("list[str]", getattr(winner, "titles", []) or [])]
    bullets_raw = [str(b) for b in cast("list[str]", getattr(winner, "bullets", []) or [])]
    title = titles[0] if titles else ""
    title_candidates = [TitleCandidate(text=t) for t in titles]
    bullets = [
        BulletPoint.model_validate({"text": b}, context={"skip_bp_length": True})
        for b in bullets_raw
    ]
    listing = ListingDraft.model_construct(
        title=title,
        title_candidates=title_candidates,
        bullets=bullets,
    )
    if product_input is None:
        product_input = ProductInput(
            product=state.request_text or "(from studio)",
            market="US",
            instruction="",
            rootwords=["placeholder"],
            keywords=["placeholder"],
        )
    return FinalPackage.model_construct(
        product_input=product_input,
        listing=listing,
        stage=PipelineStage.COMPLETED,
        stage_history=[PipelineStage.COMPLETED],
    )


__all__ = ["StudioState", "package_from_studio_state"]
