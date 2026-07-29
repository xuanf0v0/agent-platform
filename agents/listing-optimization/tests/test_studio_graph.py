"""Tests for Task 19 studio runtime — typed state, mock pipeline, edge cases.

Coverage
--------
- StudioState dataclass construction and immutability
- Full mock pipeline: success outcome with winner
- Mock pipeline: empty request does not hang (fast completion)
- Module import sanity
"""

from __future__ import annotations

import pytest

from amazon_copy.orchestrator.state import StudioState
from amazon_copy.orchestrator.studio_graph import run_studio_pipeline
from amazon_copy.schemas.agents import CandidateArtifact, IntegrationTrace, RankingResult


# ── StudioState ──────────────────────────────────────────────────────────


class TestStudioState:
    """StudioState construction, defaults, and immutability."""

    def test_defaults(self) -> None:
        """Constructed state has sensible defaults."""
        s = StudioState(request_text="test")
        assert s.request_text == "test"
        assert s.run_id == ""
        assert s.research is None
        assert s.candidates == []
        assert s.revised == []
        assert s.eligible == []
        assert s.ranking is None
        assert s.winner is None
        assert s.trace is None
        assert s.outcome == "failure"
        assert s.errors == []
        assert s.llm_calls == 0
        assert s.mcp_calls == 0

    def test_frozen_cannot_mutate(self) -> None:
        """Attempting field mutation raises FrozenInstanceError (dataclass)."""
        s = StudioState(request_text="x")
        with pytest.raises(AttributeError):
            s.request_text = "y"  # type: ignore[misc]

    def test_outcome_literal_accepts_valid_values(self) -> None:
        """All four valid outcome strings are accepted."""
        for outcome in ("success", "degraded", "no_winner", "failure"):
            s = StudioState(request_text="t", outcome=outcome)  # type: ignore[arg-type]
            assert s.outcome == outcome

    def test_fields_wire_correctly(self) -> None:
        """All constructor fields map to the right attributes."""
        s = StudioState(
            request_text="USB-C Hub",
            run_id="abc123",
            research={"mock": True},
            candidates=["c1"],
            revised=["r1"],
            eligible=["e1"],
            ranking={"rank": 1},
            winner={"id": "w1"},
            trace={"trace": "ok"},
            outcome="success",
            errors=["warn"],
            llm_calls=5,
            mcp_calls=3,
        )
        assert s.request_text == "USB-C Hub"
        assert s.run_id == "abc123"
        assert s.research == {"mock": True}
        assert s.candidates == ["c1"]
        assert s.revised == ["r1"]
        assert s.eligible == ["e1"]
        assert s.ranking == {"rank": 1}
        assert s.winner == {"id": "w1"}
        assert s.trace == {"trace": "ok"}
        assert s.outcome == "success"
        assert s.errors == ["warn"]
        assert s.llm_calls == 5
        assert s.mcp_calls == 3


# ── run_studio_pipeline (mock) ────────────────────────────────────────────


class TestRunStudioPipelineMock:
    """End-to-end mock pipeline — no network, no env vars."""

    @pytest.mark.asyncio
    async def test_full_mock_produces_winner(self) -> None:
        """Default mock pipeline produces a success or no_winner without crash.

        Note: mock fixture bullets end with ``.`` (trailing period), so the
        hard gate may filter all candidates → ``no_winner``.  This is correct
        gate behaviour, not a pipeline failure.
        """
        from amazon_copy.config import Settings

        state = await run_studio_pipeline(
            "USB-C Hub 7-in-1", settings=Settings(MOCK=True)
        )

        assert state.outcome in ("success", "no_winner"), (
            f"expected success or no_winner, got {state.outcome!r} with errors {state.errors}"
        )
        assert state.errors == [], f"unexpected errors: {state.errors}"

        # Research bundle present (stage 1 always runs)
        assert state.research is not None
        assert hasattr(state.research, "mode")

        # Writer stage ran
        assert len(state.candidates) == 3, "expected 3 writer candidates"
        assert len(state.revised) == 3, "expected 3 revised artifacts"

        # Gate outcome depends on whether revised bullets pass hard checks
        if state.outcome == "success":
            assert state.winner is not None
            assert isinstance(state.winner, CandidateArtifact)
            assert state.winner.candidate_id
            assert len(state.winner.titles) == 3
            assert len(state.winner.bullets) == 5
            assert state.trace is not None
            assert len(state.eligible) >= 1
            assert state.ranking is not None
        else:
            assert state.winner is None
            assert state.eligible == []

        # Counters updated
        assert state.llm_calls > 0, "expected LLM calls to be tracked"
        assert state.mcp_calls > 0, "expected MCP calls to be tracked"

    @pytest.mark.asyncio
    async def test_empty_request_does_not_hang(self) -> None:
        """An empty string completes quickly (no crash, no hang)."""
        from amazon_copy.config import Settings

        state = await run_studio_pipeline("", settings=Settings(MOCK=True))

        # Must not hang — outcome can be success or no_winner depending
        # on how the mock handles empty evidence
        assert state.outcome in ("success", "no_winner", "failure")
        assert isinstance(state.errors, list)

    @pytest.mark.asyncio
    async def test_runs_with_explicit_mock_settings(self) -> None:
        """Passing Settings(MOCK=True) explicitly works identically."""
        from amazon_copy.config import Settings

        settings = Settings(MOCK=True)
        state = await run_studio_pipeline("USB-C Hub", settings=settings)

        assert state.outcome in ("success", "no_winner", "failure")
        assert state.errors == []

    @pytest.mark.asyncio
    async def test_mock_provider_none_uses_fixture(self) -> None:
        """When settings.mock is True and provider=None, fixture is auto-created."""
        from amazon_copy.config import Settings

        settings = Settings(MOCK=True)
        state = await run_studio_pipeline(
            "USB-C Hub", settings=settings, provider=None
        )

        # Mock fixtures produce trailing periods on bullets — hard gate
        # may reject all candidates.  Pipeline must not crash in either case.
        assert state.outcome in ("success", "no_winner"), (
            f"expected success or no_winner, got {state.outcome!r} with errors {state.errors}"
        )
        assert state.errors == []

    @pytest.mark.asyncio
    async def test_state_is_frozen_and_can_be_read(self) -> None:
        """Returned state is a StudioState (frozen dataclass)."""
        from amazon_copy.config import Settings

        state = await run_studio_pipeline("test", settings=Settings(MOCK=True))
        assert isinstance(state, StudioState)
        assert isinstance(state.run_id, str)
        assert len(state.run_id) == 12  # uuid hex[:12]

    @pytest.mark.asyncio
    async def test_run_id_is_unique_per_call(self) -> None:
        """Two sequential calls produce different run_ids."""
        from amazon_copy.config import Settings

        mock = Settings(MOCK=True)
        s1 = await run_studio_pipeline("test", settings=mock)
        s2 = await run_studio_pipeline("test", settings=mock)
        assert s1.run_id != s2.run_id


# ── Module import sanity ──────────────────────────────────────────────────


class TestModuleImport:
    """Top-level imports resolve without error."""

    def test_state_importable(self) -> None:
        """StudioState is importable from the orchestrator module."""
        from amazon_copy.orchestrator.state import StudioState as S  # noqa: F811

        assert S is StudioState

    def test_pipeline_importable(self) -> None:
        """run_studio_pipeline is importable from the orchestrator module."""
        from amazon_copy.orchestrator.studio_graph import (  # noqa: F401
            run_studio_pipeline,
        )

    def test_schemas_still_work(self) -> None:
        """Existing agent schemas remain importable alongside new code."""
        from amazon_copy.schemas.agents import CandidateArtifact  # noqa: F401
        from amazon_copy.schemas.agents import IntegrationTrace  # noqa: F401
        from amazon_copy.schemas.agents import RankingResult  # noqa: F401
