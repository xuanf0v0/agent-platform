from __future__ import annotations

import pytest

from amazon_copy import StudioService, StudioState
from amazon_copy.config import Settings


def _mock_service() -> StudioService:
    return StudioService(settings=Settings(MOCK=True))


class TestStudioE2E:
    def test_mock_optimize_returns_state(self) -> None:
        service = _mock_service()
        state = service.optimize_listing(
            "Title: Insulated Water Bottle\n1. Keeps drinks cold\n2. BPA free"
        )
        assert isinstance(state, StudioState)
        assert state.outcome in ("success", "degraded", "no_winner", "failure")
        assert getattr(state, "llm_calls", 0) <= 12
        assert getattr(state, "mcp_calls", 0) <= 20

    def test_repeat_call_independent(self) -> None:
        service = _mock_service()
        a = service.optimize_listing("Bottle")
        b = service.optimize_listing("Bottle")
        assert isinstance(a, StudioState)
        assert isinstance(b, StudioState)
        if a.run_id and b.run_id:
            assert a.run_id != b.run_id

    def test_minimal_text_does_not_raise(self) -> None:
        service = _mock_service()
        state = service.optimize_listing("x")
        assert isinstance(state, StudioState)
        assert state.outcome in ("success", "degraded", "no_winner", "failure")
