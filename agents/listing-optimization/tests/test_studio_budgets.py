from __future__ import annotations

import json
from typing import final

import anyio
import pytest
from amazon_copy.orchestrator.budgets import (
    BudgetExhausted,
    BudgetLedger,
    BudgetLimits,
    BudgetSnapshot,
    DeadlineExceeded,
    ReservationGranted,
    ReservationOutcome,
)
from pydantic import ValidationError


@final
class _FakeClock:
    __slots__ = ("_now",)

    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _ProviderError(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_concurrent_reservations_never_exceed_separate_caps() -> None:
    # Given
    ledger = BudgetLedger()
    llm_outcomes: list[ReservationOutcome] = []
    mcp_outcomes: list[ReservationOutcome] = []

    async def reserve_llm() -> None:
        llm_outcomes.append(await ledger.reserve_llm())

    async def reserve_mcp() -> None:
        mcp_outcomes.append(await ledger.reserve_mcp())

    # When
    async with anyio.create_task_group() as task_group:
        for _ in range(13):
            _ = task_group.start_soon(reserve_llm)
        for _ in range(21):
            _ = task_group.start_soon(reserve_mcp)

    # Then
    accepted = (
        sum(isinstance(outcome, ReservationGranted) for outcome in llm_outcomes),
        sum(isinstance(outcome, ReservationGranted) for outcome in mcp_outcomes),
    )
    assert accepted == (12, 20)
    assert sum(isinstance(outcome, BudgetExhausted) for outcome in llm_outcomes) == 1
    assert sum(isinstance(outcome, BudgetExhausted) for outcome in mcp_outcomes) == 1


@pytest.mark.asyncio
async def test_failed_provider_attempt_remains_charged() -> None:
    # Given
    ledger = BudgetLedger(BudgetLimits(max_llm_calls=1))

    async def failing_provider() -> None:
        raise _ProviderError

    # When
    reservation = await ledger.reserve_llm()
    with pytest.raises(_ProviderError):
        await failing_provider()
    second = await ledger.reserve_llm()

    # Then
    assert isinstance(reservation, ReservationGranted)
    assert isinstance(second, BudgetExhausted)
    assert (await ledger.snapshot()).llm_calls == 1


@pytest.mark.asyncio
async def test_deadline_rejection_does_not_charge_or_invoke_provider() -> None:
    # Given
    clock = _FakeClock(40.0)
    ledger = BudgetLedger(BudgetLimits(run_deadline_seconds=120.0), clock=clock)
    snapshot = await ledger.snapshot()
    clock.advance(121.0)
    restored = BudgetLedger.from_snapshot(snapshot, clock=clock)
    provider_calls = 0

    # When
    outcome = await restored.reserve_llm()
    if isinstance(outcome, ReservationGranted):
        provider_calls += 1

    # Then
    assert isinstance(outcome, DeadlineExceeded)
    assert outcome.status == "deadline_exceeded"
    assert provider_calls == 0
    assert (await restored.snapshot()).llm_calls == 0


@pytest.mark.asyncio
async def test_resume_restores_counts_and_original_deadline() -> None:
    # Given
    clock = _FakeClock(10.0)
    ledger = BudgetLedger(clock=clock)
    _ = await ledger.reserve_llm()
    _ = await ledger.reserve_mcp()
    original = await ledger.snapshot()
    clock.advance(25.0)

    # When
    restored = BudgetLedger.from_snapshot(original, clock=clock)
    restored_snapshot = await restored.snapshot()

    # Then
    assert restored_snapshot == original
    assert restored.deadline == 130.0
    assert restored.remaining_timeout() == 95.0


@pytest.mark.asyncio
async def test_reservation_reports_non_negative_remaining_timeout() -> None:
    # Given
    clock = _FakeClock(5.0)
    ledger = BudgetLedger(BudgetLimits(run_deadline_seconds=10.0), clock=clock)
    clock.advance(3.5)

    # When
    outcome = await ledger.reserve_mcp()
    clock.advance(20.0)

    # Then
    assert isinstance(outcome, ReservationGranted)
    assert outcome.remaining_seconds == 6.5
    assert ledger.remaining_timeout() == 0.0


@pytest.mark.asyncio
async def test_repeated_cancelled_reservations_remain_cancelled_and_uncharged() -> None:
    # Given
    ledger = BudgetLedger()
    cancellations: list[bool] = []

    # When
    for _ in range(2):
        with anyio.CancelScope() as cancel_scope:
            cancel_scope.cancel()
            _ = await ledger.reserve_llm()
        cancellations.append(cancel_scope.cancelled_caught)

    # Then
    assert cancellations == [True, True]
    assert (await ledger.snapshot()).llm_calls == 0


def test_negative_caps_and_non_finite_duration_are_rejected() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        _ = BudgetLimits(max_llm_calls=0)
    with pytest.raises(ValidationError):
        _ = BudgetLimits(max_mcp_calls=-1)
    with pytest.raises(ValidationError):
        _ = BudgetLimits(run_deadline_seconds=float("nan"))


def test_snapshot_rejects_over_cap_counts() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match="llm_calls 13 exceeds cap 12"):
        _ = BudgetSnapshot(
            max_llm_calls=12,
            max_mcp_calls=20,
            run_deadline_seconds=120.0,
            llm_calls=13,
            mcp_calls=0,
            deadline=120.0,
        )


@pytest.mark.asyncio
async def test_snapshot_is_json_safe_and_contains_only_budget_metadata() -> None:
    # Given
    ledger = BudgetLedger()
    _ = await ledger.reserve_llm()

    # When
    checkpoint = (await ledger.snapshot()).model_dump(mode="json")
    encoded = json.dumps(checkpoint)

    # Then
    assert json.loads(encoded) == checkpoint
    assert set(checkpoint) == {
        "schema_version",
        "max_llm_calls",
        "max_mcp_calls",
        "run_deadline_seconds",
        "llm_calls",
        "mcp_calls",
        "deadline",
    }
