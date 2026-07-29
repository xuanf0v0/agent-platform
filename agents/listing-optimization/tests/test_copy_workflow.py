from __future__ import annotations

import pytest
from amazon_copy.copy_workflow import (
    CopyWorkflow,
    CopyWorkflowState,
    WorkflowStep,
    next_step,
    required_inputs,
    route_for,
)
from pydantic_core import PydanticCustomError


def test_write_route_preserves_required_order() -> None:
    assert route_for("write") == (
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
    )


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        (CopyWorkflow.OPTIMIZE, WorkflowStep.SOURCE_ANALYSIS),
        (CopyWorkflow.SEO, WorkflowStep.SEO_NEEDS),
        (CopyWorkflow.ANALYZE, WorkflowStep.SCORECARD),
    ],
)
def test_mode_routes_from_basic_input(workflow: CopyWorkflow, expected: WorkflowStep) -> None:
    state = CopyWorkflowState(workflow=workflow)
    assert next_step(state).step is expected


def test_analysis_step_requires_explicit_approval() -> None:
    state = CopyWorkflowState(workflow="write", step="market_research")
    with pytest.raises(PydanticCustomError, match="approval"):
        next_step(state)
    advanced = next_step(state, approved=True)
    assert advanced.step is WorkflowStep.PRODUCT_MANUAL
    assert advanced.revision == 1


def test_cannot_mix_steps_between_workflows() -> None:
    with pytest.raises(ValueError, match="step is not in workflow route"):
        CopyWorkflowState(workflow="analyze", step="market_research")


def test_write_collects_terms_only_after_selling_points() -> None:
    initial = CopyWorkflowState(workflow="write")
    terms = CopyWorkflowState(workflow="write", step="seo_terms")
    assert required_inputs(initial) == ("product_name", "target_market")
    assert required_inputs(terms) == ("top20_rootwords", "top20_keywords")


def test_listing_only_modes_request_complete_mode_specific_input() -> None:
    optimize = required_inputs(CopyWorkflowState(workflow="optimize"))
    seo = required_inputs(CopyWorkflowState(workflow="seo"))
    analyze = required_inputs(CopyWorkflowState(workflow="analyze"))
    assert "product_name" in optimize
    assert "target_market" in optimize
    assert "target_market" in seo
    assert "five_bullets" in seo
    assert analyze == ("five_bullets", "top20_rootwords", "top20_keywords")
