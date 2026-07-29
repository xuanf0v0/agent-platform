"""Typed inputs, cache, and terminal results for automatic optimization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Callable
from typing import Annotated, ClassVar, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from amazon_copy.config import Settings
from amazon_copy.llm import LLMClient
from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.mcp.live_research_types import ResearchBundle
from amazon_copy.review.diagnosis_models import ListingDiagnosisReport
from amazon_copy.review.models import (
    ClarificationQuestion,
    FactClaim,
    ListingReviewReport,
    MarketplaceRules,
)
from amazon_copy.schemas import OptimizedListingCopy
from amazon_copy.specialized_rules.guidance import SpecializedRuleGuidance
from amazon_copy.specialized_rules.models import (
    SpecializedRuleCache,
    SpecializedRuleLoad,
)
from amazon_copy.specialized_rules.resource_loader import SpecializedRuleRequest

_CLARIFICATION_ERROR_CODE = "clarification_value_missing"
_CLARIFICATION_ERROR_MESSAGE = "confirmed clarification requires a source description"
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
_FUNNEL_DISCLAIMER_ZH = (
    "无 CTR/CVR 实绩数据时仅为文案侧假设，不能定位真实漏斗根因。"
)

RunMode = Literal["diagnose", "optimize"]
FunnelStage = Literal["exposure", "ctr", "cvr", "cart_to_purchase"]
FunnelConfidence = Literal["low", "medium"]
FunnelBasis = Literal["copy_only", "keyword_context", "review_finding"]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ResearchFetcher(Protocol):
    """Synchronous live-research dependency used by the automatic service."""

    def __call__(self, settings: Settings, *, query: str) -> list[McpToolSnapshot]:
        """Fetch one redacted snapshot per configured provider."""
        ...


class SpecializedRuleFetcher(Protocol):
    """Synchronous specialized-rule dependency used by the automatic service."""

    def __call__(
        self,
        settings: Settings,
        *,
        request: SpecializedRuleRequest,
        cached: SpecializedRuleCache | None = None,
    ) -> SpecializedRuleLoad:
        """Load or reuse one source-bound exact profile route."""
        ...


class RuleGap(BaseModel):
    """One explicit absence in the authoritative marketplace rule context."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: Literal[
        "authoritative_rules_missing",
        "marketplace_unresolved",
        "product_type_unresolved",
    ]
    marketplace: str
    product_type: str


class RuleContext(BaseModel):
    """Resolved marketplace, inferred product type, limits, and rule gaps."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: str
    product_type: str
    rules: MarketplaceRules
    authoritative: bool
    gaps: tuple[RuleGap, ...] = ()


class EvidenceBundle(BaseModel):
    """User evidence plus allowable third-party keyword research."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    user_claims: tuple[FactClaim, ...] = ()
    suppressed_claim_terms: tuple[str, ...] = ()
    research: ResearchBundle = Field(default_factory=ResearchBundle)
    allowed_keywords: tuple[str, ...] = ()


class AutomaticResearchCache(BaseModel):
    """Source-bound successful and failed provider snapshots for resume."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    source_fingerprint: str
    query: str
    snapshots: tuple[McpToolSnapshot, ...] = ()
    bundle: ResearchBundle = Field(default_factory=ResearchBundle)


class ClarificationAnswer(BaseModel):
    """Seller confirmation or removal decision for one located question."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    question_code: str
    action: Literal["confirm", "remove"]
    value: str = ""

    @model_validator(mode="after")
    def require_confirmed_value(self) -> ClarificationAnswer:
        """Require a source description when confirming a core fact."""
        if self.action == "confirm" and not self.value.strip():
            raise PydanticCustomError(
                _CLARIFICATION_ERROR_CODE,
                _CLARIFICATION_ERROR_MESSAGE,
            )
        return self


class ProductIdentity(BaseModel):
    """Optional seller-supplied product identity for display only.

    ASIN is never guessed from title/brand/history. Absence is valid: paste-only
    flows remain fully supported. No PDP retrieval or parent/child graph in v1.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    asin: str | None = None
    marketplace: str | None = None
    product_type: str | None = None
    label: str | None = None

    @field_validator("asin", mode="before")
    @classmethod
    def normalize_asin(cls, value: object) -> str | None:
        """Uppercase and validate optional ASIN; blank becomes None."""
        if value is None:
            return None
        raw = str(value).strip().upper()
        if not raw:
            return None
        if not _ASIN_RE.fullmatch(raw):
            raise PydanticCustomError(
                "invalid_asin",
                "ASIN must be exactly 10 alphanumeric characters",
            )
        return raw


class FunnelHypothesis(BaseModel):
    """Copy-side funnel assumption; never a measured root-cause claim."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    stage: FunnelStage
    confidence: FunnelConfidence
    basis: FunnelBasis
    note_zh: NonBlank
    disclaimer_zh: NonBlank = _FUNNEL_DISCLAIMER_ZH


class AutomaticOptimizationContext(BaseModel):
    """Optional rules, evidence, answers, control-plane mode, and caches."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: str | None = None
    product_type: str | None = None
    rules: MarketplaceRules | None = None
    rule_context: RuleContext | None = None
    user_claims: tuple[FactClaim, ...] = ()
    suppressed_claim_terms: tuple[str, ...] = ()
    allowed_keywords: tuple[str, ...] = ()
    clarification_answers: tuple[ClarificationAnswer, ...] = ()
    clarification_reply: str | None = None
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
    cached_research: AutomaticResearchCache | None = None
    cached_specialized_rules: SpecializedRuleCache | None = None
    auto_resolve_unverified: bool = False
    # Control plane: default Stage1 diagnose; skip_approval restores one-shot optimize.
    mode: RunMode = "diagnose"
    skip_approval: bool = False
    approval_token: str | None = None
    identity: ProductIdentity | None = None


@dataclass(frozen=True, slots=True)
class AutomaticOptimizationDependencies:
    """Injected infrastructure for deterministic tests and production adapters."""

    settings: Settings | None = None
    llm: LLMClient | None = None
    research_fetcher: ResearchFetcher | None = None
    specialized_rule_fetcher: SpecializedRuleFetcher | None = None
    progress_callback: Callable[[str, int, int], None] | None = None
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None


class CompletedOptimization(BaseModel):
    """Paste-ready result that passed strict postflight review."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed"] = "completed"
    listing: OptimizedListingCopy
    rendered_text: str
    source_review: ListingReviewReport
    postflight_review: ListingReviewReport
    rule_context: RuleContext
    evidence_bundle: EvidenceBundle
    research_cache: AutomaticResearchCache
    cache_reused: bool
    specialized_rule_cache: SpecializedRuleCache | None = None
    specialized_cache_reused: bool = False
    specialized_rule_guidance: tuple[SpecializedRuleGuidance, ...] = ()
    diagnosis_report: ListingDiagnosisReport | None = None
    identity: ProductIdentity | None = None
    funnel_hypotheses: tuple[FunnelHypothesis, ...] = ()


class AwaitingApproval(BaseModel):
    """Stage1 diagnosis complete; generation waits for seller approval.

    No listing / rendered_text — postflight copy is only exposed after Stage2.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["awaiting_approval"] = "awaiting_approval"
    approval_token: NonBlank
    source_fingerprint: NonBlank
    identity: ProductIdentity | None = None
    source_review: ListingReviewReport
    diagnosis_report: ListingDiagnosisReport
    funnel_hypotheses: tuple[FunnelHypothesis, ...] = ()
    rule_context: RuleContext
    evidence_bundle: EvidenceBundle
    research_cache: AutomaticResearchCache
    cache_reused: bool
    specialized_rule_cache: SpecializedRuleCache | None = None
    specialized_cache_reused: bool = False
    specialized_rule_guidance: tuple[SpecializedRuleGuidance, ...] = ()


class NeedsClarification(BaseModel):
    """Paused result with targeted questions and reusable successful research."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["needs_clarification"] = "needs_clarification"
    questions: tuple[ClarificationQuestion, ...]
    source_review: ListingReviewReport
    rule_context: RuleContext
    evidence_bundle: EvidenceBundle
    research_cache: AutomaticResearchCache
    cache_reused: bool
    postflight_review: ListingReviewReport | None = None
    specialized_rule_cache: SpecializedRuleCache | None = None
    specialized_cache_reused: bool = False
    specialized_rule_guidance: tuple[SpecializedRuleGuidance, ...] = ()
    diagnosis_report: ListingDiagnosisReport | None = None
    identity: ProductIdentity | None = None
    funnel_hypotheses: tuple[FunnelHypothesis, ...] = ()


class FailedOptimization(BaseModel):
    """Safe terminal failure with no publishable listing payload."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["failed"] = "failed"
    code: Literal[
        "invalid_source",
        "optimization_failed",
        "postflight_blocked",
        "stale_approval",
    ]
    message: str
    source_review: ListingReviewReport | None = None
    postflight_review: ListingReviewReport | None = None
    rule_context: RuleContext | None = None
    evidence_bundle: EvidenceBundle | None = None
    research_cache: AutomaticResearchCache | None = None
    cache_reused: bool = False
    specialized_rule_cache: SpecializedRuleCache | None = None
    specialized_cache_reused: bool = False
    specialized_rule_guidance: tuple[SpecializedRuleGuidance, ...] = ()
    diagnosis_report: ListingDiagnosisReport | None = None
    identity: ProductIdentity | None = None
    funnel_hypotheses: tuple[FunnelHypothesis, ...] = ()
    last_candidate: OptimizedListingCopy | None = None
    last_candidate_text: str = ""
    quality_failures: tuple[str, ...] = ()


AutomaticOptimizationResult = (
    CompletedOptimization | AwaitingApproval | NeedsClarification | FailedOptimization
)


__all__ = [
    "AutomaticOptimizationContext",
    "AutomaticOptimizationDependencies",
    "AutomaticOptimizationResult",
    "AutomaticResearchCache",
    "AwaitingApproval",
    "ClarificationAnswer",
    "CompletedOptimization",
    "EvidenceBundle",
    "FailedOptimization",
    "FunnelBasis",
    "FunnelConfidence",
    "FunnelHypothesis",
    "FunnelStage",
    "NeedsClarification",
    "ProductIdentity",
    "ResearchFetcher",
    "RuleContext",
    "RuleGap",
    "RunMode",
    "SpecializedRuleCache",
    "SpecializedRuleFetcher",
]
