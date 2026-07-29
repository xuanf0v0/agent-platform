"""Non-compensating ten-dimension listing scores."""

from typing import Final, Literal

from amazon_copy.review.models import ReviewFinding, ReviewScore

Dimension = Literal[
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
]

_DIMENSIONS: Final[tuple[Dimension, ...]] = (
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
_DIMENSION_CODES: Final[dict[Dimension, frozenset[str]]] = {
    "compliance": frozenset(
        {
            "EXTERNAL_CONTACT",
            "PARENT_CHILD_SPEC",
            "PROMOTION_PRICE",
            "REFUND_REVIEW",
            "TITLE_RESTRICTED_CHAR",
        }
    ),
    "a9_seo": frozenset(
        {"HIGHLIGHTS_LENGTH", "SEARCH_TERMS_BYTES", "TITLE_LENGTH", "TITLE_WORD_REPETITION"}
    ),
    "semantic_coverage": frozenset({"BULLET_TASK_COVERAGE", "BULLET_DUPLICATION"}),
    "grammar": frozenset({"TITLE_FRAGMENT", "TITLE_WRITTEN_NUMBER"}),
    "readability": frozenset(
        {"BULLET_DUPLICATION", "HIGHLIGHTS_LENGTH", "TITLE_LENGTH", "TITLE_WORD_REPETITION"}
    ),
    "selling_points": frozenset(
        {"BULLET_COUNT_OPPORTUNITY", "BULLET_TASK_COVERAGE", "BULLET_DUPLICATION"}
    ),
    "localization": frozenset({"LOCALIZATION_LANGUAGE", "TITLE_WRITTEN_NUMBER"}),
    "technical_accuracy": frozenset(
        {
            "ACCESSORY_COUNT_AMBIGUITY",
            "ATTRIBUTE_CONFLICT",
            "FACT_CONFLICT",
            "FACT_PRIORITY_CONFLICT",
            "FACT_QUANTITY_MISMATCH",
            "OVERBROAD_COMPATIBILITY",
            "PRODUCT_CLASSIFICATION_UNRESOLVED",
            "THIRD_PARTY_FACT_REJECTED",
            "UNVERIFIED_PERFORMANCE",
            "UNVERIFIED_SAFETY",
        }
    ),
    "emotional_appeal": frozenset({"BULLET_DUPLICATION", "PROMOTION_PRICE"}),
    "purchase_motivation": frozenset(
        {"BULLET_COUNT_OPPORTUNITY", "BULLET_TASK_COVERAGE", "PROMOTION_PRICE"}
    ),
}


def _rationale(dimension: Dimension, relevant: tuple[ReviewFinding, ...]) -> str:
    if not relevant:
        return f"{dimension}：未发现该维度的确定性问题"
    issues = "、".join(f"{finding.code}:{finding.severity}" for finding in relevant)
    return f"{dimension}：依据已定位问题独立扣分（{issues}）"


def build_scores(findings: tuple[ReviewFinding, ...]) -> tuple[ReviewScore, ...]:
    """Score every dimension only from its located deterministic issues."""
    scores: list[ReviewScore] = []
    for dimension in _DIMENSIONS:
        relevant = tuple(
            finding for finding in findings if finding.code in _DIMENSION_CODES[dimension]
        )
        penalty = sum(2.5 if finding.severity == "BLOCK" else 0.75 for finding in relevant)
        scores.append(
            ReviewScore(
                dimension=dimension,
                score=max(0.0, round(10.0 - penalty, 1)),
                rationale_zh=_rationale(dimension, relevant),
            )
        )
    return tuple(scores)


__all__ = ["build_scores"]
