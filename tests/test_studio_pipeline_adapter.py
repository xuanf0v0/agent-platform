"""Tests for package_from_studio_state — mapping StudioState → FinalPackage."""

from __future__ import annotations

from amazon_copy.orchestrator import (
    StudioState,
    package_from_studio_state,
)
from amazon_copy.orchestrator.state import StudioState as StudioStateCls
from amazon_copy.schemas import FinalPackage
from amazon_copy.schemas.agents import CandidateArtifact, WriterLane


def _winner_state(
    *,
    titles: list[str] | None = None,
    bullets: list[str] | None = None,
    outcome: str = "success",
) -> StudioStateCls:
    """Build a StudioState with a synthetic winner."""
    winner = CandidateArtifact(
        candidate_id="test-candidate-1",
        lane=WriterLane.SEO,
        titles=titles or [
            "Premium USB-C Hub 7-in-1 — 4K HDMI, PD 100W",
            "Best USB C Hub Multiport Adapter for MacBook Pro",
            "USB C Hub 7-in-1 with 4K HDMI and 100W PD Charging",
        ],
        bullets=bullets or [
            "7-in-1 USB-C hub expands your laptop with HDMI, PD charging, SD card reader and more",
            "Crystal-clear 4K HDMI output for stunning presentations and extended displays",
            "100W Power Delivery lets you charge your laptop while using all hub ports simultaneously",
            "Compact aluminum design matches your MacBook and fits easily in any laptop bag",
            "Universal compatibility with Thunderbolt 3/4 and USB-C Windows and Mac laptops",
        ],
    )
    return StudioStateCls(
        request_text="USB C Hub",
        run_id="test-run-001",
        winner=winner,
        outcome=outcome,  # type: ignore[arg-type]
    )


class TestPackageFromStudioState:
    """Unit tests for the studio-to-legacy adapter."""

    def test_success_state_returns_package_with_listing(self) -> None:
        state = _winner_state()
        package = package_from_studio_state(state)
        assert package is not None
        assert package.listing is not None
        assert package.listing.title == state.winner.titles[0]  # type: ignore[union-attr]
        assert len(package.listing.title_candidates) == 3
        assert len(package.listing.bullets) == 5
        assert package.stage.value == "completed"
        assert package.error is None

    def test_title_candidates_match_winner_titles(self) -> None:
        titles = ["Title A", "Title B", "Title C"]
        state = _winner_state(titles=titles)
        package = package_from_studio_state(state)
        assert package is not None
        candidate_texts = [tc.text for tc in package.listing.title_candidates]
        assert candidate_texts == titles

    def test_bullets_map_correctly(self) -> None:
        bullets = [
            "Bullet one describes a key feature",
            "Bullet two highlights a benefit",
            "Bullet three addresses a pain point",
            "Bullet four covers compatibility",
            "Bullet five is a call to action",
        ]
        state = _winner_state(bullets=bullets)
        package = package_from_studio_state(state)
        assert package is not None
        assert [bp.text for bp in package.listing.bullets] == bullets

    def test_no_winner_returns_none(self) -> None:
        state = _winner_state(outcome="no_winner")
        state2 = StudioStateCls(
            request_text="USB C Hub",
            run_id="test-run-002",
            winner=None,
            outcome="no_winner",
        )
        assert package_from_studio_state(state) is None
        assert package_from_studio_state(state2) is None

    def test_failure_outcome_returns_none(self) -> None:
        state = StudioStateCls(
            request_text="USB C Hub",
            run_id="test-run-003",
            winner=None,
            outcome="failure",
            errors=["Something went wrong"],
        )
        assert package_from_studio_state(state) is None

    def test_degraded_outcome_returns_none(self) -> None:
        state = StudioStateCls(
            request_text="USB C Hub",
            run_id="test-run-004",
            winner=None,
            outcome="degraded",
        )
        assert package_from_studio_state(state) is None

    def test_product_input_is_optional(self) -> None:
        state = _winner_state()
        package = package_from_studio_state(state)
        assert package is not None
        assert package.product_input.product == "USB C Hub"

    def test_custom_product_input_is_respected(self) -> None:
        from amazon_copy.schemas import ProductInput

        custom = ProductInput(
            product="Custom Product",
            market="US",
            instruction="Test",
            rootwords=["test"],
            keywords=["test product"],
        )
        state = _winner_state()
        package = package_from_studio_state(state, product_input=custom)
        assert package is not None
        assert package.product_input.product == "Custom Product"

    def test_returned_package_is_frozen(self) -> None:
        state = _winner_state()
        package = package_from_studio_state(state)
        assert package is not None
        assert package.model_config.get("frozen") is True

    def test_stage_history_contains_only_completed(self) -> None:
        state = _winner_state()
        package = package_from_studio_state(state)
        assert package is not None
        assert package.stage_history == ["completed"]
