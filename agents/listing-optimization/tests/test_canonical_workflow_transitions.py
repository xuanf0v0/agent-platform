from __future__ import annotations

import pytest
from amazon_copy.schemas.canonical_deliverables import (
    DeliverableKind,
    KeywordAuditDeliverable,
    KeywordAuditEntry,
)
from amazon_copy.schemas.canonical_models import CanonicalMarketplace
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
    WorkflowTransition,
)
from pydantic import ValidationError

from tests.canonical_workflow_support import AUTHORIZED_AT, audit, stage_two

_WORKFLOW_ID = "workflow:transition-matrix"
_APPROVAL_ID = "continuation:approval"
_FACTS_ID = "continuation:facts"


def _question() -> WorkflowQuestion:
    return WorkflowQuestion(
        code="fact.dimension",
        field="dimensions",
        prompt="Confirm the verified dimensions.",
    )


def _authorization(continuation_id: str, expected_revision: int) -> ContinuationAuthorization:
    return ContinuationAuthorization(
        continuation_id=continuation_id,
        expected_revision=expected_revision,
        scope=AuthorizationScope.SINGLE,
        authorized_at=AUTHORIZED_AT,
    )


def _failed(revision: int) -> Failed:
    return Failed(
        workflow_id=_WORKFLOW_ID,
        revision=revision,
        code=FailureCode.CANCELLED,
        message="Cancelled by seller",
        recoverable=False,
    )


def _valid_edges() -> tuple[tuple[WorkflowState, WorkflowState], ...]:
    audit_ready = AuditReady(workflow_id=_WORKFLOW_ID, revision=0, audit=audit())
    approval = AwaitingApproval(
        workflow_id=_WORKFLOW_ID,
        revision=1,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        continuation_id=_APPROVAL_ID,
    )
    facts_from_audit = AwaitingFacts(
        workflow_id=_WORKFLOW_ID,
        revision=1,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        continuation_id=_FACTS_ID,
        questions=(_question(),),
    )
    facts_from_approval = facts_from_audit.model_copy(update={"revision": 2})
    authorized_from_approval = ContinuationAuthorized(
        workflow_id=_WORKFLOW_ID,
        revision=2,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=_authorization(_APPROVAL_ID, 1),
    )
    authorized_from_facts = authorized_from_approval.model_copy(
        update={"authorization": _authorization(_FACTS_ID, 1)}
    )
    generating = Generating(
        workflow_id=_WORKFLOW_ID,
        revision=3,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=authorized_from_approval.authorization,
    )
    facts_from_authorized = facts_from_audit.model_copy(update={"revision": 3})
    facts_from_generating = facts_from_audit.model_copy(update={"revision": 4})
    return (
        (audit_ready, approval),
        (audit_ready, facts_from_audit),
        (audit_ready, _failed(1)),
        (approval, authorized_from_approval),
        (approval, facts_from_approval),
        (approval, _failed(2)),
        (facts_from_audit, audit_ready.model_copy(update={"revision": 2})),
        (facts_from_audit, authorized_from_facts),
        (facts_from_audit, _failed(2)),
        (authorized_from_approval, generating),
        (authorized_from_approval, facts_from_authorized),
        (authorized_from_approval, _failed(3)),
        (
            generating,
            Completed(workflow_id=_WORKFLOW_ID, revision=4, deliverable=stage_two()),
        ),
        (generating, facts_from_generating),
        (generating, _failed(4)),
    )


def test_every_legal_workflow_edge_is_accepted() -> None:
    # Given: every edge in the canonical transition graph.
    edges = _valid_edges()

    # When: each pair crosses the transition boundary.
    transitions = tuple(
        WorkflowTransition(current=current, next=next_state) for current, next_state in edges
    )

    # Then: all legal revisions are accepted without an untyped fallback.
    assert len(transitions) == len(edges)


@pytest.mark.parametrize(
    ("continuation_id", "expected_revision"),
    [
        ("continuation:stale", 1),
        (_APPROVAL_ID, 0),
    ],
)
def test_stale_continuation_is_rejected_at_transition_boundary(
    continuation_id: str,
    expected_revision: int,
) -> None:
    # Given: approval state and a continuation bound to another token or revision.
    current = AwaitingApproval(
        workflow_id=_WORKFLOW_ID,
        revision=1,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        continuation_id=_APPROVAL_ID,
    )
    following = ContinuationAuthorized(
        workflow_id=_WORKFLOW_ID,
        revision=2,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=_authorization(continuation_id, expected_revision),
    )

    # When / Then: stale authorization cannot enter generation.
    with pytest.raises(ValidationError, match="stale_continuation"):
        _ = WorkflowTransition(current=current, next=following)


def test_cancelled_workflow_is_terminal_and_cannot_resume() -> None:
    # Given: a valid cancellation transition from a pending approval.
    current = AwaitingApproval(
        workflow_id=_WORKFLOW_ID,
        revision=1,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        continuation_id=_APPROVAL_ID,
    )
    cancelled = _failed(2)
    _ = WorkflowTransition(current=current, next=cancelled)
    resumed = ContinuationAuthorized(
        workflow_id=_WORKFLOW_ID,
        revision=3,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=_authorization(_APPROVAL_ID, 2),
    )

    # When / Then: terminal cancellation cannot be resumed with an old token.
    with pytest.raises(ValidationError, match="invalid_workflow_transition"):
        _ = WorkflowTransition(current=cancelled, next=resumed)


def test_repeated_interruption_requires_fresh_continuation_each_time() -> None:
    # Given: authorized generation interrupted by a targeted fact request twice.
    authorized = ContinuationAuthorized(
        workflow_id=_WORKFLOW_ID,
        revision=2,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=_authorization(_APPROVAL_ID, 1),
    )
    facts = AwaitingFacts(
        workflow_id=_WORKFLOW_ID,
        revision=3,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        continuation_id=_FACTS_ID,
        questions=(_question(),),
    )
    reauthorized = authorized.model_copy(
        update={
            "revision": 4,
            "authorization": _authorization(_FACTS_ID, 3),
        }
    )
    generating = Generating(
        workflow_id=_WORKFLOW_ID,
        revision=5,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=reauthorized.authorization,
    )
    interrupted_again = facts.model_copy(
        update={"revision": 6, "continuation_id": "continuation:facts:second"}
    )

    # When: the sequence crosses each explicit transition boundary.
    sequence = (
        WorkflowTransition(current=authorized, next=facts),
        WorkflowTransition(current=facts, next=reauthorized),
        WorkflowTransition(current=reauthorized, next=generating),
        WorkflowTransition(current=generating, next=interrupted_again),
    )

    # Then: every interruption remains visible and advances the revision once.
    assert tuple(item.next.revision for item in sequence) == (3, 4, 5, 6)


def test_completed_state_rejects_deliverable_that_does_not_match_generation_target() -> None:
    # Given: normal Stage 2 generation followed by a keyword-audit payload.
    authorization = _authorization(_APPROVAL_ID, 1)
    generating = Generating(
        workflow_id=_WORKFLOW_ID,
        revision=3,
        audit=audit(),
        target=DeliverableKind.NORMAL_STAGE_2,
        authorization=authorization,
    )
    misleading = Completed(
        workflow_id=_WORKFLOW_ID,
        revision=4,
        deliverable=KeywordAuditDeliverable(
            marketplace=CanonicalMarketplace.US,
            rows=(
                KeywordAuditEntry(
                    keyword="desk organizer",
                    required_locations=("title",),
                    observed_locations=("title",),
                    embedded=True,
                ),
            ),
            summary="Keyword audit complete",
        ),
    )

    # When / Then: the boundary rejects a false successful target.
    with pytest.raises(ValidationError, match="deliverable_kind_mismatch"):
        _ = WorkflowTransition(current=generating, next=misleading)


def test_stale_revision_and_illegal_skip_are_rejected() -> None:
    # Given: audit state and an attempted direct completion at a stale revision.
    current = AuditReady(workflow_id=_WORKFLOW_ID, revision=4, audit=audit())
    following = Completed(workflow_id=_WORKFLOW_ID, revision=4, deliverable=stage_two())

    # When / Then: revision checking rejects the pair before an illegal skip can land.
    with pytest.raises(ValidationError, match="stale_workflow_revision"):
        _ = WorkflowTransition(current=current, next=following)
