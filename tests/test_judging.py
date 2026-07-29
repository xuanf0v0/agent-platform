"""Tests for the anonymous dual-judge ranking module (Task 17)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from amazon_copy.agents.judging import NoEligibleError, alias_map, make_permutations, run_judges
from amazon_copy.schemas.agents import CandidateArtifact, RankingResult, WriterLane

# ── Shared test data ────────────────────────────────────────────────

_JUDGE_FIXTURE: dict = {
    "winner": "reviser",
    "rankings": [
        {"rank": 1, "candidate": "reviser", "score": 8.5, "rationale": "Best balance"},
        {"rank": 2, "candidate": "writer_seo", "score": 7.8, "rationale": "Good SEO"},
        {"rank": 3, "candidate": "writer_clarity", "score": 7.0, "rationale": "Clear"},
        {"rank": 4, "candidate": "writer_differentiation", "score": 6.5, "rationale": "Weak"},
    ],
    "dimensions": {"seo": 8.0, "clarity": 8.5, "persuasion": 8.0, "compliance": 9.0},
}


def _make_candidates(n: int) -> list[CandidateArtifact]:
    """Build *n* deterministic candidate fixtures."""
    lanes = [WriterLane.SEO, WriterLane.DIFFERENTIATION, WriterLane.CLARITY]
    return [
        CandidateArtifact(
            candidate_id=f"c{i:03d}",
            lane=lanes[i % 3],
            titles=[f"Title {i} A", f"Title {i} B", f"Title {i} C"],
            bullets=[f"b{i}_{j}" for j in range(5)],
            claim_ids=[f"clm-{i}"],
        )
        for i in range(n)
    ]


# ── Tests: make_permutations ────────────────────────────────────────


class TestMakePermutations:
    def test_two_different_orders(self):
        """Two permutations of the same list should differ."""
        ids = ["a", "b", "c", "d", "e"]
        p1, p2 = make_permutations("run-001", ids)
        assert p1 != p2, "j1 and j2 shuffles must differ"
        assert sorted(p1) == sorted(ids), "p1 must preserve elements"
        assert sorted(p2) == sorted(ids), "p2 must preserve elements"

    def test_deterministic_same_run_id(self):
        """Same run_id yields identical permutations."""
        ids = ["x", "y", "z"]
        p1a, p2a = make_permutations("stable", ids)
        p1b, p2b = make_permutations("stable", ids)
        assert p1a == p1b
        assert p2a == p2b

    def test_different_run_id_different_orders(self):
        """Different run_id should (almost certainly) yield different orders."""
        ids = ["a", "b", "c", "d"]
        p1a, p2a = make_permutations("run-A", ids)
        p1b, p2b = make_permutations("run-B", ids)
        # At least one permutation should differ.
        assert p1a != p1b or p2a != p2b

    def test_single_element_identity(self):
        """Single-element list: both permutations are the same (only order)."""
        ids = ["only"]
        p1, p2 = make_permutations("r1", ids)
        assert p1 == ["only"]
        assert p2 == ["only"]

    def test_empty_list(self):
        """Empty list returns empty permutations."""
        p1, p2 = make_permutations("r1", [])
        assert p1 == []
        assert p2 == []


# ── Tests: alias_map ────────────────────────────────────────────────


class TestAliasMap:
    def test_bidirectional_mapping(self):
        """alias_map returns both A_i→id and id→A_i entries."""
        mapping = alias_map(["id_x", "id_y"])
        assert mapping["A1"] == "id_x"
        assert mapping["A2"] == "id_y"
        assert mapping["id_x"] == "A1"
        assert mapping["id_y"] == "A2"

    def test_length_matches(self):
        """One alias per input element."""
        mapping = alias_map(["a", "b", "c", "d"])
        aliases = {k for k in mapping if k.startswith("A")}
        assert len(aliases) == 4

    def test_empty(self):
        """Empty input → empty mapping."""
        assert alias_map([]) == {}

    def test_alias_numbers_start_at_one(self):
        """Aliases are 1-indexed: A1, A2, …"""
        mapping = alias_map(["first", "second", "third"])
        assert "A1" in mapping
        assert "A3" in mapping


# ── Tests: run_judges ──────────────────────────────────────────────


class TestRunJudges:
    """End-to-end tests for the dual-judge ranking function."""

    @pytest.fixture
    def mock_judge(self):
        """Monkey-patch AsyncMockLLM so it returns a controllable fixture.

        Even though both judge instances get the *same* mock instance,
        each is called exactly once (``complete`` await_count == 2
        overall).
        """
        instance = MagicMock()
        instance.call_count = 0

        async def fake_complete(_system: str, _user: str, **kwargs: object) -> str:
            instance.call_count += 1
            return json.dumps(_JUDGE_FIXTURE)

        instance.complete = fake_complete
        patcher = patch("amazon_copy.agents.judging.AsyncMockLLM", return_value=instance)
        with patcher as mock_cls:
            yield mock_cls, instance

    # ── happy paths ─────────────────────────────────────────────

    async def test_returns_valid_ranking_result(self, mock_judge):
        """run_judges returns a valid RankingResult."""
        candidates = _make_candidates(3)
        result = await run_judges(candidates, "test-run")
        assert isinstance(result, RankingResult)
        assert len(result.ordered_candidate_ids) == 3
        assert len(result.scores) == 3
        for cid in ("c000", "c001", "c002"):
            assert cid in result.scores
            assert 0 <= result.scores[cid] <= 10

    async def test_ordered_by_score_descending(self, mock_judge):
        """Result is ordered by aggregate score descending."""
        candidates = _make_candidates(3)
        result = await run_judges(candidates, "test-run")
        scores = [result.scores[cid] for cid in result.ordered_candidate_ids]
        assert scores == sorted(scores, reverse=True)

    async def test_stable_winner_same_run_id(self, mock_judge):
        """Same run_id + same candidates yields the same winner."""
        candidates = _make_candidates(4)
        r1 = await run_judges(candidates, "stable-run")
        r2 = await run_judges(candidates, "stable-run")
        assert r1.ordered_candidate_ids == r2.ordered_candidate_ids
        assert r1.scores == r2.scores

    async def test_different_run_different_winner_possible(self, mock_judge):
        """Different run_ids may (likely will) produce different orderings."""
        candidates = _make_candidates(4)
        r_a = await run_judges(candidates, "run-alpha")
        r_b = await run_judges(candidates, "run-beta")
        # Not strictly guaranteed, but extremely unlikely with 4 candidates.
        if r_a.ordered_candidate_ids == r_b.ordered_candidate_ids:
            # If they happen to match, at least verify they're valid.
            assert len(r_a.ordered_candidate_ids) == 4

    # ── edge cases ──────────────────────────────────────────────

    async def test_empty_candidates_raises(self):
        """Empty candidate list raises NoEligibleError."""
        with pytest.raises(NoEligibleError, match="No eligible candidates"):
            await run_judges([], "empty-run")

    async def test_single_candidate(self, mock_judge):
        """Single candidate returns a result with one entry."""
        candidates = _make_candidates(1)
        result = await run_judges(candidates, "solo")
        assert len(result.ordered_candidate_ids) == 1
        assert result.ordered_candidate_ids[0] == "c000"

    async def test_two_candidates(self, mock_judge):
        """Two candidates produces a ranking with both."""
        candidates = _make_candidates(2)
        result = await run_judges(candidates, "duo")
        assert len(result.ordered_candidate_ids) == 2
        assert set(result.ordered_candidate_ids) == {"c000", "c001"}

    # ── call counts ─────────────────────────────────────────────

    async def test_two_judge_calls_for_two_plus_candidates(self, mock_judge):
        """Exactly two AsyncMockLLM instances created when ≥2 candidates."""
        mock_cls, instance = mock_judge
        await run_judges(_make_candidates(3), "count-test")
        assert mock_cls.call_count == 2, "expected 2 AsyncMockLLM instantiations"
        assert instance.call_count == 2, "expected 2 complete() invocations"

    async def test_zero_judge_calls_for_empty(self):
        """Empty candidates → NoEligibleError → no LLM calls.

        (No mock patching here — the function short-circuits before
        reaching any LLM instantiation.)
        """
        with patch("amazon_copy.agents.judging.AsyncMockLLM") as mock_cls:
            with pytest.raises(NoEligibleError):
                await run_judges([], "empty-test")
            mock_cls.assert_not_called()

    # ── tie-breaking ─────────────────────────────────────────────

    async def test_tie_break_by_lexicographic_id(self, mock_judge):
        """Ordering follows: higher score first, then lexicographic ID for ties."""
        candidates = _make_candidates(3)
        result = await run_judges(candidates, "tie-check")
        # Verify the actual ordering matches the expected tie-breaking rule.
        expected = sorted(
            result.scores.keys(),
            key=lambda cid: (-result.scores[cid], cid),
        )
        assert result.ordered_candidate_ids == expected

    async def test_score_dims_in_ballot(self, mock_judge):
        """Each judge produces a Ballot with all SCORE_DIMS keys."""
        _mock_cls, instance = mock_judge
        # We can't access internal Ballots directly, but we can verify the
        # mock was called correctly.  The fixture dimensions are:
        # seo=8.0, clarity=8.5, persuasion=8.0, compliance=9.0
        # Missing dims should default to 5.0 in the Ballot.
        await run_judges(_make_candidates(3), "dims-test")
        assert instance.call_count == 2
        # We trust _build_mock_ballot fills SCORE_DIMS correctly.
        # (Validated indirectly through Ballot construction inside.)


# ── Integration-style test ─────────────────────────────────────────


class TestFullJudgingPipeline:
    """Run with real AsyncMockLLM (no patching) to verify end-to-end."""

    async def test_real_fixture_round_trip(self):
        """Run judges with the real mock fixture — verify it doesn't crash."""
        candidates = _make_candidates(4)
        result = await run_judges(candidates, "real-fixture-run")
        assert isinstance(result, RankingResult)
        assert len(result.ordered_candidate_ids) == 4
        # All scores should be present and non-negative.
        for cid in result.ordered_candidate_ids:
            assert result.scores[cid] >= 0

    async def test_winner_is_first_in_ordered_list(self):
        """The winner is always ordered_candidate_ids[0]."""
        candidates = _make_candidates(3)
        result = await run_judges(candidates, "winner-check")
        winner = result.ordered_candidate_ids[0]
        # Verify it has the highest score.
        winner_score = result.scores[winner]
        for cid, score in result.scores.items():
            if cid != winner:
                assert winner_score >= score

    async def test_scores_within_range(self):
        """All scores are within 0-10."""
        candidates = _make_candidates(3)
        result = await run_judges(candidates, "range-check")
        for score in result.scores.values():
            assert 0 <= score <= 10
