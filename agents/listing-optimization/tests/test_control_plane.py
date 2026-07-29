"""Control-plane Stage1/Stage2, funnel hypotheses, and optional ASIN identity."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock

import amazon_copy.simple_optimizer as optimizer
import pytest
from amazon_copy.automatic_funnel import build_funnel_hypotheses
from amazon_copy.automatic_models import (
    AwaitingApproval,
    CompletedOptimization,
    FailedOptimization,
    ProductIdentity,
)
from amazon_copy.automatic_pipeline import (
    _build_quality_feedback,
    _editorial_gate_passed,
    issue_approval_token,
)
from amazon_copy.config import Settings
from amazon_copy.mcp.live_research import McpToolSnapshot, normalize_tool_payload
from amazon_copy.review.diagnosis_models import (
    BackendTermsDiagnosis,
    EditorialScore,
    FieldCheckRow,
    ListingDiagnosisReport,
    PriorityIssue,
)
from amazon_copy.review.models import (
    KeywordCoverage,
    ListingReviewReport,
    ReviewFinding,
    ReviewScore,
)

if TYPE_CHECKING:
    pass

SAFE_SOURCE = """Title: Natural River Rocks for Painting
- Smooth natural stones provide prepared painting surfaces
- Natural shape color and texture vary from stone to stone
- Finished projects can become garden markers or desk decorations"""


class _ListingLLM:
    def __init__(self) -> None:
        self.call_count = 0
        self.payloads: list[dict[str, object]] = []

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        self.call_count += 1
        payload = json.loads(user)
        if "seller_reply" in payload:
            return '{"answers":[]}'
        if "allowed_product_types" in payload or "product_type_options" in payload:
            return json.dumps(
                {
                    "product_type": "GENERAL_PRODUCT",
                    "confidence": 0.9,
                    "rationale": "generic craft stones",
                }
            )
        self.payloads.append(payload)
        source = payload["source_listing"]
        count = int(payload["target_bullet_count"])
        return json.dumps(
            {
                "title": str(source["title"]),
                "item_highlights": "Source-based product details for marketplace shoppers.",
                "bullets": [
                    f"DETAIL {index}: Product information from the source"
                    for index in range(1, count + 1)
                ],
                "backend_search_terms": "river rocks painting stones craft",
            }
        )


class _ResearchFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, settings: Settings, *, query: str) -> list[McpToolSnapshot]:
        del settings, query
        self.calls += 1
        return [
            normalize_tool_payload(
                provider="sellersprite",
                status="ok",
                tool_count=0,
                tools_sample=(),
                raw={},
            )
        ]


def _dependencies(llm: _ListingLLM, research: _ResearchFetcher) -> optimizer.AutomaticOptimizationDependencies:
    return optimizer.AutomaticOptimizationDependencies(
        settings=Settings(mock=True),
        llm=llm,
        research_fetcher=research,
    )


def _dummy_scores() -> tuple[ReviewScore, ...]:
    dims = (
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
    return tuple(
        ReviewScore(dimension=dim, score=7.0, rationale_zh="ok")  # type: ignore[arg-type]
        for dim in dims
    )


def _dummy_editorial_scores() -> tuple[EditorialScore, ...]:
    dims = (
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
    return tuple(
        EditorialScore(
            dimension=dim,  # type: ignore[arg-type]
            label_zh=dim,
            score=6.0 if dim != "purchase_motivation" else 4.0,
            rationale_zh="note",
        )
        for dim in dims
    )


def test_product_identity_rejects_invalid_asin() -> None:
    with pytest.raises(Exception):
        ProductIdentity(asin="not-an-asin")
    assert ProductIdentity(asin="b012345678").asin == "B012345678"
    assert ProductIdentity(asin="").asin is None


def test_default_mode_pauses_at_awaiting_approval() -> None:
    llm = _ListingLLM()
    research = _ResearchFetcher()
    result = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(
            marketplace="US",
            identity=ProductIdentity(asin="B0TESTASIN"),
        ),
        dependencies=_dependencies(llm, research),
    )
    assert isinstance(result, AwaitingApproval)
    assert result.approval_token
    assert result.source_fingerprint
    assert result.diagnosis_report is not None
    assert result.identity is not None
    assert result.identity.asin == "B0TESTASIN"
    # Stage1 must not call listing optimizer (product-type classifier may still call LLM).
    assert not any("target_bullet_count" in p for p in llm.payloads)
    assert research.calls == 1


def test_pipeline_reports_real_stage_progress() -> None:
    llm = _ListingLLM()
    research = _ResearchFetcher()
    updates: list[tuple[str, int, int]] = []
    dependencies = optimizer.AutomaticOptimizationDependencies(
        settings=Settings(mock=True),
        llm=llm,
        research_fetcher=research,
        progress_callback=lambda label, step, total: updates.append((label, step, total)),
    )

    result = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(marketplace="US"),
        dependencies=dependencies,
    )

    assert isinstance(result, AwaitingApproval)
    assert [step for _, step, _ in updates] == [1, 2, 3, 4, 5]
    assert updates[-1] == ("Stage 1 综合诊断", 5, 9)


def test_skip_approval_one_shot_completes() -> None:
    llm = _ListingLLM()
    research = _ResearchFetcher()
    result = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(
            marketplace="US",
            skip_approval=True,
        ),
        dependencies=_dependencies(llm, research),
    )
    assert isinstance(result, CompletedOptimization)
    assert result.rendered_text
    assert any("target_bullet_count" in p for p in llm.payloads)


def test_stage2_with_valid_token_completes() -> None:
    llm = _ListingLLM()
    research = _ResearchFetcher()
    deps = _dependencies(llm, research)
    stage1 = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(marketplace="US"),
        dependencies=deps,
    )
    assert isinstance(stage1, AwaitingApproval)
    stage2 = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(
            marketplace="US",
            mode="optimize",
            approval_token=stage1.approval_token,
            cached_research=stage1.research_cache,
            cached_specialized_rules=stage1.specialized_rule_cache,
            rule_context=stage1.rule_context,
        ),
        dependencies=deps,
    )
    assert isinstance(stage2, CompletedOptimization)
    # Research cache reused — no second fetch when fingerprint matches.
    assert research.calls == 1


def test_stage2_stale_token_fails() -> None:
    llm = _ListingLLM()
    research = _ResearchFetcher()
    deps = _dependencies(llm, research)
    stage1 = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(marketplace="US"),
        dependencies=deps,
    )
    assert isinstance(stage1, AwaitingApproval)
    failed = optimizer.run_automatic_optimization(
        SAFE_SOURCE,
        context=optimizer.AutomaticOptimizationContext(
            marketplace="US",
            mode="optimize",
            approval_token="deadbeef" * 8,
            cached_research=stage1.research_cache,
            rule_context=stage1.rule_context,
        ),
        dependencies=deps,
    )
    assert isinstance(failed, FailedOptimization)
    assert failed.code == "stale_approval"


def test_funnel_hypotheses_from_short_title_and_gaps() -> None:
    report = ListingReviewReport(
        status="WARN",
        can_optimize=True,
        findings=(
            ReviewFinding(
                code="MISSING_REQUIRED_FACT",
                severity="WARN",
                field="bullets",
                message_zh="规格事实待确认",
                fact_key="size",
            ),
        ),
        resolved_facts=(),
        keyword_coverage=(
            KeywordCoverage(field="title", covered=(), missing=("painting rocks",)),
        ),
        keyword_basis="text_relevance_only",
        scores=_dummy_scores(),
    )
    diagnosis = ListingDiagnosisReport(
        field_checks=(
            FieldCheckRow(
                field="Title",
                metric="长度",
                status="WARN",
                note_zh="偏短",
            ),
        ),
        issues=(
            PriorityIssue(level="P0", title="标题过短", detail_zh="需要补身份词"),
        ),
        backend=BackendTermsDiagnosis(
            terms="",
            bytes_used=10,
            max_bytes=250,
            token_count=2,
            duplication_pct=50.0,
            uncovered_candidates=("garden stones",),
            summary_zh="backend weak",
        ),
        scores=_dummy_editorial_scores(),
        average_score=6.0,
    )
    hyps = build_funnel_hypotheses(report, diagnosis, title="Rocks")
    stages = {h.stage for h in hyps}
    assert "ctr" in stages
    assert "cvr" in stages or "exposure" in stages
    assert all(h.confidence in {"low", "medium"} for h in hyps)
    assert all("不能定位真实漏斗根因" in h.disclaimer_zh for h in hyps)


def test_language_gate_does_not_loop_on_unrelated_p0_issue() -> None:
    diagnosis = ListingDiagnosisReport(
        field_checks=(
            FieldCheckRow(field="Title", metric="SEO", status="WARN", note_zh="偏短"),
        ),
        issues=(
            PriorityIssue(level="P0", title="SEO 标题偏短", detail_zh="补充搜索词"),
        ),
        backend=BackendTermsDiagnosis(
            terms="river rocks painting",
            bytes_used=20,
            max_bytes=250,
            token_count=3,
            duplication_pct=0,
            summary_zh="正常",
        ),
        scores=_dummy_editorial_scores(),
        average_score=6.0,
        fix_order=("补充搜索词",),
    )

    assert _editorial_gate_passed(diagnosis)
    feedback = _build_quality_feedback(diagnosis)
    assert "SEO 标题偏短" not in feedback
    assert "补充搜索词" not in feedback


def test_issue_approval_token_stable_for_same_review() -> None:
    report = ListingReviewReport(
        status="PASS",
        can_optimize=True,
        findings=(),
        resolved_facts=(),
        keyword_coverage=(),
        keyword_basis="text_relevance_only",
        scores=_dummy_scores(),
        disposition="auto_repair",
    )
    a = issue_approval_token(source_fingerprint_value="abc", source_report=report)
    b = issue_approval_token(source_fingerprint_value="abc", source_report=report)
    assert a == b
    c = issue_approval_token(source_fingerprint_value="xyz", source_report=report)
    assert a != c
