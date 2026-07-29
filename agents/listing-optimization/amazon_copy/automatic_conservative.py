"""Conservative continuation for unsupported listing claims."""

from collections.abc import Callable
from dataclasses import dataclass

from amazon_copy.automatic_clarification_interpreter import interpret_clarification_context
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticOptimizationResult,
    ClarificationAnswer,
    FailedOptimization,
    NeedsClarification,
)
from amazon_copy.automatic_postflight import apply_postflight_answers

RunOnce = Callable[
    [str, AutomaticOptimizationContext, AutomaticOptimizationDependencies],
    AutomaticOptimizationResult,
]


@dataclass(frozen=True, slots=True)
class ConservativeRunRequest:
    """Inputs for a bounded conservative optimization run."""

    source_text: str
    context: AutomaticOptimizationContext
    dependencies: AutomaticOptimizationDependencies
    run_once: RunOnce


def conservative_resume_context(
    result: NeedsClarification,
    previous: AutomaticOptimizationContext,
) -> AutomaticOptimizationContext:
    """Resolve routing gaps safely and remove every unsupported product claim."""
    answers = tuple(
        ClarificationAnswer(
            question_code=question.code,
            action="confirm" if question.fact_key in {"marketplace", "product_type"} else "remove",
            value=(
                "US"
                if question.fact_key == "marketplace"
                else "GENERAL_PRODUCT" if question.fact_key == "product_type" else ""
            ),
        )
        for question in result.questions
    )
    merged_answers_by_code = {
        answer.question_code: answer for answer in previous.clarification_answers
    }
    merged_answers_by_code.update(
        {answer.question_code: answer for answer in answers}
    )
    removed_question_terms = tuple(
        term
        for question, answer in zip(result.questions, answers, strict=True)
        if answer.action == "remove"
        for term in question.claim_terms
    )
    evidence = result.evidence_bundle
    postflight_unauthorized_terms = (
        ()
        if result.postflight_review is None
        else tuple(
            dict.fromkeys(
                term
                for finding in result.postflight_review.findings
                if finding.code == "UNAUTHORIZED_NEW_FACT"
                for term in finding.claim_terms
            )
        )
    )
    merged_suppressed = tuple(
        dict.fromkeys(
            (
                *previous.suppressed_claim_terms,
                *evidence.suppressed_claim_terms,
                *postflight_unauthorized_terms,
                *removed_question_terms,
            )
        )
    )
    return previous.model_copy(
        update={
            "rule_context": result.rule_context,
            "user_claims": evidence.user_claims,
            "suppressed_claim_terms": merged_suppressed,
            "allowed_keywords": evidence.allowed_keywords,
            "clarification_answers": tuple(merged_answers_by_code.values()),
            "clarification_reply": None,
            "clarification_questions": result.questions,
            "cached_research": result.research_cache,
            "cached_specialized_rules": result.specialized_rule_cache,
        }
    )


def run_conservatively(request: ConservativeRunRequest) -> AutomaticOptimizationResult:
    """Automatically remove unsupported claims until review settles."""
    run_context = request.context
    last_clarification: NeedsClarification | None = None
    for _attempt in range(20):
        interpreted_context = interpret_clarification_context(
            run_context,
            run_context.clarification_questions,
            request.dependencies,
        )
        active_context = apply_postflight_answers(interpreted_context or run_context)
        result = request.run_once(
            request.source_text,
            active_context,
            request.dependencies,
        )
        if not run_context.auto_resolve_unverified or not isinstance(
            result, NeedsClarification
        ):
            return result
        last_clarification = result
        run_context = conservative_resume_context(result, active_context)
    if last_clarification is None:
        return FailedOptimization(
            code="optimization_failed",
            message="Conservative automatic rewriting could not start.",
        )
    return FailedOptimization(
        code="optimization_failed",
        message="Conservative automatic rewriting did not converge.",
        source_review=last_clarification.source_review,
        postflight_review=last_clarification.postflight_review,
        rule_context=last_clarification.rule_context,
        evidence_bundle=last_clarification.evidence_bundle,
        research_cache=last_clarification.research_cache,
        cache_reused=last_clarification.cache_reused,
        specialized_rule_cache=last_clarification.specialized_rule_cache,
        specialized_cache_reused=last_clarification.specialized_cache_reused,
        specialized_rule_guidance=last_clarification.specialized_rule_guidance,
        diagnosis_report=last_clarification.diagnosis_report,
    )


__all__ = ["ConservativeRunRequest", "conservative_resume_context", "run_conservatively"]
