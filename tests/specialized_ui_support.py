from __future__ import annotations

from pathlib import Path
from typing import Literal

from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticResearchCache,
    AwaitingApproval,
    CompletedOptimization,
    EvidenceBundle,
    FunnelHypothesis,
    NeedsClarification,
    ProductIdentity,
    RuleContext,
    RuleGap,
)
from amazon_copy.review.diagnosis_models import (
    BackendTermsDiagnosis,
    EditorialScore,
    FieldCheckRow,
    ListingDiagnosisReport,
)
from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.mcp.live_research_types import ResearchBundle, ResearchGap
from amazon_copy.review.models import (
    ClarificationQuestion,
    KeywordCoverage,
    ListingReviewReport,
    MarketplaceRules,
    ReviewScore,
)
from amazon_copy.schemas import OptimizedListingCopy

APP_PATH = Path(__file__).parents[1] / "amazon_copy" / "ui" / "app.py"
SOURCE = "标题：Painting River Rocks\n五点\n· Smooth natural stones\n· Useful craft surfaces"
SOURCE_CHANGED = SOURCE.replace("Painting", "Decorative")
REMOVE_OPTION = "无法提供，删除该宣称"
DIMENSIONS = (
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
)


def report(
    *,
    status: Literal["PASS", "WARN", "BLOCK"] = "PASS",
    can_optimize: bool = True,
    disposition: Literal["auto_repair", "ask_user", "terminal"] = "auto_repair",
    questions: tuple[ClarificationQuestion, ...] = (),
) -> ListingReviewReport:
    return ListingReviewReport(
        status=status,
        can_optimize=can_optimize and not questions,
        findings=(),
        resolved_facts=(),
        keyword_coverage=(KeywordCoverage(field="title", covered=("rocks",), missing=()),),
        keyword_basis="third_party_data",
        scores=tuple(
            ReviewScore(dimension=dimension, score=8, rationale_zh="source basis")
            for dimension in DIMENSIONS
        ),
        disposition=disposition,
        clarification_questions=questions,
    )


def research_cache(*, unavailable: bool = False) -> AutomaticResearchCache:
    snapshot = McpToolSnapshot(
        provider="sellersprite",
        status="error" if unavailable else "ok",
        tool_count=0 if unavailable else 1,
        tools_sample=[] if unavailable else ["keyword_miner"],
        error="provider unavailable" if unavailable else None,
        research_gaps=(
            (ResearchGap(code="provider_error", provider="sellersprite"),) if unavailable else ()
        ),
    )
    return AutomaticResearchCache(
        source_fingerprint=source_fingerprint(SOURCE),
        query="painting river rocks",
        snapshots=(snapshot,),
        bundle=ResearchBundle(
            allowed_keywords=() if unavailable else ("painting rocks",),
            gaps=()
            if unavailable
            else (ResearchGap(code="schema_missing", provider="sellersprite"),),
        ),
    )


def rule_context() -> RuleContext:
    rules = MarketplaceRules(marketplace="US", product_type="ART_CRAFT_MATERIAL")
    return RuleContext(
        marketplace="US",
        product_type="ART_CRAFT_MATERIAL",
        rules=rules,
        authoritative=False,
        gaps=(
            RuleGap(
                code="authoritative_rules_missing",
                marketplace="US",
                product_type="ART_CRAFT_MATERIAL",
            ),
        ),
    )


def completed(*, unavailable: bool = False) -> CompletedOptimization:
    listing = OptimizedListingCopy(
        title="Painting River Rocks for Crafts",
        item_highlights="Smooth natural stones for creative projects",
        bullets=["Prepared surfaces", "Natural variation"],
        backend_search_terms="painting rocks crafts",
    )
    return CompletedOptimization(
        listing=listing,
        rendered_text=(
            "标题：Painting River Rocks for Crafts\n"
            "Item Highlights：Smooth natural stones for creative projects\n"
            "五点\n· Prepared surfaces\n· Natural variation\n"
            "Backend Search Terms：painting rocks crafts"
        ),
        source_review=report(),
        postflight_review=report(),
        rule_context=rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=research_cache(unavailable=unavailable),
        cache_reused=False,
    )


def paused(*questions: ClarificationQuestion) -> NeedsClarification:
    question_tuple = tuple(questions)
    return NeedsClarification(
        questions=question_tuple,
        source_review=report(disposition="ask_user", questions=question_tuple),
        rule_context=rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=research_cache(),
        cache_reused=False,
    )


def diagnosis_report() -> ListingDiagnosisReport:
    scores = tuple(
        EditorialScore(
            dimension=dimension,  # type: ignore[arg-type]
            label_zh=dimension,
            score=7.0,
            rationale_zh="ok",
        )
        for dimension in DIMENSIONS
    )
    return ListingDiagnosisReport(
        field_checks=(
            FieldCheckRow(
                field="Title",
                metric="长度",
                status="PASS",
                note_zh="ok",
            ),
        ),
        issues=(),
        backend=BackendTermsDiagnosis(
            terms="",
            bytes_used=0,
            max_bytes=250,
            token_count=0,
            duplication_pct=0.0,
            uncovered_candidates=(),
            summary_zh="ok",
        ),
        scores=scores,
        average_score=7.0,
    )


def awaiting_approval(
    *,
    token: str = "a" * 64,
    identity: ProductIdentity | None = None,
) -> AwaitingApproval:
    return AwaitingApproval(
        approval_token=token,
        source_fingerprint=source_fingerprint(SOURCE),
        identity=identity,
        source_review=report(),
        diagnosis_report=diagnosis_report(),
        funnel_hypotheses=(
            FunnelHypothesis(
                stage="ctr",
                confidence="low",
                basis="copy_only",
                note_zh="标题前段偏弱（假设）",
            ),
        ),
        rule_context=rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=research_cache(),
        cache_reused=False,
    )


__all__ = [
    "APP_PATH",
    "DIMENSIONS",
    "REMOVE_OPTION",
    "SOURCE",
    "SOURCE_CHANGED",
    "awaiting_approval",
    "completed",
    "diagnosis_report",
    "paused",
    "report",
    "research_cache",
    "rule_context",
]
