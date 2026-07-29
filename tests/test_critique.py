"""Tests for critique ring — edges, critique round, revision round, integration.

Reuses patterns from ``test_studio_writers`` (mock injection) and
``test_agent_schemas`` (``CandidateArtifact`` construction).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from amazon_copy.agents.critique import (
    ring_edges,
    run_critique_round,
    run_revision_round,
    critique_and_revise,
)
from amazon_copy.config import Settings
from amazon_copy.llm.mock import AsyncMockLLM
from amazon_copy.schemas.agents import CandidateArtifact, CritiqueArtifact, WriterLane


# ── Helpers ────────────────────────────────────────────────────────────


def _settings(**kwargs: object) -> Settings:
    """Build a Settings instance with ``MOCK=true`` by default."""
    kwargs.setdefault("MOCK", True)
    kwargs.setdefault("writer_model", "deepseek-chat")
    kwargs.setdefault("review_model", "deepseek-chat")
    kwargs.setdefault("vote_model", "deepseek-chat")
    return Settings.model_validate(kwargs)


def _make_candidates() -> list[CandidateArtifact]:
    """Three candidates, one per lane, with distinct IDs."""
    return [
        CandidateArtifact(
            candidate_id="cand-1",
            lane=WriterLane.SEO,
            titles=["SEO Title A", "SEO Title B", "SEO Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        ),
        CandidateArtifact(
            candidate_id="cand-2",
            lane=WriterLane.DIFFERENTIATION,
            titles=["Diff Title A", "Diff Title B", "Diff Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        ),
        CandidateArtifact(
            candidate_id="cand-3",
            lane=WriterLane.CLARITY,
            titles=["Clarity Title A", "Clarity Title B", "Clarity Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        ),
    ]


# ── Ring edges ─────────────────────────────────────────────────────────


class TestRingEdges:
    """``ring_edges`` topology — deterministic, no I/O."""

    def test_three_ids_cycle(self) -> None:
        """3 IDs produce a 3-edge cycle."""
        edges = ring_edges(["c", "a", "b"])
        assert len(edges) == 3
        # sorted → a, b, c → a→b, b→c, c→a
        assert edges == [("a", "b"), ("b", "c"), ("c", "a")]

    def test_two_ids_mutual(self) -> None:
        """2 IDs produce 2 mutual edges."""
        edges = ring_edges(["x", "y"])
        assert len(edges) == 2
        assert edges == [("x", "y"), ("y", "x")]

    def test_one_id_empty(self) -> None:
        """1 ID produces an empty edge list."""
        assert ring_edges(["only"]) == []

    def test_four_ids_empty(self) -> None:
        """4 IDs also produces an empty edge list (not handled)."""
        assert ring_edges(["a", "b", "c", "d"]) == []

    def test_empty_list_empty(self) -> None:
        """Empty input yields empty output."""
        assert ring_edges([]) == []


# ── Round-level tests (use real AsyncMockLLM via Settings) ─────────────


class TestCritiqueRound:
    """``run_critique_round`` with mock fixtures."""

    @pytest.mark.asyncio
    async def test_three_candidates_three_critiques(self) -> None:
        """3 candidates → 3 ring edges → 3 CritiqueArtifacts."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        assert len(critiques) == 3
        for c in critiques:
            assert isinstance(c, CritiqueArtifact)
            assert c.target_candidate_id in {"cand-1", "cand-2", "cand-3"}
            assert len(c.findings) > 0

    @pytest.mark.asyncio
    async def test_findings_are_normalised(self) -> None:
        """Each finding is a structured CritiqueFinding, not raw JSON."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        for c in critiques:
            for f in c.findings:
                assert hasattr(f, "category")
                assert hasattr(f, "finding")
                assert hasattr(f, "recommendation")
                assert isinstance(f.category, str)
                assert isinstance(f.finding, str)


class TestRevisionRound:
    """``run_revision_round`` with mock fixtures."""

    @pytest.mark.asyncio
    async def test_one_revision_per_unique_target(self) -> None:
        """3 unique targets → 3 revisions."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        revisions = await run_revision_round(critiques, candidates, _settings())
        assert len(revisions) == 3

    @pytest.mark.asyncio
    async def test_revisions_have_rev_ids(self) -> None:
        """Revised IDs follow the ``{old}-rev`` convention."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        revisions = await run_revision_round(critiques, candidates, _settings())
        for r in revisions:
            assert r.candidate_id.endswith("-rev")

    @pytest.mark.asyncio
    async def test_revisions_preserve_lane(self) -> None:
        """Each revision stays in its original lane."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        revisions = await run_revision_round(critiques, candidates, _settings())
        rev_map = {r.candidate_id: r for r in revisions}
        assert rev_map["cand-1-rev"].lane == WriterLane.SEO
        assert rev_map["cand-2-rev"].lane == WriterLane.DIFFERENTIATION
        assert rev_map["cand-3-rev"].lane == WriterLane.CLARITY

    @pytest.mark.asyncio
    async def test_titles_and_bullets_satisfy_contract(self) -> None:
        """Every revision has exactly 3 titles and 5 bullets, all non-empty."""
        candidates = _make_candidates()
        critiques = await run_critique_round(candidates, _settings())
        revisions = await run_revision_round(critiques, candidates, _settings())
        for r in revisions:
            assert len(r.titles) == 3, f"{r.candidate_id}: expected 3 titles"
            assert len(r.bullets) == 5, f"{r.candidate_id}: expected 5 bullets"
            assert all(t.strip() for t in r.titles), f"{r.candidate_id}: empty title"
            assert all(b.strip() for b in r.bullets), f"{r.candidate_id}: empty bullet"


# ── Integration (critique_and_revise) ──────────────────────────────────


class TestCritiqueAndRevise:
    """``critique_and_revise`` — top-level integration."""

    @pytest.mark.asyncio
    async def test_returns_revisions_with_rev_ids(self) -> None:
        """One-shot returns CandidateArtifacts with -rev suffix."""
        results = await critique_and_revise(_make_candidates(), _settings())
        assert len(results) > 0
        for r in results:
            assert isinstance(r, CandidateArtifact)
            assert r.candidate_id.endswith("-rev")

    @pytest.mark.asyncio
    async def test_preserves_lanes(self) -> None:
        """All three lanes survive critique + revise."""
        results = await critique_and_revise(_make_candidates(), _settings())
        assert len(results) == 3
        rev_map = {r.candidate_id: r for r in results}
        assert rev_map["cand-1-rev"].lane == WriterLane.SEO
        assert rev_map["cand-2-rev"].lane == WriterLane.DIFFERENTIATION
        assert rev_map["cand-3-rev"].lane == WriterLane.CLARITY

    @pytest.mark.asyncio
    async def test_call_counts_one_round_each(self) -> None:
        """Exactly one round: 3 critic + 3 reviser = 6 LLM calls, finite."""
        critic = AsyncMockLLM("critic")
        reviser = AsyncMockLLM("reviser")
        mapping: dict[str, AsyncMockLLM] = {"critic": critic, "reviser": reviser}

        def mock_get(role: str, **kwargs: object) -> AsyncMockLLM:
            return mapping[role]

        candidates = _make_candidates()
        with patch("amazon_copy.agents.critique.get_async_llm", mock_get):
            results = await critique_and_revise(candidates, _settings())

        assert critic.call_count == 3, (
            f"expected 3 critic calls for 3 edges, got {critic.call_count}"
        )
        assert reviser.call_count == 3, (
            f"expected 3 reviser calls for 3 targets, got {reviser.call_count}"
        )
        assert len(results) == 3
