"""Validated canonical workflow transitions and public state exports."""

from typing import ClassVar, Final, assert_never

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_core import PydanticCustomError

from amazon_copy.schemas.canonical_deliverables import (
    AuditDeliverable,
    DeliverableKind,
    deliverable_kind,
)
from amazon_copy.schemas.canonical_workflow_states import (
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
    WorkflowStatus,
    workflow_status,
)

_ALLOWED_TRANSITIONS: Final[dict[WorkflowStatus, frozenset[WorkflowStatus]]] = {
    WorkflowStatus.AUDIT_READY: frozenset(
        {WorkflowStatus.AWAITING_APPROVAL, WorkflowStatus.AWAITING_FACTS, WorkflowStatus.FAILED}
    ),
    WorkflowStatus.AWAITING_APPROVAL: frozenset(
        {
            WorkflowStatus.CONTINUATION_AUTHORIZED,
            WorkflowStatus.AWAITING_FACTS,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.AWAITING_FACTS: frozenset(
        {
            WorkflowStatus.AUDIT_READY,
            WorkflowStatus.CONTINUATION_AUTHORIZED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.CONTINUATION_AUTHORIZED: frozenset(
        {WorkflowStatus.GENERATING, WorkflowStatus.AWAITING_FACTS, WorkflowStatus.FAILED}
    ),
    WorkflowStatus.GENERATING: frozenset(
        {WorkflowStatus.COMPLETED, WorkflowStatus.AWAITING_FACTS, WorkflowStatus.FAILED}
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
}
_IDENTITY_ERROR: Final = "workflow_identity_mismatch"
_IDENTITY_MESSAGE: Final = "workflow transition must retain its workflow id"
_REVISION_ERROR: Final = "stale_workflow_revision"
_REVISION_MESSAGE: Final = "next workflow revision must advance by exactly one"
_TRANSITION_ERROR: Final = "invalid_workflow_transition"
_TRANSITION_MESSAGE: Final = "workflow state edge is not allowed"
_TARGET_ERROR: Final = "workflow_target_mismatch"
_TARGET_MESSAGE: Final = "workflow target changed during continuation"
_CONTINUATION_ERROR: Final = "stale_continuation"
_CONTINUATION_MESSAGE: Final = "continuation token or expected revision is stale"
_DELIVERABLE_ERROR: Final = "deliverable_kind_mismatch"
_DELIVERABLE_MESSAGE: Final = "completed deliverable does not match generation target"


def _state_target(state: WorkflowState) -> DeliverableKind | None:
    match state:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case AuditReady() | Completed() | Failed():
            return None
        case AwaitingApproval(target=target):
            return target
        case AwaitingFacts(target=target):
            return target
        case ContinuationAuthorized(target=target):
            return target
        case Generating(target=target):
            return target
    assert_never(state)


def _state_audit(state: WorkflowState) -> AuditDeliverable | None:
    match state:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case AuditReady(audit=audit):
            return audit
        case AwaitingApproval(audit=audit):
            return audit
        case AwaitingFacts(audit=audit):
            return audit
        case ContinuationAuthorized(audit=audit):
            return audit
        case Generating(audit=audit):
            return audit
        case Completed() | Failed():
            return None
    assert_never(state)


def _pending_continuation_id(state: WorkflowState) -> str | None:
    match state:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case AwaitingApproval(continuation_id=continuation_id):
            return continuation_id
        case AwaitingFacts(continuation_id=continuation_id):
            return continuation_id
        case AuditReady() | ContinuationAuthorized() | Generating() | Completed() | Failed():
            return None
    assert_never(state)


def _validate_terminal_payload(
    current: WorkflowState,
    next_state: WorkflowState,
    current_target: DeliverableKind | None,
) -> None:
    match next_state:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case ContinuationAuthorized(authorization=authorization):
            pending_id = _pending_continuation_id(current)
            if (
                pending_id is None
                or authorization.continuation_id != pending_id
                or authorization.expected_revision != current.revision
            ):
                raise PydanticCustomError(_CONTINUATION_ERROR, _CONTINUATION_MESSAGE)
            return
        case Completed(deliverable=deliverable):
            if current_target is None or deliverable_kind(deliverable) != current_target:
                raise PydanticCustomError(_DELIVERABLE_ERROR, _DELIVERABLE_MESSAGE)
            return
        case AuditReady() | AwaitingApproval() | AwaitingFacts() | Generating() | Failed():
            return
    assert_never(next_state)


class WorkflowTransition(BaseModel):
    """Boundary-validated edge between two serialized workflow states."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    current: WorkflowState
    next: WorkflowState

    @model_validator(mode="after")
    def validate_edge(self) -> "WorkflowTransition":
        """Reject stale, illegal, or target-mismatched state changes."""
        if self.current.workflow_id != self.next.workflow_id:
            raise PydanticCustomError(_IDENTITY_ERROR, _IDENTITY_MESSAGE)
        if self.next.revision != self.current.revision + 1:
            raise PydanticCustomError(_REVISION_ERROR, _REVISION_MESSAGE)
        if self.next.state not in _ALLOWED_TRANSITIONS[self.current.state]:
            raise PydanticCustomError(_TRANSITION_ERROR, _TRANSITION_MESSAGE)

        current_target = _state_target(self.current)
        next_target = _state_target(self.next)
        if current_target is not None and next_target is not None and current_target != next_target:
            raise PydanticCustomError(_TARGET_ERROR, _TARGET_MESSAGE)

        current_audit = _state_audit(self.current)
        next_audit = _state_audit(self.next)
        if (
            current_audit is not None
            and next_audit is not None
            and self.current.state is not WorkflowStatus.AWAITING_FACTS
            and current_audit != next_audit
        ):
            raise PydanticCustomError(_TRANSITION_ERROR, _TRANSITION_MESSAGE)

        _validate_terminal_payload(self.current, self.next, current_target)
        return self


__all__ = [
    "AuditReady",
    "AuthorizationScope",
    "AwaitingApproval",
    "AwaitingFacts",
    "Completed",
    "ContinuationAuthorization",
    "ContinuationAuthorized",
    "Failed",
    "FailureCode",
    "Generating",
    "WorkflowQuestion",
    "WorkflowState",
    "WorkflowStatus",
    "WorkflowTransition",
    "workflow_status",
]
