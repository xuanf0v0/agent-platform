"""Shared attempted-call and deadline budgets for Studio runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import ClassVar, Final, Literal, Self, final

import anyio
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

MonotonicClock = Callable[[], float]
_SNAPSHOT_LIMIT_ERROR: Final = "budget_snapshot_limit"
_SNAPSHOT_LIMIT_MESSAGE: Final = "{resource}_calls {used} exceeds cap {limit}"


class BudgetResource(StrEnum):
    """Provider resource with an independently enforced attempted-call cap."""

    LLM = "llm"
    MCP = "mcp"


class BudgetLimits(BaseModel):
    """Immutable attempted-call caps and run duration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_llm_calls: int = Field(default=12, ge=1)
    max_mcp_calls: int = Field(default=20, ge=1)
    run_deadline_seconds: float = Field(default=120.0, gt=0.0, allow_inf_nan=False)


DEFAULT_BUDGET_LIMITS: Final = BudgetLimits()


class BudgetSnapshot(BaseModel):
    """Redacted primitive-only checkpoint state for one budget ledger."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    max_llm_calls: int = Field(ge=1)
    max_mcp_calls: int = Field(ge=1)
    run_deadline_seconds: float = Field(gt=0.0, allow_inf_nan=False)
    llm_calls: int = Field(ge=0)
    mcp_calls: int = Field(ge=0)
    deadline: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def counts_within_limits(self) -> Self:
        """Reject restored counters that exceed their immutable caps."""
        if self.llm_calls > self.max_llm_calls:
            raise PydanticCustomError(
                _SNAPSHOT_LIMIT_ERROR,
                _SNAPSHOT_LIMIT_MESSAGE,
                {
                    "resource": BudgetResource.LLM.value,
                    "used": self.llm_calls,
                    "limit": self.max_llm_calls,
                },
            )
        if self.mcp_calls > self.max_mcp_calls:
            raise PydanticCustomError(
                _SNAPSHOT_LIMIT_ERROR,
                _SNAPSHOT_LIMIT_MESSAGE,
                {
                    "resource": BudgetResource.MCP.value,
                    "used": self.mcp_calls,
                    "limit": self.max_mcp_calls,
                },
            )
        return self


@dataclass(frozen=True, slots=True)
class ReservationGranted:
    """Successful attempted-call reservation."""

    resource: BudgetResource
    attempt_number: int
    remaining_seconds: float
    status: Literal["reserved"] = field(default="reserved", init=False)


@dataclass(frozen=True, slots=True)
class BudgetExhausted:
    """Typed rejection when a resource's attempted-call cap is already used."""

    resource: BudgetResource
    used: int
    limit: int
    status: Literal["budget_exhausted"] = field(default="budget_exhausted", init=False)


@dataclass(frozen=True, slots=True)
class DeadlineExceeded:
    """Typed rejection when the shared monotonic deadline has elapsed."""

    resource: BudgetResource
    deadline: float
    now: float
    remaining_seconds: float = field(default=0.0, init=False)
    status: Literal["deadline_exceeded"] = field(default="deadline_exceeded", init=False)


ReservationOutcome = ReservationGranted | BudgetExhausted | DeadlineExceeded


@final
class BudgetLedger:
    """Reserve shared provider attempts for one Studio run."""

    __slots__ = ("_calls", "_clock", "_deadline", "_limits", "_lock")

    def __init__(
        self,
        limits: BudgetLimits = DEFAULT_BUDGET_LIMITS,
        *,
        clock: MonotonicClock = monotonic,
    ) -> None:
        """Start empty counters with one immutable monotonic deadline."""
        self._limits = limits
        self._clock = clock
        self._deadline = clock() + limits.run_deadline_seconds
        self._calls: dict[BudgetResource, int] = {
            BudgetResource.LLM: 0,
            BudgetResource.MCP: 0,
        }
        self._lock = anyio.Lock()

    @property
    def deadline(self) -> float:
        """Return the immutable absolute monotonic deadline."""
        return self._deadline

    @property
    def limits(self) -> BudgetLimits:
        """Return the immutable caps and run duration."""
        return self._limits

    def remaining_timeout(self) -> float:
        """Return the non-negative provider timeout available now."""
        return max(0.0, self._deadline - self._clock())

    async def reserve(self, resource: BudgetResource) -> ReservationOutcome:
        """Atomically charge one provider attempt or return a typed rejection."""
        async with self._lock:
            now = self._clock()
            remaining_seconds = max(0.0, self._deadline - now)
            if remaining_seconds <= 0.0:
                return DeadlineExceeded(resource=resource, deadline=self._deadline, now=now)

            limits = {
                BudgetResource.LLM: self._limits.max_llm_calls,
                BudgetResource.MCP: self._limits.max_mcp_calls,
            }
            used = self._calls[resource]
            limit = limits[resource]
            if used >= limit:
                return BudgetExhausted(resource=resource, used=used, limit=limit)

            attempt_number = used + 1
            self._calls[resource] = attempt_number
            return ReservationGranted(
                resource=resource,
                attempt_number=attempt_number,
                remaining_seconds=remaining_seconds,
            )

    async def reserve_llm(self) -> ReservationOutcome:
        """Reserve one LLM attempt."""
        return await self.reserve(BudgetResource.LLM)

    async def reserve_mcp(self) -> ReservationOutcome:
        """Reserve one MCP attempt."""
        return await self.reserve(BudgetResource.MCP)

    async def snapshot(self) -> BudgetSnapshot:
        """Capture an atomic redacted checkpoint without locks or provider data."""
        async with self._lock:
            return BudgetSnapshot(
                max_llm_calls=self._limits.max_llm_calls,
                max_mcp_calls=self._limits.max_mcp_calls,
                run_deadline_seconds=self._limits.run_deadline_seconds,
                llm_calls=self._calls[BudgetResource.LLM],
                mcp_calls=self._calls[BudgetResource.MCP],
                deadline=self._deadline,
            )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: BudgetSnapshot,
        *,
        clock: MonotonicClock = monotonic,
    ) -> BudgetLedger:
        """Restore counts and the original absolute deadline from a checkpoint."""
        ledger = cls(
            BudgetLimits(
                max_llm_calls=snapshot.max_llm_calls,
                max_mcp_calls=snapshot.max_mcp_calls,
                run_deadline_seconds=snapshot.run_deadline_seconds,
            ),
            clock=clock,
        )
        ledger._deadline = snapshot.deadline
        ledger._calls[BudgetResource.LLM] = snapshot.llm_calls
        ledger._calls[BudgetResource.MCP] = snapshot.mcp_calls
        return ledger
