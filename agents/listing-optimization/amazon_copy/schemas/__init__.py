"""Pydantic domain schemas for the amazon_copy multi-agent system.

Encodes SOP length rules R1, R4, R7, R8, R11 at the type boundary.
Imports here do NOT pull agent, LLM, or prompt dependencies.
"""

from __future__ import annotations

from amazon_copy.schemas.agents import (
    AgentSummary,
    Ballot,
    CandidateArtifact,
    CritiqueArtifact,
    CritiqueFinding,
    GateFinding,
    GateResult,
    IntegrationTrace,
    LaneResult,
    RankingResult,
    RevisionArtifact,
    SCORE_DIMS,
    WriterLane,
)
from amazon_copy.schemas.enums import (
    SCORE_DIMENSIONS,
    SCORE_LABELS_ZH,
    PipelineMode,
    PipelineStage,
    ScoreDimKey,
    TitleMode,
)
from amazon_copy.schemas.input_research import (
    AudienceProfile,
    CompetitorAnalysis,
    FeedbackPack,
    MotiveItem,
    ProductInput,
    ResearchPack,
    SellingPoint,
)
from amazon_copy.schemas.listing import BulletPoint, ListingDraft, TitleCandidate
from amazon_copy.schemas.simple_listing import ListingFormatTemplate
from amazon_copy.schemas.metrics import (
    BpMode,
    parse_csv_terms,
    plain_len,
    strip_md_bold,
    validate_bullet_length,
    validate_bullets,
    validate_no_trailing_period,
    validate_title_length,
)
from amazon_copy.schemas.scoring import (
    EmbedRow,
    FinalPackage,
    PipelineState,
    Scorecard,
    ScoreDimension,
    SelectionTrace,
    SEOCheck,
)
from amazon_copy.schemas.simple_listing import (
    OptimizedListingCopy,
    SourceListingCopy,
)

__all__ = [
    "AgentSummary",
    "Ballot",
    "CandidateArtifact",
    "CritiqueArtifact",
    "CritiqueFinding",
    "GateFinding",
    "GateResult",
    "IntegrationTrace",
    "LaneResult",
    "RankingResult",
    "RevisionArtifact",
    "SCORE_DIMS",
    "SCORE_DIMENSIONS",
    "SCORE_LABELS_ZH",
    "AudienceProfile",
    "BpMode",
    "BulletPoint",
    "CompetitorAnalysis",
    "EmbedRow",
    "FeedbackPack",
    "FinalPackage",
    "ListingDraft",
    "ListingFormatTemplate",
    "MotiveItem",
    "OptimizedListingCopy",
    "PipelineMode",
    "PipelineStage",
    "PipelineState",
    "ProductInput",
    "ResearchPack",
    "SEOCheck",
    "ScoreDimKey",
    "ScoreDimension",
    "Scorecard",
    "SelectionTrace",
    "SellingPoint",
    "SourceListingCopy",
    "TitleCandidate",
    "TitleMode",
    "parse_csv_terms",
    "plain_len",
    "strip_md_bold",
    "validate_bullet_length",
    "validate_bullets",
    "validate_no_trailing_period",
    "validate_title_length",
]
