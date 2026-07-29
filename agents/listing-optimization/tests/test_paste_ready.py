"""Paste-ready policy: 75/125 length gates, claim denylist, accessory ambiguity."""

from __future__ import annotations

from amazon_copy.compliance.paste_ready import (
    PASTE_ITEM_HIGHLIGHTS_MAX,
    PASTE_TITLE_MAX,
    PASTE_TITLE_MIN,
    clamp_paste_ready_lengths,
    clamp_plain_text,
    normalize_dimension_spacing,
    rewrite_stability_absolutes,
    sanitize_paste_ready_listing,
    sanitize_paste_ready_text,
    strip_trailing_incomplete_tail,
    validate_paste_ready_listing,
)
from amazon_copy.utils.text_metrics import plain_len


def _clean_title_70() -> str:
    # 70 plain chars, no banned claims.
    return "Wedding Welcome Sign Stand Black Metal Easel 60 Inch Adjustable Frame"


def _clean_ih_100() -> str:
    body = (
        "Adjustable metal easel holds acrylic welcome boards for ceremony "
        "display and photo backdrops."
    )
    assert plain_len(body) <= PASTE_ITEM_HIGHLIGHTS_MAX
    assert plain_len(body) >= 80
    return body


def _clean_bullets() -> list[str]:
    return [
        "Sturdy metal frame supports acrylic welcome signs at events.",
        "Height adjusts for ceremony aisles and reception entryways.",
        "Includes 8 leather straps in black white green and brown.",
        "Two fillable water bags add stability on flat indoor floors.",
        "Folds flat for storage after bridal showers and seating charts.",
    ]


class TestPasteReadyConstants:
    def test_title_max_is_75_and_ih_max_is_125(self) -> None:
        assert PASTE_TITLE_MAX == 75
        assert PASTE_ITEM_HIGHLIGHTS_MAX == 125
        assert PASTE_TITLE_MIN == 10


class TestClampPasteReadyLengths:
    def test_clamp_plain_text_caps_at_max_and_prefers_word_break(self) -> None:
        # Live UI failure class: title plain length > 75 (e.g. 93)
        long_title = "X" * 93
        assert plain_len(long_title) == 93
        clamped = clamp_plain_text(long_title, PASTE_TITLE_MAX)
        assert plain_len(clamped) <= PASTE_TITLE_MAX
        assert clamped
        assert not clamped.endswith(" ")

        spaced = (
            "Wedding Welcome Sign Stand Black Metal Easel Adjustable Height "
            "Frame With Extra Scene Words Now"
        )
        assert plain_len(spaced) > PASTE_TITLE_MAX
        spaced_out = clamp_plain_text(spaced, PASTE_TITLE_MAX)
        assert plain_len(spaced_out) <= PASTE_TITLE_MAX
        assert " " not in spaced_out[-1:]

    def test_clamp_paste_ready_lengths_caps_title_and_ih(self) -> None:
        title = "A" * 93
        ih = "B" * 140
        out_title, out_ih = clamp_paste_ready_lengths(title, ih)
        assert plain_len(out_title) <= PASTE_TITLE_MAX
        assert plain_len(out_ih) <= PASTE_ITEM_HIGHLIGHTS_MAX
        result = validate_paste_ready_listing(
            out_title,
            out_ih,
            _clean_bullets(),
        )
        length_errors = [
            e
            for e in result.errors
            if "exceeds" in e.casefold() or "plain length" in e.casefold()
        ]
        assert length_errors == []


class TestValidatePasteReadyListingHappyPath:
    def test_clean_short_listing_has_zero_errors(self) -> None:
        title = _clean_title_70()
        ih = _clean_ih_100()
        assert plain_len(title) <= 75
        assert plain_len(title) >= 60
        assert plain_len(ih) <= 125

        result = validate_paste_ready_listing(title, ih, _clean_bullets())
        assert result.errors == []


class TestValidatePasteReadyListingLengthGates:
    def test_title_over_75_errors_mentioning_75_or_title(self) -> None:
        title = "A" * 76
        result = validate_paste_ready_listing(
            title,
            _clean_ih_100(),
            _clean_bullets(),
        )
        assert result.errors
        joined = " ".join(result.errors).lower()
        assert "75" in joined or "title" in joined

    def test_item_highlights_over_125_errors(self) -> None:
        ih = "B" * 126
        result = validate_paste_ready_listing(
            _clean_title_70(),
            ih,
            _clean_bullets(),
        )
        assert result.errors
        assert any("item_highlights" in e.lower() for e in result.errors)

    def test_blank_item_highlights_errors(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            "   ",
            _clean_bullets(),
        )
        assert result.errors
        assert any("item_highlights" in e.lower() for e in result.errors)


class TestTitleTailAndDimensions:
    def test_strip_trailing_with_count(self) -> None:
        assert strip_trailing_incomplete_tail(
            "Gold Wedding Welcome Sign Stand Adjustable with 8",
        ) == "Gold Wedding Welcome Sign Stand Adjustable"
        assert strip_trailing_incomplete_tail("Stand Frame for") == "Stand Frame"

    def test_clamp_drops_with_8_stub(self) -> None:
        # Clamp to 75 then strip incomplete "with 8" tail (audit BLOCK class).
        long_title = (
            "Gold Wedding Welcome Sign Stand, 68 x 31 x 20 Inches, Adjustable "
            "with 8 leather straps"
        )
        assert plain_len(long_title) > PASTE_TITLE_MAX
        out = clamp_plain_text(long_title, PASTE_TITLE_MAX)
        assert plain_len(out) <= PASTE_TITLE_MAX
        assert not out.casefold().endswith("with 8")
        assert not out.casefold().endswith(" with")
        assert "with 8" not in out.casefold()

    def test_normalize_dimension_spacing_triple_and_pair(self) -> None:
        assert normalize_dimension_spacing("Base 68x31x20 inches") == (
            "Base 68 x 31 x 20 inches"
        )
        assert normalize_dimension_spacing("Sign 31X20 board") == "Sign 31 x 20 board"
        # Already spaced stays stable.
        assert "68 x 31 x 20" in normalize_dimension_spacing("68 x 31 x 20 Inches")

    def test_stability_absolute_soft_rewrite(self) -> None:
        raw = (
            "The 31 x 20 inch base ensures reliable stability on various surfaces."
        )
        out = rewrite_stability_absolutes(raw)
        assert "ensures reliable stability" not in out.casefold()
        assert "helps improve stability" in out.casefold()
        assert "various surfaces" not in out.casefold()
        assert "level surfaces" in out.casefold()

    def test_sanitize_listing_dims_tail_and_stability(self) -> None:
        title = (
            "Gold Wedding Welcome Sign Stand 68x31x20 Inches Adjustable Height "
            "Frame with 8"
        )
        ih = "Pack includes straps and bags for events and more detail filler words " * 3
        bullets = [
            "Base ensures reliable stability on various surfaces when filled.",
            "Height 68x31 pair is not a triple.",
        ]
        t, i, b = sanitize_paste_ready_listing(title, ih, bullets)
        assert plain_len(t) <= PASTE_TITLE_MAX
        assert plain_len(i) <= PASTE_ITEM_HIGHLIGHTS_MAX
        assert "with 8" not in t.casefold()
        assert "68 x 31 x 20" in t or "68 x 31" in t
        assert "ensures reliable" not in b[0].casefold()
        assert "helps improve stability" in b[0].casefold()
        result = validate_paste_ready_listing(t, i, b)
        length_errors = [e for e in result.errors if "exceeds" in e.casefold()]
        assert length_errors == []


class TestSanitizePasteReadyClaims:
    def test_dual_tone_excised_from_bullet(self) -> None:
        raw = (
            "Color Options: dual-tone straps in black white green and brown "
            "for seasonal styling."
        )
        cleaned = sanitize_paste_ready_text(raw)
        assert "dual-tone" not in cleaned.casefold()
        assert "dual tone" not in cleaned.casefold()
        assert "black" in cleaned.casefold()

    def test_sanitize_listing_clears_denylist_and_passes_validate(self) -> None:
        title = "Stand with Dual-Tone Frame Wind-Resistant Finish"
        ih = "Anti-rust metal base for long-term outdoor breezy conditions."
        bullets = [
            "Includes dual tone leather straps.",
            "8 leather and water bags for events.",
            "Weighted base keeps the easel steady.",
        ]
        t, i, b = sanitize_paste_ready_listing(
            title,
            ih,
            bullets,
            allow_weighted_base=False,
        )
        result = validate_paste_ready_listing(t, i, b, allow_weighted_base=False)
        assert result.errors == []
        assert all("dual" not in x.casefold() for x in [t, i, *b])
        assert all("wind" not in x.casefold() for x in [t, i, *b])
        assert all("8 leather and water" not in x.casefold() for x in [t, i, *b])
        assert all("weighted base" not in x.casefold() for x in [t, i, *b])


class TestValidatePasteReadyListingClaimDenylist:
    def test_bullet_wind_resistant_is_error(self) -> None:
        bullets = _clean_bullets()
        bullets[0] = "Wind-Resistant frame for outdoor ceremonies."
        result = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            bullets,
        )
        assert result.errors
        joined = " ".join(result.errors).casefold()
        assert "wind" in joined

    def test_accessory_ambiguity_leather_and_water_bags(self) -> None:
        title = "Stand with 8 leather and water bags for events"
        result = validate_paste_ready_listing(
            title,
            _clean_ih_100(),
            _clean_bullets(),
        )
        assert result.errors
        joined = " ".join(result.errors).casefold()
        assert "accessory" in joined or "leather" in joined

    def test_weighted_base_errors_unless_allowed(self) -> None:
        bullets = _clean_bullets()
        bullets[1] = "Weighted base keeps the easel steady indoors."
        denied = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            bullets,
            allow_weighted_base=False,
        )
        assert denied.errors
        assert any("weighted base" in e.casefold() for e in denied.errors)

        allowed = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            bullets,
            allow_weighted_base=True,
        )
        assert not any("weighted base" in e.casefold() for e in allowed.errors)


class TestItemHighlightsFragmentDetection:
    """IH fragment completeness checks added for generation quality."""

    def test_ih_starting_with_lowercase_is_fragment_error(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            "screws, and a 31 x 20 inch base",
            _clean_bullets(),
        )
        assert result.errors
        assert any("fragment" in e.casefold() or "lowercase" in e.casefold() for e in result.errors)

    def test_ih_starting_with_and_is_fragment_error(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            "and a sturdy metal frame for events",
            _clean_bullets(),
        )
        assert result.errors
        assert any("fragment" in e.casefold() or "and" in e.casefold() for e in result.errors)

    def test_complete_ih_starts_with_uppercase_and_passes(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            "Includes 8 leather straps in 4 colors, 2 water bags, and a 31 x 20 inch base.",
            _clean_bullets(),
        )
        assert not result.errors


class TestBulletQualityChecks:
    """Deterministic bullet quality flags for filler and truncation."""

    def test_and_more_filler_triggers_error(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            ["Compatible with acrylic, foam board, and more."],
        )
        assert result.errors
        assert any("and more" in e.casefold() for e in result.errors)

    def test_bullet_truncation_at_preposition_triggers_error(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            ["Holds signs up to 1 cm thick for events under"],
        )
        assert result.errors
        assert any("truncation" in e.casefold() or "dangling" in e.casefold() for e in result.errors)

    def test_complete_bullet_sentences_pass(self) -> None:
        result = validate_paste_ready_listing(
            _clean_title_70(),
            _clean_ih_100(),
            [
                "Sturdy metal frame with gold-finished surface for events.",
                "Adjustable height from 48 to 68 inches for versatile display.",
            ],
        )
        assert not result.errors

    def test_sanitization_clears_filler_and_recapitalizes(self) -> None:
        """After ban removal, re-capitalize the first letter of item_highlights."""
        title, ih, bullets = sanitize_paste_ready_listing(
            "Anti-Rust Display Stand",
            "anti-rust metal base with stable design",
            ["Fits foam board signs up to 1 cm thick for indoor use."],
        )
        assert "anti-rust" not in ih.casefold()
        assert "anti-rust" not in title.casefold()
        # IH should start with uppercase after sanitization.
        if ih:
            assert ih[0].isupper()
