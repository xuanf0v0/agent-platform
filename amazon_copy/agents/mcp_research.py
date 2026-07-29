"""Multi-agent MCP research lane orchestration (Task 13).

Runs five concurrent research lanes (product, keyword, competitor, policy,
shopper) over an :class:`ResearchProvider`, charges MCP budget when a
:class:`BudgetLedger` is provided, and produces a :class:`ResearchBundle`
with a quorum-based completion mode.

Usage::

    bundle = await run_research_lanes("USB-C Hub", provider)
    # bundle.mode == "complete" | "degraded" | "source_only"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import anyio

from amazon_copy.mcp.protocol import ALL_ROLES, ResearchError, ResearchRole
from amazon_copy.orchestrator.research_nodes import (
    LaneOutcome,
    build_queries,
    has_competitor_signal,
    normalize_result,
)

if TYPE_CHECKING:
    from amazon_copy.mcp.protocol import ResearchProvider
    from amazon_copy.orchestrator.budgets import BudgetLedger

# ── Types ────────────────────────────────────────────────────────────────

ResearchMode = Literal["complete", "degraded", "source_only"]


@dataclass(frozen=True, slots=True)
class ResearchBundle:
    """The aggregated output of running all five MCP research lanes.

    Attributes:
        lanes: Per-role outcomes, keyed by :class:`ResearchRole`.
        mode: Aggregate completion mode determined by quorum rules.
        claim_ids: Flat deduplicated list of all claim keys gathered.
        gaps: Roles that failed (neither succeeded nor not_applicable).
    """

    lanes: dict[ResearchRole, LaneOutcome]
    mode: ResearchMode
    claim_ids: list[str]
    gaps: list[str]


# ── Public API ───────────────────────────────────────────────────────────


async def run_research_lanes(
    request: str | object,
    provider: ResearchProvider | None,
    budget: BudgetLedger | None = None,
) -> ResearchBundle:
    """Run all five MCP research lanes concurrently and return a bundle.

    Args:
        request: Either a raw text string or a :class:`StudioRequest`.
        provider: An MCP :class:`ResearchProvider`, or ``None`` to get
            ``source_only`` mode immediately without calling any lanes.
        budget: Optional :class:`BudgetLedger` — when provided, each
            lane call charges one MCP budget reservation.

    Returns:
        A :class:`ResearchBundle` with per-role outcomes and an aggregate
        mode determined by quorum:

        * ``complete`` — product, policy, **and** (keyword or shopper)
          all succeeded.  Competitor may be ``not_applicable``.
        * ``degraded`` — one or more required roles failed, but the
          provider was reachable.
        * ``source_only`` — provider was ``None``; no lanes were run.
    """
    # ── Source-only fast path ────────────────────────────────────────
    if provider is None:
        return ResearchBundle(
            lanes={},
            mode="source_only",
            claim_ids=[],
            gaps=sorted(ALL_ROLES),
        )

    queries = build_queries(request)
    outcomes: dict[ResearchRole, LaneOutcome] = {}
    lock = anyio.Lock()

    async with provider.open_session() as session, anyio.create_task_group() as tg:
        for role in ALL_ROLES:
            tg.start_soon(
                _run_one_lane,
                session,
                queries[role],
                role,
                budget,
                request,
                outcomes,
                lock,
            )

    return _build_bundle(outcomes)


# ── Internal helpers ─────────────────────────────────────────────────────


async def _run_one_lane(  # noqa: PLR0913 — internal dispatcher, 7 args is acceptable
    session: object,
    query: object,
    role: ResearchRole,
    budget: BudgetLedger | None,
    request: str | object,
    outcomes: dict[ResearchRole, LaneOutcome],
    lock: anyio.Lock,
) -> None:
    """Execute one MCP research lane and store the outcome."""
    # ── Competitor not_applicable fast path ──────────────────────
    if role == "competitor" and not has_competitor_signal(request):
        async with lock:
            outcomes[role] = LaneOutcome(role=role, status="not_applicable")
        return

    # ── Budget charge ────────────────────────────────────────────
    if budget is not None:
        from amazon_copy.orchestrator.budgets import BudgetResource  # noqa: PLC0415

        reservation = await budget.reserve(BudgetResource.MCP)
        if reservation.status != "reserved":
            async with lock:
                outcomes[role] = LaneOutcome(
                    role=role,
                    status="failed",
                    error=f"budget:{reservation.status}",
                )
            return

    # ── Execute the call ─────────────────────────────────────────
    try:
        result = await session.call(query)  # type: ignore[union-attr]
        normalized = normalize_result(result)
        async with lock:
            outcomes[role] = LaneOutcome(
                role=role,
                status="success",
                result=normalized,
            )
    except ResearchError as exc:
        async with lock:
            outcomes[role] = LaneOutcome(
                role=role,
                status="failed",
                error=f"{exc.code}: {exc.message}",
            )
    except Exception as exc:  # noqa: BLE001
        async with lock:
            outcomes[role] = LaneOutcome(
                role=role,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )


def _build_bundle(outcomes: dict[ResearchRole, LaneOutcome]) -> ResearchBundle:
    """Aggregate lane outcomes into a :class:`ResearchBundle` with quorum."""
    claim_ids: list[str] = []
    gaps: list[str] = []

    for role in ALL_ROLES:
        lane = outcomes.get(role)
        if lane is None or lane.status == "failed":
            gaps.append(role)
        elif lane.status == "success" and lane.result is not None:
            claim_ids.extend(c.key for c in lane.result.claims if c.key)

    # ── Determine mode by quorum ─────────────────────────────────
    succeeded = {r for r, o in outcomes.items() if o.status == "success"}
    has_product = "product" in succeeded
    has_policy = "policy" in succeeded
    has_keyword = "keyword" in succeeded
    has_shopper = "shopper" in succeeded

    if has_product and has_policy and (has_keyword or has_shopper):
        mode: ResearchMode = "complete"
    elif not outcomes:
        mode = "source_only"
    else:
        mode = "degraded"

    return ResearchBundle(
        lanes=outcomes,
        mode=mode,
        claim_ids=sorted(set(claim_ids)),
        gaps=sorted(set(gaps)),
    )
