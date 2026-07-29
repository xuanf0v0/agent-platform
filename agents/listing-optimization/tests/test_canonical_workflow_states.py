from __future__ import annotations

from amazon_copy.schemas.canonical_deliverables import DeliverableKind
from amazon_copy.schemas.canonical_workflow import (
    AuditReady,
    AuthorizationScope,
    AwaitingApproval,
    AwaitingFacts,
    Completed,
    ContinuationAuthorization,
    ContinuationAuthorized,
    Failed,
    FailureCode,
    Generating,
    WorkflowQuestion,
    WorkflowState,
    workflow_status,
)
from pydantic import TypeAdapter

from tests.canonical_workflow_support import AUTHORIZED_AT, audit, stage_two

_WORKFLOW_ID = "workflow:state-roundtrip"
_CONTINUATION_ID = "continuation:state-roundtrip"


def test_all_workflow_variants_round_trip_by_discriminator() -> None:
    # Given: each of the seven exhaustive workflow variants.
    authorization = ContinuationAuthorization(
        continuation_id=_CONTINUATION_ID,
        expected_revision=1,
        scope=AuthorizationScope.SINGLE,
        authorized_at=AUTHORIZED_AT,
    )
    states: tuple[WorkflowState, ...] = (
        AuditReady(workflow_id=_WORKFLOW_ID, revision=0, audit=audit()),
        AwaitingApproval(
            workflow_id=_WORKFLOW_ID,
            revision=1,
            audit=audit(),
            target=DeliverableKind.NORMAL_STAGE_2,
            continuation_id=_CONTINUATION_ID,
        ),
        AwaitingFacts(
            workflow_id=_WORKFLOW_ID,
            revision=1,
            audit=audit(),
            target=DeliverableKind.NORMAL_STAGE_2,
            continuation_id=_CONTINUATION_ID,
            questions=(
                WorkflowQuestion(
                    code="fact.dimension",
                    field="dimensions",
                    prompt="Confirm the verified dimensions.",
                ),
            ),
        ),
        ContinuationAuthorized(
            workflow_id=_WORKFLOW_ID,
            revision=2,
            audit=audit(),
            target=DeliverableKind.NORMAL_STAGE_2,
            authorization=authorization,
        ),
        Generating(
            workflow_id=_WORKFLOW_ID,
            revision=3,
            audit=audit(),
            target=DeliverableKind.NORMAL_STAGE_2,
            authorization=authorization,
        ),
        Completed(
            workflow_id=_WORKFLOW_ID,
            revision=4,
            deliverable=stage_two(),
        ),
        Failed(
            workflow_id=_WORKFLOW_ID,
            revision=2,
            code=FailureCode.CANCELLED,
            message="Cancelled by seller",
            recoverable=False,
        ),
    )
    adapter: TypeAdapter[WorkflowState] = TypeAdapter(WorkflowState)

    # When: every state crosses the serialized workflow boundary.
    parsed = tuple(adapter.validate_json(state.model_dump_json()) for state in states)

    # Then: the tagged type and frozen state survive without fallback variants.
    assert tuple(workflow_status(state) for state in parsed) == tuple(
        state.state for state in states
    )
    assert all(state.model_config.get("frozen") is True for state in parsed)
