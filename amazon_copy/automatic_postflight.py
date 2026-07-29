"""Postflight continuation questions and seller decisions."""

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    ClarificationAnswer,
)
from amazon_copy.review.models import (
    ClarificationQuestion,
    EvidenceSource,
    FactClaim,
    ListingReviewReport,
)


def postflight_questions(report: ListingReviewReport) -> tuple[ClarificationQuestion, ...]:
    """Convert remaining postflight blocks into conversational questions."""
    return tuple(
        ClarificationQuestion(
            code=f"postflight_{index}_{finding.code.casefold()}",
            finding_code=finding.code,
            fact_key=finding.fact_key or finding.field,
            question_zh=(
                f"优化稿仍触发“{finding.message_zh}”。请补充本品依据; "
                "无法确认时请回复删除, 系统会继续重写并复核。"
            ),
            evidence_needed=finding.evidence_required or "卖家确认或对应产品资料",
            claim_terms=finding.claim_terms,
        )
        for index, finding in enumerate(report.findings, start=1)
        if finding.severity == "BLOCK"
    )


def apply_postflight_answers(
    context: AutomaticOptimizationContext,
) -> AutomaticOptimizationContext:
    """Persist postflight confirmations and removals for the next generation turn."""
    questions = {question.code: question for question in context.clarification_questions}
    claims = list(context.user_claims)
    suppressed = list(context.suppressed_claim_terms)
    retained_answers: list[ClarificationAnswer] = []
    for answer in context.clarification_answers:
        question = questions.get(answer.question_code)
        if question is None or not answer.question_code.startswith("postflight_"):
            retained_answers.append(answer)
            continue
        match answer.action:
            case "confirm":
                claims.append(
                    FactClaim(
                        key=question.fact_key,
                        value=" ".join((*question.claim_terms, answer.value)).strip(),
                        source=EvidenceSource.PACKAGING_BOM_USER,
                        sku_scope="all",
                    )
                )
            case "remove":
                suppressed.extend(question.claim_terms)
    return context.model_copy(
        update={
            "user_claims": tuple(claims),
            "suppressed_claim_terms": tuple(dict.fromkeys(suppressed)),
            "clarification_answers": tuple(retained_answers),
        }
    )


__all__ = ["apply_postflight_answers", "postflight_questions"]
