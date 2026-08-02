"""Structured semantic coverage for shopper decision tasks."""

from __future__ import annotations

from typing import Annotated, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DecisionTaskName = Literal[
    "core_value",
    "product_facts",
    "usage_fit",
    "scenario_outcome",
    "expectation_care",
]
BulletIndex = Annotated[int, Field(ge=1, le=10)]

DECISION_TASKS: Final[tuple[DecisionTaskName, ...]] = (
    "core_value",
    "product_facts",
    "usage_fit",
    "scenario_outcome",
    "expectation_care",
)
DECISION_TASK_LABELS_ZH: Final[dict[DecisionTaskName, str]] = {
    "core_value": "核心价值与主要优势",
    "product_facts": "规格、设计与适用对象",
    "usage_fit": "使用方式与适配条件",
    "scenario_outcome": "使用场景与预期结果",
    "expectation_care": "包装、限制、护理与预期管理",
}


class DecisionTaskAssessment(BaseModel):
    """One evidence-backed semantic decision-task classification."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    task: DecisionTaskName
    covered: bool
    bullet_indexes: tuple[BulletIndex, ...] = ()
    evidence: str = ""

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> DecisionTaskAssessment:
        """Require cited listing evidence for every positive classification."""
        if self.covered and (not self.bullet_indexes or not self.evidence.strip()):
            msg = "covered decision tasks require bullet_indexes and exact evidence"
            raise ValueError(msg)
        if not self.covered and (self.bullet_indexes or self.evidence.strip()):
            msg = "uncovered decision tasks cannot include evidence"
            raise ValueError(msg)
        return self


def validated_semantic_tasks(
    bullets: tuple[str, ...],
    assessments: tuple[DecisionTaskAssessment, ...],
) -> tuple[DecisionTaskAssessment, ...]:
    """Accept only a complete, unique classification with exact cited evidence."""
    by_task: dict[DecisionTaskName, DecisionTaskAssessment] = {}
    for assessment in assessments:
        if assessment.task in by_task:
            return ()
        by_task[assessment.task] = assessment
    if set(by_task) != set(DECISION_TASKS):
        return ()

    ordered = tuple(by_task[task] for task in DECISION_TASKS)
    for assessment in ordered:
        if not assessment.covered:
            continue
        evidence = assessment.evidence.strip()
        cited_bullets = tuple(
            bullets[index - 1]
            for index in assessment.bullet_indexes
            if 1 <= index <= len(bullets)
        )
        if not cited_bullets or not any(evidence in bullet for bullet in cited_bullets):
            return ()
    return ordered


__all__ = [
    "DECISION_TASKS",
    "DECISION_TASK_LABELS_ZH",
    "DecisionTaskAssessment",
    "DecisionTaskName",
    "validated_semantic_tasks",
]
