"""Tests for studio pipeline agent schemas."""
import pytest
from pydantic import ValidationError
from amazon_copy.schemas.agents import (
    AgentSummary,
    Ballot,
    CandidateArtifact,
    CritiqueArtifact,
    CritiqueFinding,
    GateFinding,
    GateResult,
    IntegrationTrace,
    LaneResult,
    RankingResult,
    RevisionArtifact,
    SCORE_DIMS,
    WriterLane,
)


class TestCandidateArtifact:
    def test_valid_candidate(self):
        obj = CandidateArtifact(
            candidate_id="cand-001",
            lane=WriterLane.SEO,
            titles=["Title A", "Title B", "Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
            claim_ids=["clm-1", "clm-2"],
        )
        assert obj.candidate_id == "cand-001"
        assert obj.lane == WriterLane.SEO
        assert len(obj.titles) == 3
        assert len(obj.bullets) == 5

    def test_bad_title_count(self):
        with pytest.raises(ValidationError):
            CandidateArtifact(
                candidate_id="cand-002",
                lane=WriterLane.CLARITY,
                titles=["Only one"],  # need 3
                bullets=["b1", "b2", "b3", "b4", "b5"],
            )


class TestGateResult:
    def test_illegal_eligible_with_hard_fails(self):
        findings = [
            GateFinding(code="G001", severity="error", message="fail", passed=False),
        ]
        with pytest.raises(ValueError, match="eligible cannot be True"):
            GateResult(
                candidate_id="cand-003",
                findings=findings,
                eligible=True,
            )

    def test_eligible_false_with_hard_fail_ok(self):
        """eligible=False with hard fail should be valid."""
        findings = [
            GateFinding(code="G001", severity="error", message="fail", passed=False),
        ]
        result = GateResult(
            candidate_id="cand-004",
            findings=findings,
            eligible=False,
        )
        assert result.eligible is False
        assert len(result.findings) == 1


class TestCritique:
    def test_critique_finding(self):
        f = CritiqueFinding(
            category="grammar",
            finding="Missing period",
            recommendation="Add period",
        )
        assert f.category == "grammar"

    def test_critique_artifact(self):
        findings = [
            CritiqueFinding(
                category="grammar", finding="Missing period",
                recommendation="Add period",
            ),
        ]
        art = CritiqueArtifact(target_candidate_id="cand-001", findings=findings)
        assert art.target_candidate_id == "cand-001"
        assert len(art.findings) == 1


class TestRevision:
    def test_happy(self):
        cand = CandidateArtifact(
            candidate_id="cand-002",
            lane=WriterLane.SEO,
            titles=["A", "B", "C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        )
        rev = RevisionArtifact(parent_candidate_id="cand-001", candidate=cand)
        assert rev.parent_candidate_id == "cand-001"
        assert rev.candidate.candidate_id == "cand-002"

    def test_requires_parent_candidate_id(self):
        cand = CandidateArtifact(
            candidate_id="cand-003",
            lane=WriterLane.CLARITY,
            titles=["A", "B", "C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        )
        with pytest.raises(ValidationError):
            RevisionArtifact(parent_candidate_id="", candidate=cand)


class TestBallot:
    def _make_valid_scores(self) -> dict[str, float]:
        return {dim: 8.0 for dim in SCORE_DIMS}

    def test_happy(self):
        scores = self._make_valid_scores()
        b = Ballot(judge_alias="judge-1", scores=scores, ranked_aliases=["cand-A", "cand-B"])
        assert b.judge_alias == "judge-1"
        assert b.ranked_aliases == ["cand-A", "cand-B"]

    def test_ballot_missing_dim_fails(self):
        scores = self._make_valid_scores()
        del scores[SCORE_DIMS[0]]
        with pytest.raises(ValueError, match="scores keys must match"):
            Ballot(judge_alias="judge-1", scores=scores, ranked_aliases=[])

    def test_ballot_extra_dim_fails(self):
        scores = self._make_valid_scores()
        scores["extra_dim"] = 5.0
        with pytest.raises(ValueError, match="scores keys must match"):
            Ballot(judge_alias="judge-1", scores=scores, ranked_aliases=[])

    def test_ballot_score_out_of_range_low(self):
        scores = self._make_valid_scores()
        scores[SCORE_DIMS[0]] = -1.0
        with pytest.raises(ValueError, match="must be between 0 and 10"):
            Ballot(judge_alias="judge-1", scores=scores, ranked_aliases=[])

    def test_ballot_score_out_of_range_high(self):
        scores = self._make_valid_scores()
        scores[SCORE_DIMS[0]] = 10.1
        with pytest.raises(ValueError, match="must be between 0 and 10"):
            Ballot(judge_alias="judge-1", scores=scores, ranked_aliases=[])


class TestRankingResult:
    def test_happy(self):
        r = RankingResult(
            ordered_candidate_ids=["cand-A", "cand-B"],
            scores={"overall": 8.5},
        )
        assert r.ordered_candidate_ids == ["cand-A", "cand-B"]
        assert r.tie_break_notes == ""


class TestIntegrationTrace:
    def test_happy(self):
        t = IntegrationTrace(
            winner_id="cand-001",
            used_claim_ids=["clm-1", "clm-2"],
        )
        assert t.winner_id == "cand-001"
        assert t.fallback_used is False

    def test_fallback_true(self):
        t = IntegrationTrace(
            winner_id="cand-002",
            used_claim_ids=[],
            fallback_used=True,
        )
        assert t.fallback_used is True


class TestAgentSummary:
    def test_happy(self):
        s = AgentSummary(agent_role="writer", status="completed")
        assert s.agent_role == "writer"
        assert s.redacted_notes == ""


class TestLaneResult:
    def test_with_candidate(self):
        cand = CandidateArtifact(
            candidate_id="cand-001",
            lane=WriterLane.SEO,
            titles=["A", "B", "C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        )
        lr = LaneResult(lane=WriterLane.SEO, candidate=cand)
        assert lr.candidate is not None
        assert lr.error is None

    def test_with_error(self):
        lr = LaneResult(lane=WriterLane.CLARITY, error="LLM timeout")
        assert lr.candidate is None
        assert lr.error == "LLM timeout"

    def test_both_none(self):
        lr = LaneResult(lane=WriterLane.DIFFERENTIATION)
        assert lr.candidate is None
        assert lr.error is None


class TestFullChain:
    def test_model_dump_serializes(self):
        """Full chain: Candidate → Revision → Critique → Ballot → Ranking → Integration."""
        # Build a candidate
        cand = CandidateArtifact(
            candidate_id="cand-001",
            lane=WriterLane.SEO,
            titles=["Title A", "Title B", "Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
            claim_ids=["clm-1"],
        )
        # Revision wrapping the candidate
        rev = RevisionArtifact(parent_candidate_id="cand-000", candidate=cand)

        # Critique targeting the candidate
        findings = [
            CritiqueFinding(
                category="grammar", finding="Missing period",
                recommendation="Add period",
            ),
        ]
        critique = CritiqueArtifact(target_candidate_id="cand-001", findings=findings)

        # Ballot scoring the candidate
        scores = {dim: 7.5 for dim in SCORE_DIMS}
        ballot = Ballot(judge_alias="judge-A", scores=scores, ranked_aliases=["cand-001"])

        # Ranking result
        ranking = RankingResult(
            ordered_candidate_ids=["cand-001"],
            scores={"overall": 7.5},
            tie_break_notes="unanimous",
        )

        # Integration trace
        trace = IntegrationTrace(
            winner_id="cand-001",
            used_claim_ids=["clm-1"],
            fallback_used=False,
        )

        # Agent summary + lane result
        summary = AgentSummary(agent_role="writer", status="completed")
        lane = LaneResult(lane=WriterLane.SEO, candidate=cand)

        # Assert every model dumps without error
        for obj in (cand, rev, critique, ballot, ranking, trace, summary, lane):
            d = obj.model_dump()
            assert isinstance(d, dict)
        # Also assert model_dump_json round-trips
        for obj in (cand, rev, critique, ballot, ranking, trace, summary, lane):
            j = obj.model_dump_json()
            assert isinstance(j, str)
            assert len(j) > 0
