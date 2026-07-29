"""Tests for Task 16 hard gates — deterministic pre-pipeline eligibility."""

from __future__ import annotations

import pydantic
import pytest
from amazon_copy.agents.hard_gates import evaluate_candidate, filter_eligible
from amazon_copy.schemas import CandidateArtifact, GateFinding, GateResult, WriterLane

# ── helpers ──────────────────────────────────────────────────────────────


def _candidate(
    *,
    titles: list[str] | None = None,
    bullets: list[str] | None = None,
    claim_ids: list[str] | None = None,
    candidate_id: str = "test-cand",
    lane: WriterLane = WriterLane.SEO,
) -> CandidateArtifact:
    return CandidateArtifact(
        candidate_id=candidate_id,
        lane=lane,
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


def _clean_titles() -> list[str]:
    return [
        "USB-C Hub 7-in-1 Multiport Adapter for Laptop Docking Station",
        "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
        "7-in-1 USB-C Hub Adapter with PD 100W for Laptop Docking",
    ]


def _clean_bullets() -> list[str]:
    return [
        "7-in-1 USB-C hub expands your laptop connectivity with HDMI 4K output",
        "100W Power Delivery pass-through charges your laptop at full speed",
        "SD/TF card slots support simultaneous access for photographers",
        "Compact aluminum design fits perfectly in your travel bag",
        "Plug-and-play setup requires no additional drivers or software",
    ]


# ── 1. Structure counts ─────────────────────────────────────────────────


class TestStructureCounts:
    def test_wrong_title_count(self) -> None:
        # Use model_construct to bypass CandidateArtifact's own Pydantic
        # min_length=3 validation and test the gate's defensive check.
        cand = CandidateArtifact.model_construct(
            candidate_id="test",
            lane=WriterLane.SEO,
            titles=["title a", "title b"],
            bullets=_clean_bullets(),
        )
        result = evaluate_candidate(cand)
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "STRUCTURE_TITLES_LEN" in codes

    def test_wrong_bullet_count(self) -> None:
        cand = CandidateArtifact.model_construct(
            candidate_id="test",
            lane=WriterLane.SEO,
            titles=_clean_titles(),
            bullets=["bp1", "bp2"],
        )
        result = evaluate_candidate(cand)
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "STRUCTURE_BULLETS_LEN" in codes

    def test_both_wrong_counts_multiple_findings(self) -> None:
        cand = CandidateArtifact.model_construct(
            candidate_id="multi",
            lane=WriterLane.SEO,
            titles=["a", "b"],
            bullets=["x", "y", "z"],
        )
        result = evaluate_candidate(cand)
        assert not result.eligible
        codes = {f.code for f in result.findings}
        assert "STRUCTURE_TITLES_LEN" in codes
        assert "STRUCTURE_BULLETS_LEN" in codes

    def test_exact_counts_pass_no_findings(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand)
        # These structural checks produce no findings when correct
        assert not any(f.code.startswith("STRUCTURE_") for f in result.findings)


# ── 2. Empty content ────────────────────────────────────────────────────


class TestEmptyContent:
    def test_empty_title(self) -> None:
        titles = [
            "USB-C Hub Multiport Adapter for Laptop Docking",
            "",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "CONTENT_EMPTY_TITLE" for f in result.findings)

    def test_whitespace_only_title(self) -> None:
        titles = [
            "USB-C Hub Multiport Adapter for Laptop Docking",
            "   ",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "CONTENT_EMPTY_TITLE" for f in result.findings)

    def test_empty_bullet(self) -> None:
        bullets = [
            "7-in-1 USB-C hub expands your laptop connectivity",
            "",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "CONTENT_EMPTY_BULLET" for f in result.findings)

    def test_all_titles_empty(self) -> None:
        cand = _candidate(titles=["", "", ""])
        result = evaluate_candidate(cand)
        assert not result.eligible
        empty_titles = [f for f in result.findings if f.code == "CONTENT_EMPTY_TITLE"]
        assert len(empty_titles) == 3


# ── 3. Trailing period on bullets ───────────────────────────────────────


class TestTrailingPeriod:
    def test_single_trailing_period(self) -> None:
        bullets = [
            "7-in-1 USB-C hub expands your laptop connectivity.",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly in your bag",
            "Plug-and-play setup requires no additional software",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        period_findings = [f for f in result.findings if f.code == "CONTENT_TRAILING_PERIOD"]
        assert len(period_findings) == 1

    def test_all_bullets_trailing_period(self) -> None:
        bullets = [
            "First bullet point here.",
            "Second bullet point content.",
            "Third bullet describes features.",
            "Fourth bullet talks about specs.",
            "Fifth bullet concludes listing.",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        period_findings = [f for f in result.findings if f.code == "CONTENT_TRAILING_PERIOD"]
        assert len(period_findings) == 5

    def test_internal_period_ok(self) -> None:
        bullets = [
            "USB 3.0 speeds for fast data transfer up to 5 Gbps",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly in your bag",
            "Plug-and-play setup requires no additional software",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not any(f.code == "CONTENT_TRAILING_PERIOD" for f in result.findings)


# ── 4. Banned promo phrases ────────────────────────────────────────────


class TestBannedPromoPhrases:
    def test_free_shipping_in_title_via_scanner(self) -> None:
        titles = [
            "Free Shipping USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_TITLE_PHRASE" for f in result.findings)

    def test_best_seller_in_title_via_scanner_subjective(self) -> None:
        titles = [
            "Best Seller USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_TITLE_PHRASE" for f in result.findings)

    def test_risk_free_in_title_via_scanner(self) -> None:
        titles = [
            "Risk Free USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_TITLE_PHRASE" for f in result.findings)

    def test_free_shipping_in_bullet_via_static_list(self) -> None:
        bullets = [
            "Free shipping on this USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)

    def test_best_seller_in_bullet_via_static_list(self) -> None:
        bullets = [
            "Best seller USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)

    def test_quality_guaranteed_in_bullet_via_static_list(self) -> None:
        bullets = [
            "100% quality guaranteed on this USB-C hub",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)

    def test_promo_terms_casefold_matches(self) -> None:
        bullets = [
            "FREE SHIPPING on USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)


class TestCustomBannedTerms:
    def test_custom_term_on_title(self) -> None:
        titles = [
            "Limited edition USB-C Hub for Laptop Docking",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand, banned_terms=["limited edition"])
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)

    def test_custom_term_on_bullet(self) -> None:
        bullets = [
            "Exclusive offer: USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand, banned_terms=["exclusive offer"])
        assert not result.eligible
        assert any(f.code == "PROMO_BANNED_TERM" for f in result.findings)

    def test_custom_term_no_match_still_eligible(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand, banned_terms=["nonexistent term xyz"])
        assert result.eligible

    def test_multiple_custom_terms(self) -> None:
        bullets = [
            "Clearance sale on USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "Discount price for a limited time only",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand, banned_terms=["clearance", "discount"])
        assert not result.eligible
        promo_terms = [f for f in result.findings if f.code == "PROMO_BANNED_TERM"]
        assert len(promo_terms) >= 2

    def test_custom_terms_no_default_overlap_noise(self) -> None:
        """Custom terms overlapping defaults should not double-flag."""
        bullets = [
            "Free shipping on USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets)
        result = evaluate_candidate(cand, banned_terms=["free shipping"])
        promo_terms = [f for f in result.findings if f.code == "PROMO_BANNED_TERM"]
        assert len(promo_terms) == 1  # not 2


# ── 5. Seller name in title ─────────────────────────────────────────────


class TestSellerNameInTitle:
    def test_seller_name_in_title_fails(self) -> None:
        titles = [
            "Acme USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand, seller_name="Acme")
        assert not result.eligible
        assert any(f.code == "SELLER_NAME_IN_TITLE" for f in result.findings)

    def test_seller_name_casefold_matches(self) -> None:
        titles = [
            "ACME USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand, seller_name="acme")
        assert not result.eligible
        assert any(f.code == "SELLER_NAME_IN_TITLE" for f in result.findings)

    def test_seller_name_none_does_not_fail(self) -> None:
        """Omitting seller_name should not produce seller-name findings."""
        cand = _candidate()
        result = evaluate_candidate(cand)
        assert not any(f.code == "SELLER_NAME_IN_TITLE" for f in result.findings)

    def test_seller_name_substring_in_title_fails(self) -> None:
        """Seller name that is part of a larger word still counts."""
        titles = [
            "AcmeCorp USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand, seller_name="Acme")
        assert not result.eligible
        assert any(f.code == "SELLER_NAME_IN_TITLE" for f in result.findings)

    def test_seller_name_not_present_ok(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand, seller_name="NonExistentBrand")
        assert result.eligible

    def test_empty_seller_name_is_noop(self) -> None:
        """An empty-string seller name should not cause issues."""
        cand = _candidate()
        result = evaluate_candidate(cand, seller_name="")
        assert result.eligible


# ── 6. Duplicate titles ─────────────────────────────────────────────────


class TestDuplicateTitles:
    def test_duplicate_titles_fails(self) -> None:
        titles = [
            "USB-C Hub Multiport Adapter for Laptop Docking",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
            "USB-C Hub Multiport Adapter for Laptop Docking",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "DUPLICATE_TITLES" for f in result.findings)

    def test_casefold_duplicate_detected(self) -> None:
        """Titles differing only in case are considered duplicates."""
        titles = [
            "USB-C Hub Multiport Adapter for Laptop Docking",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
            "usb-c hub multiport adapter for laptop docking",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "DUPLICATE_TITLES" for f in result.findings)

    def test_whitespace_normalized_duplicate(self) -> None:
        """Titles differing only in whitespace are duplicates after strip."""
        titles = [
            "USB-C Hub Multiport Adapter for Laptop",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop and MacBook",
            "  USB-C Hub Multiport Adapter for Laptop  ",
        ]
        cand = _candidate(titles=titles)
        result = evaluate_candidate(cand)
        assert not result.eligible
        assert any(f.code == "DUPLICATE_TITLES" for f in result.findings)

    def test_all_unique_titles_no_finding(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand)
        assert not any(f.code == "DUPLICATE_TITLES" for f in result.findings)


# ── 7. claim_ids ────────────────────────────────────────────────────────


class TestClaimIds:
    def test_empty_claim_ids_does_not_fail(self) -> None:
        cand = _candidate(claim_ids=[])
        result = evaluate_candidate(cand)
        assert result.eligible

    def test_populated_claim_ids_does_not_fail(self) -> None:
        cand = _candidate(claim_ids=["claim-1", "claim-2"])
        result = evaluate_candidate(cand)
        assert result.eligible


# ── Valid candidate (smoke) ──────────────────────────────────────────────


class TestValidCandidate:
    def test_clean_candidate_eligible(self) -> None:
        """A candidate with no hard-gate violations should pass."""
        cand = _candidate()
        result = evaluate_candidate(cand)
        assert result.eligible
        assert all(f.passed for f in result.findings)
        assert isinstance(result, GateResult)

    def test_clean_candidate_with_all_params(self) -> None:
        """Every optional param provided, but no violations triggered."""
        cand = _candidate()
        result = evaluate_candidate(
            cand,
            seller_name="AcmeCorp",
            banned_terms=["clearance", "discount"],
        )
        assert result.eligible

    def test_clean_candidate_no_findings(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand)
        # A fully clean candidate should have zero findings
        assert len(result.findings) == 0

    def test_gate_result_shape(self) -> None:
        cand = _candidate()
        result = evaluate_candidate(cand)
        assert result.candidate_id == "test-cand"
        assert isinstance(result.findings, list)
        assert isinstance(result.eligible, bool)
        for f in result.findings:
            assert isinstance(f, GateFinding)


# ── filter_eligible ─────────────────────────────────────────────────────


class TestFilterEligible:
    def test_filters_ineligible(self) -> None:
        good = _candidate(candidate_id="good")
        bad = CandidateArtifact.model_construct(
            candidate_id="bad",
            lane=WriterLane.SEO,
            titles=_clean_titles(),
            bullets=_clean_bullets(),
            claim_ids=[],
        )
        # Make bad fail by adding a promo title
        bad.titles[0] = "Free Shipping USB-C Hub Multiport Adapter for Laptop"
        eligible = filter_eligible([good, bad])
        assert len(eligible) == 1
        assert eligible[0].candidate_id == "good"

    def test_all_eligible(self) -> None:
        c1 = _candidate(candidate_id="c1")
        c2 = _candidate(candidate_id="c2")
        assert filter_eligible([c1, c2]) == [c1, c2]

    def test_all_ineligible(self) -> None:
        c1 = CandidateArtifact.model_construct(
            candidate_id="c1",
            lane=WriterLane.SEO,
            titles=_clean_titles(),
            bullets=_clean_bullets(),
        )
        c1.titles[0] = "Limited Time Offer USB-C Hub Multiport Adapter"
        c2 = CandidateArtifact.model_construct(
            candidate_id="c2",
            lane=WriterLane.SEO,
            titles=_clean_titles(),
            bullets=_clean_bullets(),
        )
        c2.bullets[0] = "Best seller USB-C hub with great features"
        assert filter_eligible([c1, c2]) == []

    def test_empty_list(self) -> None:
        assert filter_eligible([]) == []

    def test_passes_seller_name_kwarg(self) -> None:
        titles = [
            "Acme USB-C Hub for Laptop Docking Station",
            "USB C Hub Multiport Adapter 7-in-1 for Laptop",
            "7-in-1 USB-C Hub Adapter with PD 100W for Laptop",
        ]
        cand = _candidate(titles=titles, candidate_id="c1")
        eligible = filter_eligible([cand], seller_name="Acme")
        assert len(eligible) == 0

    def test_passes_banned_terms_kwarg(self) -> None:
        bullets = [
            "Clearance sale on USB-C hub for laptop connectivity",
            "100W Power Delivery pass-through charges your laptop",
            "SD/TF card slots support simultaneous access",
            "Compact aluminum design fits perfectly",
            "Plug-and-play setup requires no drivers",
        ]
        cand = _candidate(bullets=bullets, candidate_id="c1")
        eligible = filter_eligible([cand], banned_terms=["clearance"])
        assert len(eligible) == 0

    def test_preserves_order(self) -> None:
        c1 = _candidate(candidate_id="c1")
        c2 = CandidateArtifact.model_construct(
            candidate_id="c2",
            lane=WriterLane.SEO,
            titles=_clean_titles(),
            bullets=_clean_bullets(),
        )
        c2.titles[0] = "Free Shipping USB-C Hub Multiport Adapter"
        c3 = _candidate(candidate_id="c3")
        eligible = filter_eligible([c1, c2, c3])
        assert [c.candidate_id for c in eligible] == ["c1", "c3"]


# ── CandidateArtifact validation boundary ────────────────────────────────


class TestCandidateBoundary:
    def test_titles_too_many_rejected_by_pydantic(self) -> None:
        """4 titles violates CandidateArtifact max_length=3."""
        with pytest.raises(pydantic.ValidationError):
            _candidate(titles=["a", "b", "c", "d"])

    def test_bullets_too_few_rejected_by_pydantic(self) -> None:
        """4 bullets violates CandidateArtifact min_length=5."""
        with pytest.raises(pydantic.ValidationError):
            _candidate(bullets=["a", "b", "c", "d"])
