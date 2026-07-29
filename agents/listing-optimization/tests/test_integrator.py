"""Tests for Task 18 integrator — post-validation and first-eligible selection."""

from __future__ import annotations

from amazon_copy.agents.integrator import integrate, post_validate
from amazon_copy.schemas import (
    CandidateArtifact,
    GateResult,
    RankingResult,
    WriterLane,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def _candidate(
    *,
    candidate_id: str = "cand-1",
    claim_ids: list[str] | None = None,
    titles: list[str] | None = None,
    bullets: list[str] | None = None,
) -> CandidateArtifact:
    return CandidateArtifact(
        candidate_id=candidate_id,
        lane=WriterLane.SEO,
        titles=titles
        or [
            "USB-C Hub 7-in-1 Multiport Adapter for Laptop Docking Station",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop Docking",
        ],
        bullets=bullets
        or [
            "7-in-1 USB-C hub expands your laptop connectivity with HDMI 4K output",
            "100W Power Delivery pass-through charges your laptop at full speed",
            "SD/TF card slots support simultaneous access for photographers",
            "Compact aluminum design fits perfectly in your travel bag",
            "Plug-and-play setup requires no additional drivers or software",
        ],
        claim_ids=claim_ids or [],
    )


def _promo_candidate(candidate_id: str = "cand-promo") -> CandidateArtifact:
    """A candidate that fails hard gates due to a promo phrase in title."""
    titles = [
        "Free Shipping USB-C Hub Multiport Adapter for Laptop Docking",
        "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
        "7-in-1 USB-C Hub Adapter with PD 100W for Laptop Docking",
    ]
    return _candidate(candidate_id=candidate_id, titles=titles)


def _ranking(
    ordered_ids: list[str],
    scores: dict[str, float] | None = None,
) -> RankingResult:
    if scores is None:
        scores = {cid: 10.0 - i for i, cid in enumerate(ordered_ids)}
    return RankingResult(
        ordered_candidate_ids=ordered_ids,
        scores=scores,
    )


# ── post_validate ──────────────────────────────────────────────────────


class TestPostValidate:
    def test_delegates_to_evaluate_candidate(self) -> None:
        """A clean candidate should pass post_validate."""
        cand = _candidate()
        result = post_validate(cand)
        assert result.eligible
        assert isinstance(result, GateResult)

    def test_hard_gate_failures_preserved(self) -> None:
        """Hard-gate failures from evaluate_candidate are preserved."""
        cand = _promo_candidate()
        result = post_validate(cand)
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "PROMO_TITLE_PHRASE" in codes

    def test_unknown_claim_ids_when_allowed_set_provided(self) -> None:
        """claim_ids not in the allowed set produce a CLAIM_ID_UNKNOWN finding."""
        cand = _candidate(claim_ids=["claim-1", "claim-99"])
        result = post_validate(cand, allowed_claim_ids={"claim-1", "claim-2"})
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "CLAIM_ID_UNKNOWN" in codes

    def test_known_claim_ids_pass(self) -> None:
        """All claim_ids in the allowed set — no extra finding."""
        cand = _candidate(claim_ids=["claim-1", "claim-2"])
        result = post_validate(cand, allowed_claim_ids={"claim-1", "claim-2", "claim-3"})
        assert result.eligible
        assert not any(f.code == "CLAIM_ID_UNKNOWN" for f in result.findings)

    def test_allowed_claim_ids_none_is_noop(self) -> None:
        """Omitting allowed_claim_ids should not gate on claim_ids."""
        cand = _candidate(claim_ids=["any-old-id"])
        result = post_validate(cand)
        assert result.eligible

    def test_allowed_claim_ids_empty_set_rejects(self) -> None:
        """Empty allowed set means any claim_id is unknown."""
        cand = _candidate(claim_ids=["claim-1"])
        result = post_validate(cand, allowed_claim_ids=set())
        assert not result.eligible
        assert any(f.code == "CLAIM_ID_UNKNOWN" for f in result.findings)

    def test_unknown_claim_ids_and_hard_gate_failure(self) -> None:
        """Both hard-gate failure and unknown claim IDs appear in findings."""
        cand = _promo_candidate(candidate_id="multi-fail")
        # Replace claim_ids — can't use model_construct because it's frozen
        cand = CandidateArtifact(
            candidate_id="multi-fail",
            lane=WriterLane.SEO,
            titles=cand.titles,
            bullets=cand.bullets,
            claim_ids=["unknown-claim"],
        )
        result = post_validate(cand, allowed_claim_ids={"allowed-1"})
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "PROMO_TITLE_PHRASE" in codes
        assert "CLAIM_ID_UNKNOWN" in codes


# ── integrate ──────────────────────────────────────────────────────────


class TestIntegrate:
    async def test_picks_first_eligible_ranked(self) -> None:
        """First candidate in ranking that passes gates is returned."""
        c1 = _candidate(candidate_id="cand-1")
        c2 = _candidate(candidate_id="cand-2")
        ranked = _ranking(["cand-1", "cand-2"])
        winner, trace = await integrate(ranked, [c1, c2])
        assert winner is not None
        assert winner.candidate_id == "cand-1"
        assert trace.winner_id == "cand-1"
        assert not trace.fallback_used

    async def test_skips_ineligible(self) -> None:
        """Candidates failing hard gates are skipped for the next ranked."""
        c1 = _promo_candidate(candidate_id="cand-1")
        c2 = _candidate(candidate_id="cand-2")
        ranked = _ranking(["cand-1", "cand-2"])
        winner, trace = await integrate(ranked, [c1, c2])
        assert winner is not None
        assert winner.candidate_id == "cand-2"
        assert trace.winner_id == "cand-2"
        assert not trace.fallback_used

    async def test_all_ineligible_returns_none(self) -> None:
        """When every candidate fails gates, returns (None, fallback trace)."""
        c1 = _promo_candidate(candidate_id="cand-1")
        c2 = _promo_candidate(candidate_id="cand-2")
        ranked = _ranking(["cand-1", "cand-2"])
        winner, trace = await integrate(ranked, [c1, c2])
        assert winner is None
        assert trace.winner_id == ""
        assert trace.used_claim_ids == []
        assert not trace.fallback_used

    async def test_empty_ranking_returns_none(self) -> None:
        """An empty ranking produces no winner."""
        c1 = _candidate(candidate_id="cand-1")
        ranked = _ranking([])
        winner, trace = await integrate(ranked, [c1])
        assert winner is None
        assert trace.winner_id == ""
        assert not trace.fallback_used

    async def test_ranking_with_missing_candidate_skipped(self) -> None:
        """A candidate_id in the ranking but absent from the pool is skipped."""
        c1 = _candidate(candidate_id="cand-1")
        ranked = _ranking(["missing", "cand-1"])
        winner, trace = await integrate(ranked, [c1])
        assert winner is not None
        assert winner.candidate_id == "cand-1"
        assert trace.winner_id == "cand-1"

    async def test_unknown_claim_ids_make_ineligible(self) -> None:
        """claim_ids outside the allowed set disqualify ranked candidates."""
        c1 = _candidate(candidate_id="cand-1", claim_ids=["claim-99"])
        c2 = _candidate(candidate_id="cand-2", claim_ids=["claim-1"])
        ranked = _ranking(["cand-1", "cand-2"])
        winner, trace = await integrate(
            ranked, [c1, c2], allowed_claim_ids={"claim-1"},
        )
        assert winner is not None
        assert winner.candidate_id == "cand-2"
        assert trace.winner_id == "cand-2"

    async def test_preserves_winner_claim_ids_in_trace(self) -> None:
        """IntegrationTrace carries the winner's claim_ids."""
        c1 = _candidate(candidate_id="cand-1", claim_ids=["c1", "c2"])
        ranked = _ranking(["cand-1"])
        _, trace = await integrate(ranked, [c1])
        assert trace.used_claim_ids == ["c1", "c2"]

    async def test_settings_param_ignored(self) -> None:
        """settings parameter is accepted but not used."""
        c1 = _candidate(candidate_id="cand-1")
        ranked = _ranking(["cand-1"])
        winner, _trace = await integrate(ranked, [c1], _settings={"key": "val"})
        assert winner is not None
        assert winner.candidate_id == "cand-1"
