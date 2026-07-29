"""Step-gated conversation contract for the four Amazon copy workflows."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class CopyWorkflow(StrEnum):
    """User-selectable copy workflow."""

    WRITE = "write"
    OPTIMIZE = "optimize"
    SEO = "seo"
    ANALYZE = "analyze"


class WorkflowStep(StrEnum):
    """Ordered user-visible workflow steps."""

    BASIC_INPUT = "basic_input"
    MARKET_RESEARCH = "market_research"
    PRODUCT_MANUAL = "product_manual"
    PRODUCT_ANALYSIS = "product_analysis"
    COMPETITOR_INPUT = "competitor_input"
    COMPETITOR_ANALYSIS = "competitor_analysis"
    SELLING_POINTS = "selling_points"
    SEO_TERMS = "seo_terms"
    COPY_OUTPUT = "copy_output"
    SOURCE_ANALYSIS = "source_analysis"
    SEO_NEEDS = "seo_needs"
    SEO_AUDIT = "seo_audit"
    SCORECARD = "scorecard"
    COMPLETED = "completed"


_ROUTES: Final[dict[CopyWorkflow, tuple[WorkflowStep, ...]]] = {
    CopyWorkflow.WRITE: (
        WorkflowStep.BASIC_INPUT,
        WorkflowStep.MARKET_RESEARCH,
        WorkflowStep.PRODUCT_MANUAL,
        WorkflowStep.PRODUCT_ANALYSIS,
        WorkflowStep.COMPETITOR_INPUT,
        WorkflowStep.COMPETITOR_ANALYSIS,
        WorkflowStep.SELLING_POINTS,
        WorkflowStep.SEO_TERMS,
        WorkflowStep.COPY_OUTPUT,
        WorkflowStep.COMPLETED,
    ),
    CopyWorkflow.OPTIMIZE: (
        WorkflowStep.BASIC_INPUT,
        WorkflowStep.SOURCE_ANALYSIS,
        WorkflowStep.COPY_OUTPUT,
        WorkflowStep.COMPLETED,
    ),
    CopyWorkflow.SEO: (
        WorkflowStep.BASIC_INPUT,
        WorkflowStep.SEO_NEEDS,
        WorkflowStep.SEO_AUDIT,
        WorkflowStep.COMPLETED,
    ),
    CopyWorkflow.ANALYZE: (
        WorkflowStep.BASIC_INPUT,
        WorkflowStep.SCORECARD,
        WorkflowStep.COMPLETED,
    ),
}

_APPROVAL_STEPS: Final[frozenset[WorkflowStep]] = frozenset(
    {
        WorkflowStep.MARKET_RESEARCH,
        WorkflowStep.PRODUCT_ANALYSIS,
        WorkflowStep.COMPETITOR_ANALYSIS,
        WorkflowStep.SELLING_POINTS,
        WorkflowStep.SOURCE_ANALYSIS,
        WorkflowStep.SEO_NEEDS,
    }
)
_INVALID_STEP_CODE: Final = "invalid_copy_workflow_step"
_INVALID_STEP_MESSAGE: Final = "step is not in workflow route"
_APPROVAL_CODE: Final = "copy_workflow_approval_required"
_APPROVAL_MESSAGE: Final = "explicit user approval is required before continuing"

_REQUIRED_INPUTS: Final[dict[tuple[CopyWorkflow, WorkflowStep], tuple[str, ...]]] = {
    (CopyWorkflow.WRITE, WorkflowStep.BASIC_INPUT): ("product_name", "target_market"),
    (CopyWorkflow.WRITE, WorkflowStep.PRODUCT_MANUAL): ("product_manual",),
    (CopyWorkflow.WRITE, WorkflowStep.COMPETITOR_INPUT): ("competitor_copy_optional",),
    (CopyWorkflow.WRITE, WorkflowStep.SEO_TERMS): ("top20_rootwords", "top20_keywords"),
    (CopyWorkflow.OPTIMIZE, WorkflowStep.BASIC_INPUT): (
        "product_name",
        "target_market",
        "five_bullets",
        "top20_rootwords",
        "top20_keywords",
    ),
    (CopyWorkflow.SEO, WorkflowStep.BASIC_INPUT): (
        "target_market",
        "five_bullets",
        "top20_rootwords",
        "top20_keywords",
    ),
    (CopyWorkflow.ANALYZE, WorkflowStep.BASIC_INPUT): (
        "five_bullets",
        "top20_rootwords",
        "top20_keywords",
    ),
}


class CopyWorkflowState(BaseModel):
    """Serializable state that prevents skipping required user approvals."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    workflow: CopyWorkflow
    step: WorkflowStep = WorkflowStep.BASIC_INPUT
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def step_belongs_to_route(self) -> CopyWorkflowState:
        """Reject steps that do not belong to the selected workflow."""
        if self.step not in _ROUTES[self.workflow]:
            raise PydanticCustomError(_INVALID_STEP_CODE, _INVALID_STEP_MESSAGE)
        return self


def next_step(state: CopyWorkflowState, *, approved: bool | None = None) -> CopyWorkflowState:
    """Advance exactly one step, requiring explicit approval after analysis stages."""
    route = _ROUTES[state.workflow]
    if state.step is WorkflowStep.COMPLETED:
        return state
    if state.step in _APPROVAL_STEPS and approved is not True:
        raise PydanticCustomError(
            _APPROVAL_CODE,
            _APPROVAL_MESSAGE,
        )
    index = route.index(state.step)
    return state.model_copy(update={"step": route[index + 1], "revision": state.revision + 1})


def route_for(workflow: CopyWorkflow | str) -> tuple[WorkflowStep, ...]:
    """Return the immutable ordered route for one workflow."""
    resolved = workflow if isinstance(workflow, CopyWorkflow) else CopyWorkflow(workflow)
    return _ROUTES[resolved]


def required_inputs(state: CopyWorkflowState) -> tuple[str, ...]:
    """Return only the fields that may be requested at the current step."""
    return _REQUIRED_INPUTS.get((state.workflow, state.step), ())


__all__ = [
    "CopyWorkflow",
    "CopyWorkflowState",
    "WorkflowStep",
    "next_step",
    "required_inputs",
    "route_for",
]
