"""Studio pipeline orchestrator — pure async six-stage topology.

Topology
--------
1. research   → run_research_lanes (MCP provider, 5 concurrent lanes)
2. writers    → generate_candidates (3 parallel LLM lanes: SEO, diff, clarity)
3. critique   → critique_and_revise (ring critique + revision)
4. gates      → filter_eligible (hard-gate checks, no I/O)
5. judges     → run_judges (dual-judge anonymised ranking)
6. integrate  → integrate (first-eligible selection)

All stages execute via plain ``asyncio`` — no LangGraph dependency.  Each
stage is optional given earlier failures; the state object tracks the exact
cut point.

Usage
-----
    state = await run_studio_pipeline("USB-C Hub 7-in-1")
    assert state.outcome in ("success", "no_winner")
"""

from __future__ import annotations

import uuid
from dataclasses import replace as replace_state
from typing import TYPE_CHECKING, Any

import amazon_copy.config as config_module
from amazon_copy.agents.critique import critique_and_revise
from amazon_copy.agents.hard_gates import filter_eligible
from amazon_copy.agents.integrator import integrate
from amazon_copy.agents.judging import NoEligibleError, run_judges
from amazon_copy.agents.mcp_research import ResearchBundle, run_research_lanes
from amazon_copy.agents.studio_writer import WriterQuorumError, generate_candidates
from amazon_copy.config import Settings
from amazon_copy.mcp.protocol import ALL_ROLES
from amazon_copy.orchestrator.state import StudioState
from amazon_copy.schemas.agents import CandidateArtifact

if TYPE_CHECKING:
    from amazon_copy.mcp.protocol import ResearchProvider
    from amazon_copy.orchestrator.budgets import BudgetLedger


# ── Helpers ────────────────────────────────────────────────────────────────


def _bundle_to_snapshot(bundle: ResearchBundle) -> dict[str, Any]:
    """Convert a ResearchBundle into a plain dict for the writer lanes.

    Extracts structured claim data from every successful lane so the three
    writer roles can use it as their evidence context.
    """
    lanes_raw: dict[str, Any] = {}
    for role in ALL_ROLES:
        outcome = bundle.lanes.get(role)
        if outcome is not None and outcome.status == "success" and outcome.result is not None:
            lanes_raw[role] = {
                "claims": [
                    {
                        "key": c.key,
                        "value": c.value,
                        "authority": c.authority,
                        "confidence": c.confidence,
                        "content_hash": c.content_hash,
                    }
                    for c in outcome.result.claims
                ],
                "fixture": outcome.result.fixture,
            }

    return {
        "mode": bundle.mode,
        "claim_ids": bundle.claim_ids,
        "gaps": bundle.gaps,
        "lanes": lanes_raw,
    }


def _pick_outcome(
    winner: object | None,
    current_outcome: str,
    research_mode: str,
) -> str:
    """Determine the final outcome string."""
    if winner is not None:
        return "success"
    if current_outcome == "no_winner":
        return "no_winner"
    if research_mode == "source_only":
        return "degraded"
    # Preserve whatever was set (failure, degraded, etc.)
    return current_outcome


# ── Public API ─────────────────────────────────────────────────────────────


async def run_studio_pipeline(
    request_text: str,
    *,
    settings: Settings | None = None,
    provider: ResearchProvider | None = None,
    budget: BudgetLedger | None = None,
) -> StudioState:
    """Execute the full six-stage studio pipeline and return the final state.

    Parameters
    ----------
    request_text:
        Raw user request (product description, title, etc.).
    settings:
        Application settings.  Defaults to ``Settings()`` from env when
        ``None``.  Pass ``Settings(MOCK=True)`` explicitly for offline fixtures.
    provider:
        MCP research provider.  When ``None`` **and** ``settings.mock`` is
        ``True``, a :func:`~amazon_copy.mcp.fixture_server.build_fixture_provider`
        is created automatically.  When ``None`` and not mock, research runs
        in ``source_only`` mode (no lanes).
    budget:
        Optional :class:`BudgetLedger` to cap MCP calls.  Passed through to
        ``run_research_lanes``; writer/judge/integrate stages do not charge
        MCP budget.

    Returns
    -------
    StudioState
        A frozen snapshot of the entire pipeline run.  Check ``.outcome``
        for the overall result: ``"success"``, ``"degraded"``,
        ``"no_winner"``, or ``"failure"``.
    """
    # ── Default: load env; offline tests must pass Settings(MOCK=True) ────
    if settings is None:
        settings = Settings()
        config_module.apply_runtime_settings(settings)

    run_id = uuid.uuid4().hex[:12]
    state = StudioState(request_text=request_text, run_id=run_id)
    llm_count = 0
    mcp_count = 0

    try:
        # ── 1. Research — MCP lanes ──────────────────────────────────────
        resolved_provider = provider
        if resolved_provider is None and settings.mock:
            from amazon_copy.mcp.fixture_server import build_fixture_provider

            resolved_provider = build_fixture_provider("fresh")

        bundle = await run_research_lanes(
            request_text,
            resolved_provider,
            budget=budget,
        )
        evidence = _bundle_to_snapshot(bundle)
        mcp_count = len(bundle.lanes)

        if budget is not None:
            snap = await budget.snapshot()
            mcp_count = snap.mcp_calls

        state = replace_state(state, research=bundle, mcp_calls=mcp_count)

        # ── 2. Writers — 3 parallel LLM lanes ───────────────────────────
        raw_candidates = await generate_candidates(evidence, settings)
        candidates: list[CandidateArtifact] = [
            c for c in raw_candidates if isinstance(c, CandidateArtifact)
        ]
        llm_count += 3  # one LLM call per writer lane
        state = replace_state(state, candidates=candidates, llm_calls=llm_count)

        # ── 3. Critique & revise — ring topology ────────────────────────
        if candidates:
            revised = await critique_and_revise(candidates, settings)
            # critique: 1 LLM per edge (3 for 3 candidates)
            # revision: 1 LLM per target (3 for 3 targets)
            llm_count += len(candidates) + len(revised)
        else:
            revised = []
        state = replace_state(state, revised=revised, llm_calls=llm_count)

        # ── 4. Hard gates — deterministic, no I/O ───────────────────────
        eligible = filter_eligible(revised)
        state = replace_state(state, eligible=eligible)

        # ── 5. Judges — dual-judge ranking ──────────────────────────────
        if eligible:
            ranking = await run_judges(eligible, run_id, settings)
            llm_count += 2  # two judge LLM calls
            state = replace_state(state, ranking=ranking, llm_calls=llm_count)
        else:
            state = replace_state(state, outcome="no_winner")

        # ── 6. Integrate — first-eligible selection ─────────────────────
        if state.ranking is not None:
            winner, trace = await integrate(
                state.ranking,
                eligible,
                settings,
            )
            state = replace_state(state, winner=winner, trace=trace)

        # ── 7. Final outcome ────────────────────────────────────────────
        research_mode = getattr(bundle, "mode", "source_only")
        outcome = _pick_outcome(state.winner, state.outcome, research_mode)
        state = replace_state(state, outcome=outcome)  # type: ignore[arg-type]

    except WriterQuorumError:
        state = replace_state(
            state,
            outcome="failure",
            errors=["No writer quorum — fewer than 2 lanes succeeded"],
        )
    except NoEligibleError:
        state = replace_state(state, outcome="no_winner")
    except Exception as exc:
        state = replace_state(
            state,
            outcome="failure",
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    return state
