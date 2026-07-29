"""Automatic research, review, clarification, optimization, and postflight."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from amazon_copy.agents.english_listing_reviewer import (
    EnglishListingReview,
    EnglishListingReviewError,
    apply_english_review_suggestions,
    review_english_listing,
)
from amazon_copy.agents.listing_diagnosis import diagnose_listing
from amazon_copy.automatic_clarification import ClarificationRequest, resolve_clarifications
from amazon_copy.automatic_conservative import ConservativeRunRequest, run_conservatively
from amazon_copy.automatic_context import (
    build_evidence_bundle,
    postflight_review_request,
    resolve_rule_context,
    source_fingerprint,
    source_review_request,
)
from amazon_copy.automatic_failure import optimization_failure_message
from amazon_copy.automatic_funnel import build_funnel_hypotheses
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticOptimizationResult,
    AutomaticResearchCache,
    AwaitingApproval,
    CompletedOptimization,
    EvidenceBundle,
    FailedOptimization,
    FunnelHypothesis,
    NeedsClarification,
    ProductIdentity,
    RuleContext,
)
from amazon_copy.automatic_postflight import postflight_questions
from amazon_copy.automatic_research import (
    AutomaticResearchRequest,
    load_research_cache,
)
from amazon_copy.automatic_safe_rewrite import safely_rewrite_output, safely_rewrite_source
from amazon_copy.automatic_specialized import (
    SpecializedAutomaticState,
    SpecializedStateRequest,
    apply_specialized_route,
    resolve_specialized_state,
)
from amazon_copy.mcp.research_context import (
    build_diagnosis_summary,
    build_research_context,
    build_review_summary,
)
from amazon_copy.mcp.writing_mcp import (
    analyze_listing_writing,
    polish_listing_with_editor,
)
from amazon_copy.optimizer_runtime import SimpleOptimizerError, resolve_client
from amazon_copy.optimizer_service import OptimizerRequest, optimize_listing_request
from amazon_copy.review.diagnosis_models import ListingDiagnosisReport
from amazon_copy.review.models import (
    ClarificationQuestion,
    ListingReviewReport,
    ListingReviewRequest,
    ReviewFinding,
)
from amazon_copy.review.service import review_listing
from amazon_copy.schemas.simple_listing import (
    CopyPointsParseError,
    OptimizedListingCopy,
    SourceListingCopy,
    format_canonical_optimized_listing,
    parse_listing_block,
    split_verified_facts_from_listing,
)

_APPROVAL_SALT = "amazon-copy-approval-v1"
_GRAMMAR_SCORE_THRESHOLD = 6.0
_MAX_QUALITY_ATTEMPTS = 8
_EDITORIAL_DIMENSIONS = {"grammar", "readability", "localization"}


class _QualityGateExhausted(SimpleOptimizerError):
    """Carry the final non-publishable candidate out of the quality loop."""

    def __init__(
        self,
        message: str,
        *,
        candidate: OptimizedListingCopy,
        postflight: ListingReviewReport,
        failures: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.candidate = candidate
        self.postflight = postflight
        self.failures = failures


def _progress(
    dependencies: AutomaticOptimizationDependencies,
    label: str,
    step: int,
    total: int = 9,
) -> None:
    """Publish transient UI progress without coupling it to result models."""
    callback = dependencies.progress_callback
    if callback is not None:
        callback(label, step, total)


def _quality_failure_reasons(
    diagnosis: ListingDiagnosisReport,
    english_review: EnglishListingReview,
    postflight: ListingReviewReport,
) -> tuple[str, ...]:
    """Return language and blocking release-rule failures for this round."""
    del diagnosis
    english_reasons = tuple(
        f"{issue.location} [{issue.issue_type}]: "
        f"{issue.original} -> {issue.suggestion}"
        for issue in english_review.issues
    )
    rule_reasons = tuple(
        f"{finding.field} [rule:{finding.code}]: {finding.message_zh}"
        for finding in _blocking_findings(postflight)
    )
    return (*english_reasons, *rule_reasons)


def _blocking_findings(postflight: ListingReviewReport) -> tuple[ReviewFinding, ...]:
    """Return only rules that prevent release; WARN findings remain advisory."""
    return tuple(
        finding for finding in postflight.findings if finding.severity == "BLOCK"
    )


def _publish_quality_round(
    dependencies: AutomaticOptimizationDependencies,
    attempt: int,
    diagnosis: ListingDiagnosisReport,
    english_review: EnglishListingReview,
    postflight: ListingReviewReport,
) -> None:
    reasons = _quality_failure_reasons(diagnosis, english_review, postflight)
    callback = dependencies.quality_callback
    if callback is not None:
        callback(attempt, _MAX_QUALITY_ATTEMPTS, reasons, not reasons)


@dataclass(frozen=True, slots=True)
class _ClarificationState:
    report: ListingReviewReport
    questions: tuple[ClarificationQuestion, ...]
    rule_context: RuleContext
    evidence: EvidenceBundle
    cache: AutomaticResearchCache
    cache_reused: bool
    specialized: SpecializedAutomaticState
    diagnosis_report: ListingDiagnosisReport | None = None
    identity: ProductIdentity | None = None
    funnel_hypotheses: tuple[FunnelHypothesis, ...] = ()


@dataclass(frozen=True, slots=True)
class _PreparedDiagnosis:
    """Shared Stage1 state used by approval pause or Stage2 generation."""

    source: SourceListingCopy
    original_listing_text: str
    review_request: ListingReviewRequest
    source_report: ListingReviewReport
    rule_context: RuleContext
    evidence: EvidenceBundle
    cache: AutomaticResearchCache
    cache_reused: bool
    specialized: SpecializedAutomaticState
    diagnosis_report: ListingDiagnosisReport
    writing_analysis: dict[str, object]
    research_context: object
    identity: ProductIdentity | None
    funnel_hypotheses: tuple[FunnelHypothesis, ...]
    fingerprint: str


def _needs_clarification(state: _ClarificationState) -> NeedsClarification:
    return NeedsClarification(
        questions=state.questions,
        source_review=state.report,
        rule_context=state.rule_context,
        evidence_bundle=state.evidence,
        research_cache=state.cache,
        cache_reused=state.cache_reused,
        specialized_rule_cache=state.specialized.cache,
        specialized_cache_reused=state.specialized.cache_reused,
        specialized_rule_guidance=state.specialized.guidance,
        diagnosis_report=state.diagnosis_report,
        identity=state.identity,
        funnel_hypotheses=state.funnel_hypotheses,
    )


def _resolved_identity(
    context: AutomaticOptimizationContext,
    rule_context: RuleContext,
) -> ProductIdentity | None:
    """Merge optional seller identity with resolved marketplace/product type for display."""
    base = context.identity
    marketplace = (
        (base.marketplace if base is not None and base.marketplace else None)
        or context.marketplace
        or rule_context.marketplace
    )
    product_type = (
        (base.product_type if base is not None and base.product_type else None)
        or context.product_type
        or rule_context.product_type
    )
    asin = base.asin if base is not None else None
    label = base.label if base is not None else None
    if asin is None and marketplace is None and product_type is None and label is None:
        return None
    return ProductIdentity(
        asin=asin,
        marketplace=marketplace,
        product_type=product_type,
        label=label,
    )


def issue_approval_token(
    *,
    source_fingerprint_value: str,
    source_report: ListingReviewReport,
) -> str:
    """Bind Stage2 to source fingerprint + deterministic source-review codes.

    Avoids LLM diagnosis digests so Stage2 token validation stays stable.
    """
    finding_codes = ",".join(sorted({finding.code for finding in source_report.findings}))
    disposition = source_report.disposition
    material = (
        f"{source_fingerprint_value}|{finding_codes}|{disposition}|{_APPROVAL_SALT}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _review_safe_source(
    source: SourceListingCopy,
    request: ListingReviewRequest,
    evidence: EvidenceBundle,
) -> tuple[SourceListingCopy, ListingReviewRequest, ListingReviewReport]:
    report = review_listing(request)
    repaired = safely_rewrite_source(source, report, evidence)
    if repaired == source:
        return source, request, report
    repaired_request = request.model_copy(
        update={
            "title": repaired.title,
            "item_highlights": repaired.item_highlights,
            "bullets": tuple(repaired.bullets),
        }
    )
    return repaired, repaired_request, review_listing(repaired_request)


def run_automatic_optimization(
    source_text: str,
    context: AutomaticOptimizationContext | None = None,
    dependencies: AutomaticOptimizationDependencies | None = None,
) -> AutomaticOptimizationResult:
    """Run automatic live research through strict postflight suppression."""
    run_context = context or AutomaticOptimizationContext()
    run_dependencies = dependencies or AutomaticOptimizationDependencies()
    return run_conservatively(
        ConservativeRunRequest(
            source_text,
            run_context,
            run_dependencies,
            _run_automatic_optimization,
        )
    )


def _run_automatic_optimization(
    source_text: str,
    run_context: AutomaticOptimizationContext,
    run_dependencies: AutomaticOptimizationDependencies,
) -> AutomaticOptimizationResult:
    stage1 = _run_through_diagnosis(source_text, run_context, run_dependencies)
    if not isinstance(stage1, _PreparedDiagnosis):
        return stage1

    should_pause = run_context.mode == "diagnose" and not run_context.skip_approval
    if should_pause:
        token = issue_approval_token(
            source_fingerprint_value=stage1.fingerprint,
            source_report=stage1.source_report,
        )
        return AwaitingApproval(
            approval_token=token,
            source_fingerprint=stage1.fingerprint,
            identity=stage1.identity,
            source_review=stage1.source_report,
            diagnosis_report=stage1.diagnosis_report,
            funnel_hypotheses=stage1.funnel_hypotheses,
            rule_context=stage1.rule_context,
            evidence_bundle=stage1.evidence,
            research_cache=stage1.cache,
            cache_reused=stage1.cache_reused,
            specialized_rule_cache=stage1.specialized.cache,
            specialized_cache_reused=stage1.specialized.cache_reused,
            specialized_rule_guidance=stage1.specialized.guidance,
        )

    if run_context.mode == "optimize" and not run_context.skip_approval:
        expected = issue_approval_token(
            source_fingerprint_value=stage1.fingerprint,
            source_report=stage1.source_report,
        )
        provided = (run_context.approval_token or "").strip()
        if not provided or provided != expected:
            return FailedOptimization(
                code="stale_approval",
                message=(
                    "诊断审批已失效：请重新分析当前 Listing 后再生成上传稿。"
                ),
                source_review=stage1.source_report,
                rule_context=stage1.rule_context,
                evidence_bundle=stage1.evidence,
                research_cache=stage1.cache,
                cache_reused=stage1.cache_reused,
                specialized_rule_cache=stage1.specialized.cache,
                specialized_cache_reused=stage1.specialized.cache_reused,
                specialized_rule_guidance=stage1.specialized.guidance,
                diagnosis_report=stage1.diagnosis_report,
                identity=stage1.identity,
                funnel_hypotheses=stage1.funnel_hypotheses,
            )

    return _run_optimize_from_prepared(stage1, run_dependencies)


def _run_through_diagnosis(
    source_text: str,
    run_context: AutomaticOptimizationContext,
    run_dependencies: AutomaticOptimizationDependencies,
) -> _PreparedDiagnosis | FailedOptimization | NeedsClarification:
    _progress(run_dependencies, "解析 Listing", 1)
    listing_text, _ = split_verified_facts_from_listing(source_text)
    # Optimizer receives listing-only paste (verified-fact marker lines already stripped).
    original_listing_text = listing_text
    try:
        source = parse_listing_block(listing_text)
    except CopyPointsParseError:
        return FailedOptimization(code="invalid_source", message="Listing source is invalid.")
    fingerprint = source_fingerprint(source_text)
    _progress(run_dependencies, "市场研究与关键词", 2)
    cache, cache_reused = load_research_cache(
        AutomaticResearchRequest(
            source_text=source_text,
            source=source,
            context=run_context,
            dependencies=run_dependencies,
        )
    )
    _progress(run_dependencies, "产品路由与专项规则", 3)
    specialized = resolve_specialized_state(
        SpecializedStateRequest(
            source_text=source_text,
            source=source,
            context=run_context,
            dependencies=run_dependencies,
        )
    )
    rule_context = apply_specialized_route(
        resolve_rule_context(source, run_context),
        specialized,
    )
    _progress(run_dependencies, "事实证据与冲突检查", 4)
    evidence = build_evidence_bundle(run_context, cache.bundle)
    research_context = build_research_context(
        evidence.research,
        snapshots=cache.snapshots,
    )
    review_request = source_review_request(
        source,
        rule_context,
        evidence,
        specialized.requirements,
    )
    source, review_request, source_report = _review_safe_source(
        source,
        review_request,
        evidence,
    )
    writing_analysis = analyze_listing_writing(
        run_dependencies.settings,
        title=source.title,
        item_highlights=source.item_highlights,
        bullets=source.bullets,
    ).as_prompt_dict()
    _progress(run_dependencies, "Stage 1 综合诊断", 5)
    diagnosis_report = diagnose_listing(
        review_request,
        source_report,
        settings=run_dependencies.settings,
        research_context=research_context,
        writing_analysis=writing_analysis,
    )
    identity = _resolved_identity(run_context, rule_context)
    funnel_hypotheses = build_funnel_hypotheses(
        source_report,
        diagnosis_report,
        title=source.title,
    )
    pending_questions = specialized.questions
    if source_report.disposition == "ask_user":
        resolution = resolve_clarifications(
            ClarificationRequest(
                source=source,
                evidence=evidence,
                report=source_report,
                answers=run_context.clarification_answers,
            )
        )
        if resolution.unanswered_codes or specialized.questions:
            unanswered = frozenset(resolution.unanswered_codes)
            pending_questions = (
                *specialized.questions,
                *(
                    question
                    for question in source_report.clarification_questions
                    if question.code in unanswered
                ),
            )
            evidence = resolution.evidence
        source = resolution.source
        if not pending_questions:
            evidence = resolution.evidence
            review_request = source_review_request(source, rule_context, evidence)
            review_request = review_request.model_copy(
                update={"fact_requirements": specialized.requirements}
            )
            source_report = review_listing(review_request)
            writing_analysis = analyze_listing_writing(
                run_dependencies.settings,
                title=source.title,
                item_highlights=source.item_highlights,
                bullets=source.bullets,
            ).as_prompt_dict()
            diagnosis_report = diagnose_listing(
                review_request,
                source_report,
                settings=run_dependencies.settings,
                research_context=research_context,
                writing_analysis=writing_analysis,
            )
            funnel_hypotheses = build_funnel_hypotheses(
                source_report,
                diagnosis_report,
                title=source.title,
            )
            if source_report.disposition == "ask_user":
                pending_questions = source_report.clarification_questions
    if pending_questions:
        return _needs_clarification(
            _ClarificationState(
                report=source_report,
                questions=pending_questions,
                rule_context=rule_context,
                evidence=evidence,
                cache=cache,
                cache_reused=cache_reused,
                specialized=specialized,
                diagnosis_report=diagnosis_report,
                identity=identity,
                funnel_hypotheses=funnel_hypotheses,
            )
        )
    return _PreparedDiagnosis(
        source=source,
        original_listing_text=original_listing_text,
        review_request=review_request,
        source_report=source_report,
        rule_context=rule_context,
        evidence=evidence,
        cache=cache,
        cache_reused=cache_reused,
        specialized=specialized,
        diagnosis_report=diagnosis_report,
        writing_analysis=writing_analysis,
        research_context=research_context,
        identity=identity,
        funnel_hypotheses=funnel_hypotheses,
        fingerprint=fingerprint,
    )


def _build_quality_feedback(
    diagnosis: ListingDiagnosisReport,
    english_review: EnglishListingReview | None = None,
) -> str:
    """Turn output diagnosis issues into optimizer revision feedback."""
    parts = [
        "The prior output had quality issues. Revise to fix these:",
    ]
    # This loop owns language quality only. Compliance, evidence, SEO and
    # merchandising findings belong to their dedicated gates; injecting them
    # here made an otherwise-correct English candidate oscillate indefinitely.
    parts.extend(
        f"- {score.label_zh} scored {score.score}/10: {score.rationale_zh}"
        for score in diagnosis.scores
        if score.dimension in _EDITORIAL_DIMENSIONS
        and score.score < _GRAMMAR_SCORE_THRESHOLD
    )
    if english_review is not None and english_review.issues:
        parts.append(
            "Dedicated US English review table:\n"
            + english_review.as_markdown_table()
        )
    parts.append(
        "Return a JSON object with nonblank title and item_highlights plus "
        "exactly the requested number of nonblank bullets. Each bullet must "
        "start with a benefit-led label (3-7 words) followed by a colon and a "
        "complete sentence. Use only source facts."
    )
    return " ".join(parts)


def _grammar_score(diagnosis: ListingDiagnosisReport) -> float:
    """Return the grammar score, treating a missing dimension as passing."""
    return next(
        (score.score for score in diagnosis.scores if score.dimension == "grammar"),
        10.0,
    )


def _editorial_gate_passed(diagnosis: ListingDiagnosisReport) -> bool:
    required_dimensions = _EDITORIAL_DIMENSIONS
    scores = {
        score.dimension: score.score
        for score in diagnosis.scores
        if score.dimension in required_dimensions
    }
    return (
        all(
            scores.get(dimension, 10.0) >= _GRAMMAR_SCORE_THRESHOLD
            for dimension in required_dimensions
        )
    )


def _diagnose_generated_listing(
    listing: OptimizedListingCopy,
    postflight: ListingReviewReport,
    prepared: _PreparedDiagnosis,
    run_dependencies: AutomaticOptimizationDependencies,
) -> tuple[ListingDiagnosisReport, dict[str, object]]:
    """Run the editorial/grammar agent against one generated candidate."""
    output_writing = analyze_listing_writing(
        run_dependencies.settings,
        title=listing.title,
        item_highlights=listing.item_highlights,
        bullets=listing.bullets,
    ).as_prompt_dict()
    output_diagnosis = diagnose_listing(
        postflight_review_request(
            listing,
            prepared.rule_context,
            prepared.evidence,
            prepared.review_request,
        ),
        postflight,
        settings=run_dependencies.settings,
        research_context=prepared.research_context,
        writing_analysis=output_writing,
    )
    return output_diagnosis, output_writing


def _run_quality_gate(
    listing: OptimizedListingCopy,
    postflight: ListingReviewReport,
    prepared: _PreparedDiagnosis,
    run_dependencies: AutomaticOptimizationDependencies,
) -> tuple[OptimizedListingCopy, ListingReviewReport, ListingDiagnosisReport]:
    """Iterate language review and revision until all editorial gates pass."""
    _progress(run_dependencies, "语法、语义与结构诊断", 7)
    output_diagnosis, output_writing = _diagnose_generated_listing(
        listing, postflight, prepared, run_dependencies
    )

    strict_loop = not bool(
        run_dependencies.settings and run_dependencies.settings.mock
    )
    english_review = EnglishListingReview()
    if strict_loop:
        _progress(run_dependencies, "美国本土化审核 Agent", 8)
        try:
            english_review = review_english_listing(
                listing,
                llm=resolve_client(
                    run_dependencies.llm,
                    run_dependencies.settings,
                ),
                rule_findings=_blocking_findings(postflight),
            )
        except EnglishListingReviewError as error:
            raise SimpleOptimizerError("英文文案审核 agent 返回无效结果") from error
    _publish_quality_round(
        run_dependencies,
        1,
        output_diagnosis,
        english_review,
        postflight,
    )
    if not strict_loop and _grammar_score(output_diagnosis) >= _GRAMMAR_SCORE_THRESHOLD:
        return listing, postflight, output_diagnosis
    if not english_review.issues and not _blocking_findings(postflight):
        return listing, postflight, output_diagnosis

    current = listing
    current_postflight = postflight
    current_diagnosis = output_diagnosis
    current_writing = output_writing
    for _attempt in range(2, _MAX_QUALITY_ATTEMPTS + 1):
        _progress(
            run_dependencies,
            f"汇总失败规则并重写 · 第 {_attempt} 轮",
            6,
        )
        # Apply only the exact field fragments identified by the isolated
        # English reviewer. Unmentioned fields and text remain unchanged.
        revised = apply_english_review_suggestions(current, english_review)
        revised_postflight = review_listing(
            postflight_review_request(
                revised,
                prepared.rule_context,
                prepared.evidence,
                prepared.review_request,
            )
        )
        repaired = safely_rewrite_output(
            revised,
            revised_postflight,
            prepared.evidence.suppressed_claim_terms,
        )
        if repaired != revised:
            revised = repaired
            revised_postflight = review_listing(
                postflight_review_request(
                    revised,
                    prepared.rule_context,
                    prepared.evidence,
                    prepared.review_request,
                )
            )
        current = revised
        current_postflight = revised_postflight
        current_diagnosis, current_writing = _diagnose_generated_listing(
            current, current_postflight, prepared, run_dependencies
        )
        try:
            _progress(run_dependencies, "美国本土化审核 Agent", 8)
            english_review = review_english_listing(
                current,
                llm=resolve_client(
                    run_dependencies.llm,
                    run_dependencies.settings,
                ),
                rule_findings=_blocking_findings(current_postflight),
            )
        except EnglishListingReviewError as error:
            raise SimpleOptimizerError("英文文案审核 agent 返回无效结果") from error
        _publish_quality_round(
            run_dependencies,
            _attempt,
            current_diagnosis,
            english_review,
            current_postflight,
        )
        if not english_review.issues and not _blocking_findings(current_postflight):
            return current, current_postflight, current_diagnosis

    remaining = list(
        _quality_failure_reasons(
            current_diagnosis,
            english_review,
            current_postflight,
        )
    )
    detail = "\n".join(f"- {item}" for item in remaining[:12])
    message = f"语法与编辑校验在 {_MAX_QUALITY_ATTEMPTS} 轮后仍未全部通过"
    if detail:
        message += f"。最后一轮未通过项:\n{detail}"
    raise _QualityGateExhausted(
        message,
        candidate=current,
        postflight=current_postflight,
        failures=tuple(remaining),
    )


def _run_optimize_from_prepared(
    prepared: _PreparedDiagnosis,
    run_dependencies: AutomaticOptimizationDependencies,
) -> AutomaticOptimizationResult:
    _progress(run_dependencies, "生成上传稿", 6)
    try:
        listing = optimize_listing_request(
            OptimizerRequest(
                source=prepared.source,
                llm=run_dependencies.llm,
                settings=run_dependencies.settings,
                review_request=prepared.review_request,
                specialized_guidance=prepared.specialized.guidance,
                suppressed_claim_terms=prepared.evidence.suppressed_claim_terms,
                research_context=prepared.research_context,
                source_review_summary=build_review_summary(prepared.source_report),
                diagnosis_summary=build_diagnosis_summary(prepared.diagnosis_report),
                original_source_text=prepared.original_listing_text,
                writing_analysis=prepared.writing_analysis,
                # The observable outer loop owns iterative language/structure
                # quality. Avoid an invisible nested loop that can fail before
                # the UI receives round events or a final candidate.
                strict_quality_loop=False,
            )
        )
    except (TimeoutError, OSError, RuntimeError, ValueError) as error:
        return FailedOptimization(
            code="optimization_failed",
            message=optimization_failure_message(error),
            source_review=prepared.source_report,
            rule_context=prepared.rule_context,
            evidence_bundle=prepared.evidence,
            research_cache=prepared.cache,
            cache_reused=prepared.cache_reused,
            specialized_rule_cache=prepared.specialized.cache,
            specialized_cache_reused=prepared.specialized.cache_reused,
            specialized_rule_guidance=prepared.specialized.guidance,
            diagnosis_report=prepared.diagnosis_report,
            identity=prepared.identity,
            funnel_hypotheses=prepared.funnel_hypotheses,
        )
    polished = polish_listing_with_editor(run_dependencies.settings, listing)
    if polished is not None:
        listing = polished
    _progress(run_dependencies, "确定性安全与发布门禁", 9)
    postflight = review_listing(
        postflight_review_request(
            listing,
            prepared.rule_context,
            prepared.evidence,
            prepared.review_request,
        )
    )
    repaired_listing = safely_rewrite_output(
        listing,
        postflight,
        prepared.evidence.suppressed_claim_terms,
    )
    if repaired_listing != listing:
        listing = repaired_listing
        postflight = review_listing(
            postflight_review_request(
                listing,
                prepared.rule_context,
                prepared.evidence,
                prepared.review_request,
            )
        )
    # Quality gate: diagnose output grammar/structure, re-optimize if poor.
    try:
        listing, postflight, _output_diagnosis = _run_quality_gate(
            listing, postflight, prepared, run_dependencies
        )
    except _QualityGateExhausted as error:
        return FailedOptimization(
            code="optimization_failed",
            message=str(error),
            source_review=prepared.source_report,
            postflight_review=error.postflight,
            rule_context=prepared.rule_context,
            evidence_bundle=prepared.evidence,
            research_cache=prepared.cache,
            cache_reused=prepared.cache_reused,
            specialized_rule_cache=prepared.specialized.cache,
            specialized_cache_reused=prepared.specialized.cache_reused,
            specialized_rule_guidance=prepared.specialized.guidance,
            diagnosis_report=prepared.diagnosis_report,
            identity=prepared.identity,
            funnel_hypotheses=prepared.funnel_hypotheses,
            last_candidate=error.candidate,
            last_candidate_text=format_canonical_optimized_listing(error.candidate),
            quality_failures=error.failures,
        )
    except SimpleOptimizerError as error:
        return FailedOptimization(
            code="optimization_failed",
            message=str(error),
            source_review=prepared.source_report,
            postflight_review=postflight,
            rule_context=prepared.rule_context,
            evidence_bundle=prepared.evidence,
            research_cache=prepared.cache,
            cache_reused=prepared.cache_reused,
            specialized_rule_cache=prepared.specialized.cache,
            specialized_cache_reused=prepared.specialized.cache_reused,
            specialized_rule_guidance=prepared.specialized.guidance,
            diagnosis_report=prepared.diagnosis_report,
            identity=prepared.identity,
            funnel_hypotheses=prepared.funnel_hypotheses,
        )
    if not postflight.can_optimize:
        return NeedsClarification(
            questions=postflight_questions(postflight),
            source_review=prepared.source_report,
            postflight_review=postflight,
            rule_context=prepared.rule_context,
            evidence_bundle=prepared.evidence,
            research_cache=prepared.cache,
            cache_reused=prepared.cache_reused,
            specialized_rule_cache=prepared.specialized.cache,
            specialized_cache_reused=prepared.specialized.cache_reused,
            specialized_rule_guidance=prepared.specialized.guidance,
            diagnosis_report=prepared.diagnosis_report,
            identity=prepared.identity,
            funnel_hypotheses=prepared.funnel_hypotheses,
        )
    return CompletedOptimization(
        listing=listing,
        rendered_text=format_canonical_optimized_listing(listing),
        source_review=prepared.source_report,
        postflight_review=postflight,
        rule_context=prepared.rule_context,
        evidence_bundle=prepared.evidence,
        research_cache=prepared.cache,
        cache_reused=prepared.cache_reused,
        specialized_rule_cache=prepared.specialized.cache,
        specialized_cache_reused=prepared.specialized.cache_reused,
        specialized_rule_guidance=prepared.specialized.guidance,
        diagnosis_report=prepared.diagnosis_report,
        identity=prepared.identity,
        funnel_hypotheses=prepared.funnel_hypotheses,
    )


__all__ = [
    "issue_approval_token",
    "run_automatic_optimization",
]
