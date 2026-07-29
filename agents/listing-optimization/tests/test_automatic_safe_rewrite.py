from amazon_copy.automatic_models import EvidenceBundle
from amazon_copy.automatic_safe_rewrite import safely_rewrite_output, safely_rewrite_source
from amazon_copy.review.models import ReviewFinding
from amazon_copy.schemas import OptimizedListingCopy, SourceListingCopy

from tests.specialized_ui_support import report


def test_unauthorized_generated_bom_benefit_is_removed_conservatively() -> None:
    # Given: generated copy turns confirmed accessories into an unverified stability benefit.
    phrase = "Includes leather straps and water bags for added stability"
    listing = OptimizedListingCopy(
        title="Wedding Welcome Sign Stand",
        item_highlights=f"{phrase}.",
        bullets=[f"CONTENTS: {phrase}.", "Gold metal frame for event signs"],
        backend_search_terms="",
    )
    blocked_report = report(status="BLOCK", can_optimize=False, disposition="terminal").model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNAUTHORIZED_NEW_FACT",
                    severity="BLOCK",
                    field="item_highlights",
                    message_zh="unsupported BOM benefit",
                    fact_key="bom",
                    claim_terms=(phrase,),
                ),
            ),
            "fact_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    # When: deterministic postflight repair applies conservative deletion.
    rewritten = safely_rewrite_output(listing, blocked_report)

    # Then: the unsupported phrase is gone without leaving a required field blank.
    assert rewritten.item_highlights == listing.title
    assert rewritten.bullets == ["Gold metal frame for event signs"]


def test_postflight_format_and_promotion_blocks_are_repaired_without_terminating() -> None:
    # Given: generated copy has an overlong title and retains a promotional source phrase.
    listing = OptimizedListingCopy(
        title=(
            "DALTACK 10 Large Natural River Rocks for Painting, Flat Smooth Stones "
            "for Arts and Crafting Projects"
        ),
        item_highlights="Natural stones for painting and craft projects",
        bullets=["KINDNESS ROCKS: Join the viral trend with painted stones"],
        backend_search_terms="painting rocks craft stones",
    )
    blocked_report = report(status="BLOCK", can_optimize=False, disposition="terminal").model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="TITLE_LENGTH",
                    severity="BLOCK",
                    field="title",
                    message_zh="title too long",
                ),
                ReviewFinding(
                    code="PROMOTION_PRICE",
                    severity="BLOCK",
                    field="listing",
                    message_zh="promotional phrase",
                    claim_terms=("viral trend",),
                ),
            ),
            "format_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    # When: deterministic postflight repair runs.
    rewritten = safely_rewrite_output(listing, blocked_report)

    # Then: both safe-to-repair blocks are removed instead of terminating the workflow.
    assert len(rewritten.title) <= 75
    assert "viral trend" not in " ".join(rewritten.bullets).casefold()


def test_listing_level_unverified_safe_claim_is_removed_from_actual_field() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Natural stones for painting and craft projects",
        bullets=["Easy Painting: Safe rocks with smooth painting surfaces"],
        backend_search_terms="painting rocks craft stones",
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="terminal"
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNVERIFIED_SAFETY",
                    severity="BLOCK",
                    field="listing",
                    message_zh="存在未经证实的安全宣称：safe",
                    claim_terms=("safe",),
                ),
            ),
            "fact_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    rewritten = safely_rewrite_output(listing, blocked_report)

    assert "safe" not in " ".join(rewritten.bullets).casefold()
    assert rewritten.bullets == [
        "Easy Painting: rocks with smooth painting surfaces"
    ]


def test_source_title_over_length_is_clamped() -> None:
    # Given: source title exceeds the paste-ready 75-char limit.
    source = SourceListingCopy(
        title=(
            "Gold Wedding Welcome Sign Stand with Adjustable Height 68 x 31 x 20 Inch "
            "Metal Frame Floor Display for Reception Events Parties"
        ),
        item_highlights="Gold floor stand for wedding welcome signs",
        bullets=["Adjustable height: 53'' to 68''", "Sturdy metal frame for indoor events"],
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="auto_repair",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="TITLE_LENGTH",
                    severity="BLOCK",
                    field="title",
                    message_zh="标题超过75字符硬限制",
                ),
            ),
            "format_status": "BLOCK",
        }
    )
    evidence = EvidenceBundle()

    # When: source safe-rewrite clamps the title.
    repaired = safely_rewrite_source(source, blocked_report, evidence)

    # Then: title is clamped to ≤75 chars; IH and bullets are preserved.
    assert len(repaired.title) <= 75
    assert repaired.item_highlights == source.item_highlights
    assert repaired.bullets == source.bullets


def test_source_highlights_over_length_is_clamped() -> None:
    # Given: source item_highlights exceeds the paste-ready 125-char limit.
    source = SourceListingCopy(
        title="Wedding Welcome Sign Stand",
        item_highlights=(
            "Gold metal frame display stand with 8 leather straps in black, brown, tan, "
            "and cream colors plus 2 fillable water bags for outdoor stability on grass, "
            "patio, or deck surfaces"
        ),
        bullets=["Adjustable height: 53'' to 68''"],
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="auto_repair",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="HIGHLIGHTS_LENGTH",
                    severity="BLOCK",
                    field="item_highlights",
                    message_zh="Item Highlights超过125字符硬限制",
                ),
            ),
            "format_status": "BLOCK",
        }
    )
    evidence = EvidenceBundle()

    # When: source safe-rewrite clamps the item_highlights.
    repaired = safely_rewrite_source(source, blocked_report, evidence)

    # Then: IH is clamped to ≤125 chars; title and bullets are preserved.
    assert len(repaired.item_highlights) <= 125
    assert repaired.title == source.title
    assert repaired.bullets == source.bullets


def test_source_rewrite_removes_conservatively_suppressed_specialized_facts() -> None:
    source = SourceListingCopy(
        title="Adjustable Wedding Sign Stand 68 x 31 x 20 Inch",
        item_highlights="Includes two fillable water bags",
        bullets=[
            "Two height options: 5.7ft meters and 4ft meters",
            "Weighted base measuring 31 x 20 inches",
            "Securely holds signs up to 1 cm thick",
        ],
    )
    evidence = EvidenceBundle(
        suppressed_claim_terms=(
            "5.7ft meters and 4ft meters",
            "31 x 20 inches",
            "1 cm thick",
            "two fillable water bags",
        )
    )

    repaired = safely_rewrite_source(source, report(), evidence)

    visible = " ".join(
        (repaired.title, repaired.item_highlights, *repaired.bullets)
    ).casefold()
    assert "5.7ft meters and 4ft meters" not in visible
    assert "31 x 20 inches" not in visible
    assert "1 cm thick" not in visible
    assert "two fillable water bags" not in visible


def test_source_title_and_highlights_both_clamped() -> None:
    # Given: both title and IH exceed their paste-ready limits.
    source = SourceListingCopy(
        title=(
            "Gold Wedding Welcome Sign Stand with Adjustable Height 68 x 31 x 20 Inch "
            "Metal Frame Floor Display Stand for Reception Events and Party Decorations"
        ),
        item_highlights=(
            "Elegant gold-finished floor display stand with 8 premium leather straps in "
            "four classic colors (black, brown, tan, cream) plus 2 heavy-duty fillable "
            "water bags for enhanced outdoor stability and wind resistance on any surface"
        ),
        bullets=["Adjustable height: 53'' to 68''"],
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="auto_repair",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="TITLE_LENGTH",
                    severity="BLOCK",
                    field="title",
                    message_zh="标题超过75字符硬限制",
                ),
                ReviewFinding(
                    code="HIGHLIGHTS_LENGTH",
                    severity="BLOCK",
                    field="item_highlights",
                    message_zh="Item Highlights超过125字符硬限制",
                ),
            ),
            "format_status": "BLOCK",
        }
    )
    evidence = EvidenceBundle()

    # When: source safe-rewrite clamps both fields.
    repaired = safely_rewrite_source(source, blocked_report, evidence)

    # Then: both fields are within their limits.
    assert len(repaired.title) <= 75
    assert len(repaired.item_highlights) <= 125
    assert repaired.bullets == source.bullets


def test_truncated_unauthorized_bom_phrase_removed_via_substring_fallback() -> None:
    # Given: the fact-candidate extractor limits BOM matches to 60 chars, so
    # claim_terms are a truncated prefix of the actual listing text (e.g.
    # "...ages 2-" vs "...ages 2-6 Years Old").  A word-boundary regex cannot
    # match a mid-word truncation — the substring fallback must kick in.
    full_ih_text = (
        "Includes shoulder harness with arm wings for kids 22-66 lbs, ages 2-6 Years Old"
    )
    truncated_claim = "Includes shoulder harness with arm wings for kids 22-66 lbs, ages 2-"

    listing = OptimizedListingCopy(
        title="Toddler Swim Vest",
        item_highlights=full_ih_text,
        bullets=["Designed for Kids 22-66 lbs & Ages 2-6"],
        backend_search_terms="kids swim vest toddler floaties",
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="terminal",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNAUTHORIZED_NEW_FACT",
                    severity="BLOCK",
                    field="item_highlights",
                    message_zh="生成文案新增未授权bom事实",
                    fact_key="bom",
                    claim_terms=(truncated_claim,),
                ),
            ),
            "fact_status": "BLOCK",
            "format_status": "PASS",
            "release_disposition": "block",
        }
    )

    # When: deterministic postflight repair runs.
    rewritten = safely_rewrite_output(listing, blocked_report)

    # Then: the unauthorized BOM claim is gone (even though only a truncated
    # prefix was supplied as the claim_term).
    unfolded = rewritten.item_highlights.casefold()
    assert "shoulder harness" not in unfolded
    assert "arm wings" not in unfolded
    # Title and bullets should be preserved (the claim is only in item_highlights).
    assert rewritten.title == listing.title
    assert rewritten.bullets == listing.bullets


def test_exact_phrase_match_still_works_when_boundaries_align() -> None:
    # Given: full exact phrase that aligns with word boundaries — the primary
    # regex path should handle it (regression check after adding substring fallback).
    phrase = "Includes leather straps for outdoor use"
    listing = OptimizedListingCopy(
        title="Wedding Welcome Sign Stand",
        item_highlights=f"{phrase}. Sturdy metal frame.",
        bullets=["Gold-finished for events"],
        backend_search_terms="",
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="terminal",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNAUTHORIZED_NEW_FACT",
                    severity="BLOCK",
                    field="item_highlights",
                    message_zh="unsupported BOM",
                    fact_key="bom",
                    claim_terms=(phrase,),
                ),
            ),
            "fact_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    rewritten = safely_rewrite_output(listing, blocked_report)

    # The exact phrase is gone; the rest of the text remains.
    assert phrase.casefold() not in rewritten.item_highlights.casefold()
    assert "sturdy metal frame" in rewritten.item_highlights.casefold()


def test_short_suppressed_terms_do_not_clip_larger_words() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Stones for Painting",
        item_highlights="Each piece measures 2-3 inches wide.",
        bullets=["Natural Stones: Includes 10 stones for craft projects."],
        backend_search_terms="river stones painting",
    )

    rewritten = safely_rewrite_output(
        listing,
        report(status="PASS", can_optimize=True),
        suppressed_claim_terms=("stone", "inc"),
    )

    assert rewritten.title == listing.title
    assert rewritten.item_highlights == listing.item_highlights
    assert rewritten.bullets == listing.bullets


def test_unauthorized_claim_in_title_is_removed_in_place() -> None:
    # Given: the generated title itself contains the unauthorized BOM claim.
    # The old ``contaminated_title`` shortcut cleared the title to "" before
    # removal, so the fallback ``title or highlights or listing.title`` always
    # brought back the original (still-contaminated) listing.title — the claim
    # survived every retry.  Now _remove_terms runs on the real title.
    claim_phrase = "Includes 4 leather straps and 2 water bags"
    listing = OptimizedListingCopy(
        title=f"Gold Sign Stand {claim_phrase} for Events",
        item_highlights=f"{claim_phrase}. Sturdy metal frame.",
        bullets=["Gold-finished for weddings and receptions"],
        backend_search_terms="sign stand event display",
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="terminal",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNAUTHORIZED_NEW_FACT",
                    severity="BLOCK",
                    field="title",
                    message_zh="生成文案新增未授权bom事实",
                    fact_key="bom",
                    claim_terms=(claim_phrase,),
                ),
            ),
            "fact_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    rewritten = safely_rewrite_output(listing, blocked_report)

    # The unauthorized claim must be gone from both title and highlights.
    assert claim_phrase.casefold() not in rewritten.title.casefold()
    assert claim_phrase.casefold() not in rewritten.item_highlights.casefold()
    # The title should still contain the legitimate product name.
    assert "gold sign stand" in rewritten.title.casefold()
    # Highlights should keep the non-claim content.
    assert "sturdy metal frame" in rewritten.item_highlights.casefold()


def test_truncated_unauthorized_claim_in_title_is_removed_via_substring_fallback() -> None:
    # Given: the title contains the full unauthorized text but the claim_term is
    # a truncated prefix (as extracted by the fact-candidate BOM pattern limited
    # to 60 chars).  The substring fallback must remove it from the title.
    full_title = "Wedding Sign Stand with 4 Leather Straps and 2 Fillable Water Bags for Events"
    truncated_claim = "Wedding Sign Stand with 4 Leather Straps and 2 Fillable Wa"

    listing = OptimizedListingCopy(
        title=full_title,
        item_highlights="Gold metal frame for event display.",
        bullets=["Adjustable height for any venue"],
        backend_search_terms="wedding sign stand",
    )
    blocked_report = report(
        status="BLOCK", can_optimize=False, disposition="terminal",
    ).model_copy(
        update={
            "findings": (
                ReviewFinding(
                    code="UNAUTHORIZED_NEW_FACT",
                    severity="BLOCK",
                    field="title",
                    message_zh="生成文案新增未授权bom事实",
                    fact_key="bom",
                    claim_terms=(truncated_claim,),
                ),
            ),
            "fact_status": "BLOCK",
            "release_disposition": "block",
        }
    )

    rewritten = safely_rewrite_output(listing, blocked_report)

    # The unauthorized text (full and truncated) must be gone from the title.
    assert "4 leather straps" not in rewritten.title.casefold()
    assert "fillable water bags" not in rewritten.title.casefold()
    # Other fields are untouched.
    assert rewritten.item_highlights == listing.item_highlights
    assert rewritten.bullets == listing.bullets
