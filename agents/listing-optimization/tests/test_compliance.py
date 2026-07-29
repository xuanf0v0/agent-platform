"""R10 hard-ban compliance scanner and mode-aware title/BP validators."""

from __future__ import annotations

from amazon_copy.compliance.check import (
    ComplianceHit,
    ValidationResult,
    scan_title_hard_bans,
    validate_bullets,
    validate_title,
)
from amazon_copy.schemas import BulletPoint, TitleMode, plain_len


def _bp_of_len(n: int, *, trailing_period: bool = False) -> str:
    body = "b" * n
    return body if not trailing_period else body[:-1] + "."


class TestScanTitleHardBansWhenPromoDecorativeSubjective:
    def test_best_seller_free_shipping_hub_bangs_has_hits(self) -> None:
        title = "Best Seller Free Shipping Hub!!!"
        hits = scan_title_hard_bans(title)
        assert len(hits) >= 1
        categories = {h.category for h in hits}
        assert categories & {"promo", "decorative", "subjective"}
        phrases_lower = {h.phrase.lower() for h in hits}
        assert any("free shipping" in p or "best seller" in p for p in phrases_lower) or any(
            h.category == "decorative" for h in hits
        )

    def test_clean_product_title_zero_hard_promo_decorative(self) -> None:
        title = "USB-C Hub 7-in-1 Multiport Adapter for Laptop Docking"
        hits = scan_title_hard_bans(title)
        hard = [h for h in hits if h.category in ("promo", "decorative")]
        assert hard == []

    def test_case_insensitive_promo_phrase(self) -> None:
        hits = scan_title_hard_bans("Cable FREE SHIPPING Included")
        assert any(h.category == "promo" for h in hits)

    def test_copyright_marks_hit_as_decorative(self) -> None:
        hits = scan_title_hard_bans("Brand Widget Kit marked with symbols")
        # inject marks
        hits = scan_title_hard_bans("Brand\u00ae Widget\u2122 Kit \u00a92024")
        assert any(h.category == "decorative" for h in hits)
        assert any(h.phrase in {"\u00ae", "\u2122", "\u00a9"} for h in hits)


class TestValidateTitleModeAware:
    def test_strict_rejects_all_caps_and_non_title_case(self) -> None:
        all_caps = validate_title(
            "USB C HUB MULTIPORT ADAPTER FOR LAPTOP",
            TitleMode.STRICT_AMAZON,
        )
        assert any("all caps" in error.lower() for error in all_caps.errors)

        sentence_case = validate_title(
            "USB C Hub multiport adapter for Laptop",
            TitleMode.STRICT_AMAZON,
        )
        assert any("title case" in error.lower() for error in sentence_case.errors)

    def test_strict_rejects_known_seller_name_without_external_inference(self) -> None:
        result = validate_title(
            "Acme USB C Hub Multiport Adapter for Laptop",
            TitleMode.STRICT_AMAZON,
            seller_name="Acme",
        )
        assert any("seller name" in error.lower() for error in result.errors)

    def test_promo_always_hard_error(self) -> None:
        title = "USB Hub Free Shipping Multiport Dock Adapter Cable"
        assert plain_len(title) >= 10
        result = validate_title(title, TitleMode.SOP_SEO)
        assert isinstance(result, ValidationResult)
        assert result.errors
        assert any("promo" in e.lower() or "free shipping" in e.lower() for e in result.errors)

    def test_decorative_always_hard_error(self) -> None:
        result = validate_title("USB Hub Adapter!!! Dock Station", TitleMode.SOP_SEO)
        assert result.errors
        assert any("decorative" in e.lower() or "!" in e for e in result.errors)

    def test_subjective_warning_in_sop_seo(self) -> None:
        title = "Best Seller USB-C Hub Multiport Laptop Dock"
        result = validate_title(title, TitleMode.SOP_SEO)
        assert not any(
            "subjective" in e.lower() or "best seller" in e.lower() for e in result.errors
        )
        assert result.warnings
        assert any("subjective" in w.lower() or "best seller" in w.lower() for w in result.warnings)

    def test_subjective_error_in_strict_amazon(self) -> None:
        title = "Best Seller USB Hub"
        result = validate_title(title, TitleMode.STRICT_AMAZON)
        assert result.errors
        assert any("subjective" in e.lower() or "best seller" in e.lower() for e in result.errors)

    def test_min_plain_length_10(self) -> None:
        result = validate_title("USB Hub", TitleMode.STRICT_AMAZON)
        assert any("10" in e or "short" in e.lower() or "min" in e.lower() for e in result.errors)

    def test_clean_title_no_hard_errors(self) -> None:
        title = "USB-C Hub 7-in-1 Multiport Adapter for Laptop Docking Station"
        result = validate_title(title, TitleMode.SOP_SEO)
        hard_hits = [h for h in result.hits if h.category in ("promo", "decorative")]
        assert hard_hits == []
        assert not any("promo" in e.lower() or "decorative" in e.lower() for e in result.errors)

    def test_mode_string_accepted(self) -> None:
        result = validate_title(
            "USB-C Hub 7-in-1 Multiport Adapter for Laptop",
            "strict_amazon",
        )
        assert isinstance(result, ValidationResult)


class TestValidateBulletsTrailingPeriodAndLength:
    def test_trailing_period_fails_bp(self) -> None:
        bullets = [_bp_of_len(120, trailing_period=True)]
        result = validate_bullets(bullets, "write")
        assert result.errors
        assert any("period" in e.lower() or "." in e for e in result.errors)

    def test_usb_30_internal_period_ok(self) -> None:
        core = "USB 3.0 feature pack "
        text = core + ("x" * (120 - len(core)))
        assert not text.endswith(".")
        assert plain_len(text) == 120
        result = validate_bullets([text], "write")
        assert not any("period" in e.lower() for e in result.errors)

    def test_write_mode_rejects_too_short(self) -> None:
        result = validate_bullets([_bp_of_len(99)], "write")
        assert result.errors
        assert any(
            "99" in e or "write" in e.lower() or "length" in e.lower() for e in result.errors
        )

    def test_optimize_accepts_200(self) -> None:
        result = validate_bullets([_bp_of_len(200)], "optimize")
        assert not any("length" in e.lower() or "optimize" in e.lower() for e in result.errors)

    def test_accepts_bullet_point_models(self) -> None:
        bp = BulletPoint.model_validate(
            {"text": _bp_of_len(120), "text_zh": "point"},
            context={"bp_mode": "write"},
        )
        result = validate_bullets([bp], "write")
        assert result.errors == []

    def test_happy_clean_write_bullets(self) -> None:
        bullets = [_bp_of_len(120) for _ in range(5)]
        result = validate_bullets(bullets, "write")
        assert result.errors == []
        assert result.hits == []


class TestComplianceHitShape:
    def test_hit_has_required_fields(self) -> None:
        hits = scan_title_hard_bans("Free Shipping USB Hub")
        assert hits
        hit = hits[0]
        assert isinstance(hit, ComplianceHit)
        assert hit.phrase
        assert hit.category
        assert hit.severity
