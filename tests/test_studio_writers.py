"""Tests for studio writer lanes — isolation, quorum, call counting."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from amazon_copy.agents.studio_writer import WriterQuorumError, generate_candidates
from amazon_copy.config import Settings
from amazon_copy.llm.mock import AsyncMockLLM
from amazon_copy.schemas.agents import CandidateArtifact, LaneResult


def _settings(**kwargs: object) -> Settings:
    kwargs.setdefault("MOCK", True)
    kwargs.setdefault("writer_model", "deepseek-chat")
    kwargs.setdefault("review_model", "deepseek-chat")
    kwargs.setdefault("vote_model", "deepseek-chat")
    return Settings.model_validate(kwargs)


class _FailingLLM:
    """Async mock that always raises on ``complete()``."""

    call_count = 0

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        self.call_count += 1
        msg = "LLM failure"
        raise RuntimeError(msg)


class TestGenerateCandidates:
    """``generate_candidates`` behaviour under success and partial failure."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_three_candidates_distinct_ids_and_lanes(self) -> None:
        """All three writers return valid artifacts with unique IDs and lanes."""
        results = await generate_candidates({"test": "data"}, _settings())
        assert len(results) == 3
        for r in results:
            assert isinstance(r, CandidateArtifact)
        ids = [r.candidate_id for r in results]
        assert len(set(ids)) == 3, f"expected 3 distinct IDs, got {ids}"
        lanes = [r.lane for r in results]
        assert len(set(lanes)) == 3, f"expected 3 distinct lanes, got {lanes}"

    @pytest.mark.asyncio
    async def test_call_count_all_three_succeed(self) -> None:
        """Each writer's LLM is called exactly once — 3 total."""
        seo = AsyncMockLLM("writer_seo")
        diff = AsyncMockLLM("writer_differentiation")
        clarity = AsyncMockLLM("writer_clarity")
        mapping = {"writer_seo": seo, "writer_differentiation": diff, "writer_clarity": clarity}

        def mock_get(role: str, **kwargs: object) -> AsyncMockLLM:
            return mapping[role]

        with patch("amazon_copy.agents.studio_writer.get_async_llm", mock_get):
            results = await generate_candidates({"x": 1}, _settings())

        assert len(results) == 3
        assert seo.call_count == 1
        assert diff.call_count == 1
        assert clarity.call_count == 1
        assert seo.call_count + diff.call_count + clarity.call_count == 3

    # ------------------------------------------------------------------
    # Partial failure — quorum survives
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_one_bad_llm_still_yields_two_candidates(self) -> None:
        """A single failing lane does not cancel its siblings (quorum met)."""
        seo = AsyncMockLLM("writer_seo")
        diff = AsyncMockLLM("writer_differentiation")
        failing = _FailingLLM()
        mapping = {"writer_seo": seo, "writer_differentiation": diff, "writer_clarity": failing}

        def mock_get(role: str, **kwargs: object) -> AsyncMockLLM | _FailingLLM:
            return mapping[role]

        with patch("amazon_copy.agents.studio_writer.get_async_llm", mock_get):
            results = await generate_candidates({"x": 1}, _settings())

        assert len(results) == 3
        artifacts = [r for r in results if isinstance(r, CandidateArtifact)]
        lane_errors = [r for r in results if isinstance(r, LaneResult)]
        assert len(artifacts) == 2, f"expected 2 artifacts, got {len(artifacts)}"
        assert len(lane_errors) == 1, f"expected 1 lane error, got {len(lane_errors)}"
        assert lane_errors[0].error is not None
        assert "LLM failure" in lane_errors[0].error

    # ------------------------------------------------------------------
    # Quorum failure
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_two_bad_triggers_quorum_failure(self) -> None:
        """Two failed lanes raise WriterQuorumError (successes < 2)."""
        seo = AsyncMockLLM("writer_seo")
        fail1 = _FailingLLM()
        fail2 = _FailingLLM()
        mapping = {"writer_seo": seo, "writer_differentiation": fail1, "writer_clarity": fail2}

        def mock_get(role: str, **kwargs: object) -> AsyncMockLLM | _FailingLLM:
            return mapping[role]

        with (
            pytest.raises(WriterQuorumError, match="quorum"),
            patch("amazon_copy.agents.studio_writer.get_async_llm", mock_get),
        ):
            await generate_candidates({"x": 1}, _settings())

    # ------------------------------------------------------------------
    # All fail — still quorum failure
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_three_bad_triggers_quorum_failure(self) -> None:
        """All three failing also raises WriterQuorumError."""
        fail1 = _FailingLLM()
        fail2 = _FailingLLM()
        fail3 = _FailingLLM()
        mapping = {
            "writer_seo": fail1,
            "writer_differentiation": fail2,
            "writer_clarity": fail3,
        }

        def mock_get(role: str, **kwargs: object) -> _FailingLLM:
            return mapping[role]

        with (
            pytest.raises(WriterQuorumError, match="quorum"),
            patch("amazon_copy.agents.studio_writer.get_async_llm", mock_get),
        ):
            await generate_candidates({"x": 1}, _settings())
