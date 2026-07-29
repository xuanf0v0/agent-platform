"""Phase-aware actions and seller clarification questions."""

from dataclasses import dataclass
from typing import Final, assert_never

from amazon_copy.review.models import (
    ClarificationQuestion,
    ReviewDisposition,
    ReviewFinding,
    ReviewPhase,
)


@dataclass(frozen=True, slots=True)
class _QuestionSpec:
    code: str
    fact_key: str
    label_zh: str
    evidence_zh: str


_QUESTION_SPECS: Final = {
    "ACCESSORY_COUNT_AMBIGUITY": _QuestionSpec(
        "confirm_accessory_counts",
        "included_accessories",
        "配件数量",
        "包装清单、BOM或卖家逐项确认",
    ),
    "FACT_CONFLICT": _QuestionSpec(
        "resolve_fact_conflict",
        "conflicting_fact",
        "冲突产品事实",
        "包装、BOM、说明书或卖家确认",
    ),
    "FACT_PRIORITY_CONFLICT": _QuestionSpec(
        "resolve_fact_priority",
        "conflicting_fact",
        "被权威证据否定的产品事实",
        "更正后的包装、BOM或说明书",
    ),
    "FACT_QUANTITY_MISMATCH": _QuestionSpec(
        "confirm_product_quantity",
        "quantity",
        "产品数量",
        "包装清单、BOM或卖家确认",
    ),
    "OVERBROAD_COMPATIBILITY": _QuestionSpec(
        "confirm_compatibility_evidence",
        "compatibility",
        "兼容性范围",
        "逐项兼容性测试或卖家确认删除宽泛宣称",
    ),
    "PARENT_CHILD_SPEC": _QuestionSpec(
        "confirm_variation_scope",
        "variation_scope",
        "父子体规格范围",
        "变体主题和子体属性清单",
    ),
    "PRODUCT_CLASSIFICATION_UNRESOLVED": _QuestionSpec(
        "confirm_product_classification",
        "product_classification",
        "产品分类",
        "包装标签、合规分类或卖家确认",
    ),
    "UNVERIFIED_PERFORMANCE": _QuestionSpec(
        "confirm_performance_evidence",
        "performance",
        "性能宣称",
        "说明书、实测报告或卖家确认删除该宣称",
    ),
    "UNVERIFIED_SAFETY": _QuestionSpec(
        "confirm_safety_evidence",
        "safety",
        "安全宣称",
        "安全测试、认证文件或卖家确认删除该宣称",
    ),
}
_SPECIALIZED_FACT_CODE: Final = "SPECIALIZED_FACT_UNVERIFIED"


def review_disposition(
    phase: ReviewPhase,
    findings: tuple[ReviewFinding, ...],
) -> ReviewDisposition:
    """Choose automatic repair, seller clarification, or terminal suppression."""
    blocking = tuple(finding for finding in findings if finding.severity == "BLOCK")
    if phase is ReviewPhase.POSTFLIGHT:
        return "terminal" if blocking else "auto_repair"
    if phase is ReviewPhase.SOURCE:
        if any(
            finding.code in _QUESTION_SPECS or finding.code == _SPECIALIZED_FACT_CODE
            for finding in blocking
        ):
            return "ask_user"
        return "auto_repair"
    assert_never(phase)


def build_clarification_questions(
    findings: tuple[ReviewFinding, ...],
) -> tuple[ClarificationQuestion, ...]:
    """Build one stable, located question for every unresolved core fact."""
    questions: list[ClarificationQuestion] = []
    seen: set[str] = set()
    for finding in findings:
        if (
            finding.code == _SPECIALIZED_FACT_CODE
            and finding.severity == "BLOCK"
            and finding.question_code
            and finding.question_code not in seen
        ):
            terms = "、".join(finding.claim_terms)
            questions.append(
                ClarificationQuestion(
                    code=finding.question_code,
                    finding_code=finding.code,
                    fact_key=finding.fact_key,
                    question_zh=(
                        f"请提供支持“{terms}”的{finding.evidence_required}；"
                        "若无法提供，请确认删除该宣称。"
                    ),
                    evidence_needed=finding.evidence_required,
                    claim_terms=finding.claim_terms,
                )
            )
            seen.add(finding.question_code)
            continue
        spec = _QUESTION_SPECS.get(finding.code)
        if spec is None or finding.severity != "BLOCK" or spec.code in seen:
            continue
        fact_key = (
            finding.field.removeprefix("fact.")
            if finding.field.startswith("fact.")
            else spec.fact_key
        )
        terms = "、".join(finding.claim_terms)
        subject = f"“{terms}”" if terms else spec.label_zh
        evidence = finding.evidence_required or spec.evidence_zh
        questions.append(
            ClarificationQuestion(
                code=spec.code,
                finding_code=finding.code,
                fact_key=fact_key,
                question_zh=f"请提供支持{subject}的{evidence}；若无法提供，请确认删除该宣称。",
                evidence_needed=evidence,
                claim_terms=finding.claim_terms,
            )
        )
        seen.add(spec.code)
    return tuple(questions)


__all__ = ["build_clarification_questions", "review_disposition"]
