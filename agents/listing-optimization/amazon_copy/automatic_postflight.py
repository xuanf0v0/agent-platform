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

_BULLET_EVIDENCE_GAP = "BULLET_EVIDENCE_GAP"


def bullet_evidence_questions(
    current_count: int,
    target_count: int,
) -> tuple[ClarificationQuestion, ...]:
    """Ask once for the exact evidence gap instead of inventing filler bullets."""
    missing = max(0, target_count - current_count)
    if missing == 0:
        return ()
    return (
        ClarificationQuestion(
            code="postflight_bullet_evidence_gap",
            finding_code=_BULLET_EVIDENCE_GAP,
            fact_key="additional_bullet_facts",
            question_zh=(
                f"安全清理后只保留 {current_count}/{target_count} 条 Bullet。请补充至少 "
                f"{missing} 个尚未出现且可核实的产品事实，例如材质/结构、尺寸或调节范围、"
                "包装配件、安装方式、适用范围、护理或使用限制，并写明具体值。"
                f"如果无法确认，可回复“按现有 {current_count} 条继续”，系统不会编造补齐。"
            ),
            evidence_needed="卖家确认、包装/BOM、说明书或其他本品一方资料",
        ),
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
                if question.finding_code == _BULLET_EVIDENCE_GAP:
                    retained_answers.append(answer)
                else:
                    suppressed.extend(question.claim_terms)
    return context.model_copy(
        update={
            "user_claims": tuple(claims),
            "suppressed_claim_terms": tuple(dict.fromkeys(suppressed)),
            "clarification_answers": tuple(retained_answers),
        }
    )


__all__ = [
    "apply_postflight_answers",
    "bullet_evidence_questions",
    "postflight_questions",
]
