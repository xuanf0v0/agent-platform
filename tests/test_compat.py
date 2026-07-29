"""Tests for the ``amazon_copy.compat`` compatibility layer."""

from __future__ import annotations

import pytest
from amazon_copy.compat import (
    CompatError,
    product_input_to_studio_request,
    report_to_optimized_listing,
    source_listing_to_studio_request,
)
from amazon_copy.schemas import OptimizedListingCopy, ProductInput, SourceListingCopy
from amazon_copy.schemas.studio_output import (
    AuditMetadata,
    BulletOption,
    FailureOutcome,
    NoWinnerOutcome,
    OptimizationReport,
    SuccessOutcome,
    TitleOption,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_product() -> ProductInput:
    return ProductInput(
        product="Premium Coffee Maker 12-Cup with Thermal Carafe",
        market="US",
        instruction="Focus on durability and rich flavor extraction",
        rootwords=["coffee", "maker", "brewer", "thermal", "carafe"],
        keywords=["coffee maker", "drip coffee", "automatic brewer", "thermal carafe"],
    )


def _sample_source() -> SourceListingCopy:
    return SourceListingCopy(
        title="ReePlan 10PCS Large Scallop Shells for Crafts",
        bullets=[
            "Natural sea shells for coastal decorating",
            "4-5 inch size perfect for DIY projects",
            "White seashells bulk pack for crafting",
        ],
    )


def _sample_report() -> OptimizationReport:
    return OptimizationReport(
        title_options=(
            TitleOption(text="Premium Coffee Maker 12-Cup with Thermal Carafe"),
            TitleOption(text="Premium Coffee Maker with Thermal Carafe Brewer"),
            TitleOption(text="Premium Coffee Maker for Home Barista"),
        ),
        bullets=(
            BulletOption(text="Rich flavor brewing technology for perfect extraction"),
            BulletOption(text="Thermal carafe keeps coffee hot for hours"),
            BulletOption(text="Easy-clean removable filter basket"),
            BulletOption(text="Auto shut-off safety feature for peace of mind"),
            BulletOption(text="Brews up to 12 cups for entertaining guests"),
        ),
        description="Premium drip coffee maker with double-wall thermal carafe.",
        search_terms="coffee maker brewer thermal carafe drip automatic",
        analysis=(
            "The product excels in thermal retention and brewing quality. "
            "Customer reviews highlight the durable build and consistent "
            "flavor extraction as key differentiators."
        ),
        audit=AuditMetadata(run_id="test-run-001", request_hash="abc123def456"),
    )


# ---------------------------------------------------------------------------
# CompatError
# ---------------------------------------------------------------------------


class TestCompatError:
    def test_is_value_error(self) -> None:
        error = CompatError("something went wrong")
        assert isinstance(error, ValueError)

    def test_stores_reason(self) -> None:
        error = CompatError("test reason")
        assert error.reason == "test reason"

    def test_string_representation(self) -> None:
        error = CompatError("my reason")
        assert str(error) == "my reason"


# ---------------------------------------------------------------------------
# product_input_to_studio_request
# ---------------------------------------------------------------------------


class TestProductInputToStudioRequest:
    def test_returns_studio_request(self) -> None:
        product = _sample_product()
        result = product_input_to_studio_request(product)
        assert result.title == product.product
        assert len(result.bullets) >= 1
        # instruction should appear in one of the bullets
        all_text = " ".join(result.bullets).casefold()
        assert "durability" in all_text
        # keywords should appear
        assert "coffee maker" in all_text

    def test_without_instruction(self) -> None:
        product = ProductInput(
            product="Basic Widget",
            market="US",
            instruction="",
            rootwords=["widget"],
            keywords=["widget", "gadget"],
        )
        result = product_input_to_studio_request(product)
        assert result.title == "Basic Widget"
        assert len(result.bullets) >= 1

    def test_uses_parse_studio_request(self) -> None:
        """Verify the function goes through parse_studio_request by checking
        the StudioRequest shape (hash, assertions, template)."""
        product = _sample_product()
        result = product_input_to_studio_request(product)
        assert result.request_hash  # non-empty hash present
        assert len(result.seller_assertions) >= 1  # title assertion
        # evidence gaps for missing asin/brand/category
        assert len(result.evidence_gaps) >= 1


# ---------------------------------------------------------------------------
# source_listing_to_studio_request
# ---------------------------------------------------------------------------


class TestSourceListingToStudioRequest:
    def test_round_trips_title_and_bullets(self) -> None:
        source = _sample_source()
        result = source_listing_to_studio_request(source)
        assert result.title == source.title
        assert len(result.bullets) == len(source.bullets)

    def test_preserves_bullet_order(self) -> None:
        source = _sample_source()
        result = source_listing_to_studio_request(source)
        for result_bullet, source_bullet in zip(result.bullets, source.bullets, strict=True):
            assert result_bullet == source_bullet

    def test_returns_frozen_instance(self) -> None:
        source = _sample_source()
        result = source_listing_to_studio_request(source)
        # StudioRequest model_config has frozen=True
        assert result.model_config.get("frozen") is True


# ---------------------------------------------------------------------------
# report_to_optimized_listing
# ---------------------------------------------------------------------------


class TestReportToOptimizedListing:
    def test_maps_success_outcome(self) -> None:
        report = _sample_report()
        outcome = SuccessOutcome(report=report)
        result = report_to_optimized_listing(outcome)

        assert isinstance(result, OptimizedListingCopy)
        assert result.title == report.title_options[0].text
        assert len(result.bullets) == 5
        assert result.bullets == [b.text for b in report.bullets]
        assert result.item_highlights == report.description

    def test_maps_degraded_outcome(self) -> None:
        report = _sample_report()
        outcome = SuccessOutcome(report=report)
        result = report_to_optimized_listing(outcome)

        assert result.title == report.title_options[0].text
        assert len(result.bullets) == 5

    def test_uses_description_for_item_highlights(self) -> None:
        """When description is present, item_highlights uses it (not analysis)."""
        report = _sample_report()
        outcome = SuccessOutcome(report=report)
        result = report_to_optimized_listing(outcome)
        assert result.item_highlights == report.description
        assert result.item_highlights != report.analysis[:120]

    def test_raises_compat_error_on_no_winner(self) -> None:
        outcome = NoWinnerOutcome(reason="no viable candidate found")
        with pytest.raises(CompatError) as exc_info:
            report_to_optimized_listing(outcome)
        assert exc_info.value.reason == "no_winner"

    def test_raises_compat_error_on_failure(self) -> None:
        outcome = FailureOutcome(reason="LLM provider returned an error")
        with pytest.raises(CompatError) as exc_info:
            report_to_optimized_listing(outcome)
        assert exc_info.value.reason == "no_winner"
