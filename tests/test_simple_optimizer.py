from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from amazon_copy import simple_optimizer
from amazon_copy.llm import MockLLM
from amazon_copy.review.models import (
    EvidenceSource,
    FactClaim,
    ListingReviewRequest,
    MarketplaceRules,
)
from amazon_copy.schemas import OptimizedListingCopy, SourceListingCopy
from amazon_copy.schemas.simple_listing import split_verified_facts_from_listing
from amazon_copy.simple_optimizer import (
    CopyPointsParseError,
    SimpleOptimizerError,
    format_optimized_listing,
    optimize_listing,
    parse_copy_points,
    parse_listing_block,
)
from amazon_copy.utils.text_metrics import plain_len
from pydantic import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterator


SOURCE = SourceListingCopy(
    title=(
        "ReePlan 10PCS Large Scallop Shells for Crafts, 4-5 Inch Natural Sea Shells "
        "for Decorating, White Seashells Bulk for DIY Crafting"
    ),
    bullets=[f"Original shell bullet {index}" for index in range(1, 6)],
)


class _SequenceLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses: Iterator[str] = iter(responses)
        self._call_count = 0
        self.requests: list[dict[str, object]] = []

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user
        self._call_count += 1
        self.requests.append(kwargs)
        return next(self._responses)


def test_copy_points_parser_handles_middot_sample() -> None:
    raw = "· First shell benefit\n· Second shell benefit\n· Third shell benefit"

    assert parse_copy_points(raw) == [
        "First shell benefit",
        "Second shell benefit",
        "Third shell benefit",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1. First line\ncontinuation\n2) Second line", ["First line continuation", "Second line"]),
        ("First line\nSecond line\nThird line", ["First line", "Second line", "Third line"]),
        (
            "First paragraph\nwraps here\n\nSecond paragraph",
            ["First paragraph wraps here", "Second paragraph"],
        ),
    ],
)
def test_copy_points_parser_handles_numbered_continuations_and_plain_text(
    raw: str, expected: list[str]
) -> None:
    assert parse_copy_points(raw) == expected


@pytest.mark.parametrize("raw", ["", "\n".join(f"- Point {index}" for index in range(11))])
def test_copy_points_parser_rejects_empty_and_more_than_ten(raw: str) -> None:
    with pytest.raises(CopyPointsParseError):
        parse_copy_points(raw)


def test_split_verified_facts_from_listing_inline_and_block() -> None:
    listing, facts = split_verified_facts_from_listing(
        "标题：支架\n五点\n· 第一条\n· 第二条\n\n"
        "事实：8 leather straps black/white/green/brown 2 each; 2 water bags"
    )
    assert "事实" not in listing
    assert "标题：支架" in listing
    assert facts is not None
    assert "8 leather straps" in facts
    assert "2 water bags" in facts

    bare, none_facts = split_verified_facts_from_listing("标题：支架\n· 一条")
    assert none_facts is None
    assert "标题：支架" in bare

    multi_listing, multi_facts = split_verified_facts_from_listing(
        "Title: Stand\n- Bullet one\n\nVerified facts:\n"
        "8 straps four colors\n2 fillable bags\n\n"
        "事实：glossy gold finish"
    )
    assert multi_facts is not None
    assert "8 straps" in multi_facts
    assert "glossy gold" in multi_facts
    assert "Verified" not in multi_listing
    assert "事实" not in multi_listing


def test_listing_block_parser_captures_chinese_labels_and_middot_layout() -> None:
    # Given: one whole listing pasted with Chinese labels and middot points
    raw = "标题：贝壳手工套装\n\n五点\n· 第一条。\n· 第二条。\n· 第三条。\n· 第四条。\n· 第五条。"

    # When: the source crosses the whole-block parser boundary
    source = parse_listing_block(raw)

    # Then: title, points, and typed layout are captured without inventing a section
    assert source.title == "贝壳手工套装"
    assert source.bullets == ["第一条。", "第二条。", "第三条。", "第四条。", "第五条。"]
    assert source.format_template.title_label == "标题："
    assert source.format_template.title_label_position == "same_line"
    assert source.format_template.section_label == "五点"
    assert source.format_template.bullet_marker == "·"
    assert source.format_template.blank_line_between_points is False
    assert source.format_template.terminal_punctuation == "。"


def test_listing_block_formatter_adds_required_highlights_to_chinese_middot_shape() -> None:
    # Given: a parsed source with no Item Highlights section
    source = parse_listing_block(
        "标题：原始标题\n五点\n" + "\n".join(f"· 原始点 {i}" for i in range(1, 6))
    )
    result = OptimizedListingCopy(
        title="优化标题",
        item_highlights="不应显示的摘要",
        bullets=[f"优化点 {i}" for i in range(1, 6)],
    )

    # When: the typed result is formatted for copy
    formatted = format_optimized_listing(result, source.format_template)

    # Then: required highlights precede the source-recognizable five-point section
    assert formatted == (
        "标题：优化标题\nItem Highlights:\n不应显示的摘要\n五点\n"
        + "\n".join(f"· 优化点 {i}" for i in range(1, 6))
    )


@pytest.mark.parametrize(
    ("marker", "expected_marker"),
    [("1.", "1."), ("1)", "1)"), ("-", "-"), ("", "")],
)
def test_listing_block_parser_and_formatter_retain_recognizable_variants(
    marker: str, expected_marker: str
) -> None:
    # Given: a whole listing using one of the supported marker layouts
    lines = [f"{marker}{' ' if marker else ''}Point {index}" for index in range(1, 4)]
    source = parse_listing_block("Source title\n" + "\n".join(lines))
    result = OptimizedListingCopy(
        title="Updated title",
        item_highlights="unused",
        bullets=[f"Updated {index}" for index in range(1, 4)],
    )

    # When: the result is rendered against its source template
    formatted = format_optimized_listing(result, source.format_template)

    # Then: the same marker family and point count are present
    output_lines = formatted.splitlines()
    assert output_lines[0] == "Updated title"
    assert output_lines[1:3] == ["Item Highlights:", "unused"]
    assert len(output_lines[3:]) == 3
    if expected_marker:
        assert output_lines[3].startswith(expected_marker)
    else:
        assert output_lines[3] == "Updated 1"


def test_listing_block_parser_rejects_empty_input() -> None:
    # Given/When/Then: an empty whole-listing paste is invalid
    with pytest.raises(CopyPointsParseError):
        parse_listing_block("\n  \n")


def test_optimized_listing_accepts_variable_bullet_count() -> None:
    # Given: a complete simplified listing result
    payload = {
        "title": "ReePlan 10 Pack Large Natural Scallop Shells",
        "item_highlights": "Natural shells for painting and coastal decor.",
        "bullets": [f"Optimized bullet {index}." for index in range(1, 4)],
    }

    # When: the response crosses the typed boundary
    result = OptimizedListingCopy.model_validate(payload)

    # Then: the six copy fields are retained exactly
    assert result.title == payload["title"]
    assert result.item_highlights == payload["item_highlights"]
    assert result.bullets == payload["bullets"]


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " ", "item_highlights": "Useful", "bullets": ["x"] * 5},
        {"title": "Valid", "item_highlights": " ", "bullets": ["x"] * 5},
        {"title": "Valid", "item_highlights": "Useful", "bullets": []},
        {"title": "Valid", "item_highlights": "Useful", "bullets": ["x"] * 11},
        {"title": "Valid", "item_highlights": "Useful", "bullets": ["x"] * 4 + [" "]},
    ],
)
def test_optimized_listing_rejects_incomplete_output(payload: dict[str, str | list[str]]) -> None:
    # Given/When/Then: incomplete provider output cannot cross the boundary
    with pytest.raises(ValidationError):
        OptimizedListingCopy.model_validate(payload)


def test_listing_optimizer_uses_one_dedicated_mock_role_call() -> None:
    # Given: the dedicated offline optimizer role
    llm = MockLLM("listing_optimizer")

    # When: one source listing is optimized
    result = optimize_listing(SOURCE, llm=llm)

    # Then: one model call produces the complete typed contract
    assert llm.call_count == 1
    assert len(result.bullets) == 5
    assert result.item_highlights


def test_baseline_whole_listing_represents_title_and_variable_points() -> None:
    # Given: a complete pasted listing represented by the old two-field boundary
    raw_points = "\n".join(f"· Original shell point {index}" for index in range(1, 6))
    source = SourceListingCopy(
        title="ReePlan natural scallop shells for crafts",
        bullets=parse_copy_points(raw_points),
    )

    # When: the unchanged simplified optimizer receives the source shape
    result = optimize_listing(source, llm=MockLLM("listing_optimizer"))

    # Then: the typed source and deterministic fixture retain all five points
    assert source.title == "ReePlan natural scallop shells for crafts"
    assert len(source.bullets) == 5
    assert len(result.bullets) == len(source.bullets)


def test_automatic_optimization_public_api_is_callable() -> None:
    # Given: the backend module consumed by the Streamlit workflow
    automatic_runner = getattr(simple_optimizer, "run_automatic_optimization", None)

    # When/Then: automatic research/review/optimization has one reusable entry point
    assert callable(automatic_runner)


def test_listing_optimizer_retries_count_mismatch_once() -> None:
    # Given: one malformed response followed by a valid response
    three_source = SourceListingCopy(title=SOURCE.title, bullets=SOURCE.bullets[:3])
    mismatch = OptimizedListingCopy(
        title="Wrong count",
        item_highlights="Useful",
        bullets=["One", "Two"],
    ).model_dump_json()
    valid = OptimizedListingCopy(
        title="ReePlan 10 Pack Large Natural Scallop Shells",
        item_highlights="Natural shells for painting and coastal decor.",
        bullets=[f"Optimized bullet {index}." for index in range(1, 4)],
    ).model_dump_json()
    llm = _SequenceLLM([mismatch, valid])

    # When: provider validation fails on the first attempt
    result = optimize_listing(three_source, llm=llm)

    # Then: exactly one repair call is allowed
    assert result.title.startswith("ReePlan")
    assert len(result.bullets) == 3
    assert llm.call_count == 2


def test_listing_optimizer_reserves_output_budget_for_reasoning_models() -> None:
    # Given: a valid response from a provider that may spend completion tokens on reasoning
    llm = _SequenceLLM([_paste_ready_listing(title="Natural Scallop Shells for Crafts")])

    # When: the listing optimizer requests structured output
    optimize_listing(SOURCE, llm=llm)

    # Then: the completion budget leaves room for reasoning and the final JSON payload
    assert llm.requests[0]["max_tokens"] == 4096


def test_listing_optimizer_stops_after_one_failed_retry() -> None:
    # Given: two malformed provider responses
    llm = _SequenceLLM(["not json", "still not json"])

    # When/Then: the service raises a safe typed error after two calls
    with pytest.raises(SimpleOptimizerError):
        optimize_listing(SOURCE, llm=llm)
    assert llm.call_count == 2


def _paste_ready_listing(
    *,
    title: str,
    item_highlights: str = "Natural shells for painting and coastal decor.",
    bullet_count: int = 5,
) -> str:
    return OptimizedListingCopy(
        title=title,
        item_highlights=item_highlights,
        bullets=[f"Optimized bullet {index}." for index in range(1, bullet_count + 1)],
    ).model_dump_json()


def test_listing_optimizer_clamps_overlong_title_and_ih_without_repair() -> None:
    # Given: model returns title 93 / IH 140 (live UI failure class) but no bans
    overlong_title = "Wedding Welcome Sign Stand " + ("Metal Easel Frame " * 4)
    overlong_ih = (
        "Adjustable metal easel holds acrylic welcome boards for ceremony "
        "display photo backdrops reception entry and extra filler words "
        "for shoppers who need more detail."
    )
    assert plain_len(overlong_title) >= 93
    assert plain_len(overlong_ih) >= 140
    llm = _SequenceLLM(
        [
            _paste_ready_listing(
                title=overlong_title,
                item_highlights=overlong_ih,
            ),
        ]
    )

    # When: only length budgets are violated
    result = optimize_listing(SOURCE, llm=llm)

    # Then: deterministic clamp fixes length; no second LLM call
    assert plain_len(result.title) <= 75
    assert plain_len(result.item_highlights) <= 125
    assert llm.call_count == 1


def test_listing_optimizer_strips_truncated_with_count_title_tail() -> None:
    # Given: overlong title that clamps into "... with 8" (audit BLOCK class)
    overlong_title = (
        "Gold Wedding Welcome Sign Stand, 68x31x20 Inches, Adjustable Height "
        "Frame with 8 leather straps extra words"
    )
    assert plain_len(overlong_title) > 75
    llm = _SequenceLLM(
        [
            _paste_ready_listing(
                title=overlong_title,
                item_highlights="8 leather straps and 2 water bags for events.",
            ),
        ]
    )

    result = optimize_listing(SOURCE, llm=llm)

    assert plain_len(result.title) <= 75
    assert "with 8" not in result.title.casefold()
    assert "68 x 31 x 20" in result.title
    assert llm.call_count == 1


def test_listing_optimizer_strips_banned_claims_without_repair() -> None:
    # Given: model keeps dual-tone / wind-resistant (live UI failure class)
    banned_title = "ReePlan Wind-Resistant Large Natural Scallop Shells Pack"
    banned_bullet = "Color Options: dual-tone straps in black white green and brown."
    assert "wind-resistant" in banned_title.casefold()
    assert "dual-tone" in banned_bullet.casefold()
    payload = OptimizedListingCopy(
        title=banned_title,
        item_highlights="Natural shells for painting and coastal decor.",
        bullets=[
            "Optimized bullet 1.",
            "Optimized bullet 2.",
            "Optimized bullet 3.",
            banned_bullet,
            "Optimized bullet 5.",
        ],
    ).model_dump_json()
    llm = _SequenceLLM([payload])

    # When: denylist phrases are present after a successful parse
    result = optimize_listing(SOURCE, llm=llm)

    # Then: deterministic sanitize removes bans; no second LLM call
    assert plain_len(result.title) <= 75
    assert "wind-resistant" not in result.title.casefold()
    assert all("dual-tone" not in b.casefold() for b in result.bullets)
    assert all("dual tone" not in b.casefold() for b in result.bullets)
    assert len(result.bullets) == 5
    assert llm.call_count == 1


def test_listing_optimizer_raises_when_paste_ready_repair_still_invalid() -> None:
    # Given: model returns blank item_highlights twice (sanitize cannot invent IH
    # from nothing without violating NonBlank → we use stub, so need another gate).
    # Use too-few bullets after parse is blocked by format; instead force
    # validate failure via empty title after sanitize of claim-only title that
    # collapses — policy fills a stub, so raise path needs residual length min
    # failure: title shorter than PASTE_TITLE_MIN after sanitize + stub edge.
    # Practical residual: inject via monkey by returning IH that becomes blank
    # and title that is too short when only punctuation remains.
    short_bad = OptimizedListingCopy(
        title="Ab",  # below PASTE_TITLE_MIN after no sanitize change
        item_highlights="Natural shells for painting and coastal decor.",
        bullets=[f"Optimized bullet {i}." for i in range(1, 6)],
    ).model_dump_json()
    llm = _SequenceLLM([short_bad, short_bad])

    # When/Then: after one paste-ready repair the service fails closed
    with pytest.raises(SimpleOptimizerError, match="可粘贴校验未通过"):
        optimize_listing(SOURCE, llm=llm)
    assert llm.call_count == 2


def test_listing_optimizer_includes_verified_facts_when_nonempty() -> None:
    # Given: a sequence LLM that records the first user payload
    class _CaptureLLM(_SequenceLLM):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.users: list[str] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.users.append(user)
            self._call_count += 1
            return next(self._responses)

    good = _paste_ready_listing(title="ReePlan 10 Pack Large Natural Scallop Shells")
    llm = _CaptureLLM([good])

    # When: verified_facts is a non-empty stripped string
    optimize_listing(
        SOURCE,
        llm=llm,
        verified_facts="  product has weighted base and 8 straps  ",
    )

    # Then: the user JSON includes verified_facts (stripped)
    payload = json.loads(llm.users[0])
    assert payload["verified_facts"] == "product has weighted base and 8 straps"


def test_listing_optimizer_omits_blank_verified_facts() -> None:
    # Given: blank verified_facts should not appear in the user JSON
    class _CaptureLLM(_SequenceLLM):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.users: list[str] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.users.append(user)
            self._call_count += 1
            return next(self._responses)

    good = _paste_ready_listing(title="ReePlan 10 Pack Large Natural Scallop Shells")
    llm = _CaptureLLM([good])

    # When: verified_facts is whitespace-only
    optimize_listing(SOURCE, llm=llm, verified_facts="   ")

    # Then: verified_facts key is absent
    payload = json.loads(llm.users[0])
    assert "verified_facts" not in payload


def test_review_context_expands_to_supported_bullets_and_preserves_keywords() -> None:
    # Given: a category supporting five bullets and three fact-poor source points
    source = SourceListingCopy(
        title="Natural River Rocks for Painting",
        bullets=[
            "Smooth natural stones for prepared painting surfaces",
            "Natural shape and color vary from stone to stone",
            "Finished projects can become garden markers or desk decorations",
        ],
    )
    request = ListingReviewRequest(
        title=source.title,
        bullets=tuple(source.bullets),
        rules=MarketplaceRules(product_type="ART_CRAFT_MATERIAL", supported_bullet_count=5),
        primary_terms=("painting rocks", "river rocks"),
        secondary_terms=("craft stones",),
    )

    class _CaptureLLM(_SequenceLLM):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.users: list[str] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.users.append(user)
            self._call_count += 1
            return next(self._responses)

    llm = _CaptureLLM(
        [
            _paste_ready_listing(
                title="Natural River Rocks for Painting and Craft Projects",
                bullet_count=5,
            )
        ]
    )

    # When: evidence-aware optimization consumes the resolved review context
    result = optimize_listing(source, llm=llm, review_request=request)

    # Then: the marketplace upload count and allowed terms reach generation
    payload = json.loads(llm.users[0])
    assert payload["target_bullet_count"] == 5
    assert len(result.bullets) == 5
    assert payload["allowed_keywords"] == ["painting rocks", "river rocks", "craft stones"]
    assert result.backend_search_terms == "painting rocks river craft stones"


def test_third_party_product_fact_is_not_injected_into_generation() -> None:
    # Given: priority-6 market research that attempts to assert product material
    request = ListingReviewRequest(
        title=SOURCE.title,
        bullets=tuple(SOURCE.bullets),
        rules=MarketplaceRules(product_type="CRAFT_SHELL"),
        claims=(
            FactClaim(
                key="material",
                value="granite",
                source=EvidenceSource.THIRD_PARTY_PUBLIC_DATA,
                sku_scope="all",
            ),
        ),
    )

    class _CaptureLLM(_SequenceLLM):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.users: list[str] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.users.append(user)
            self._call_count += 1
            return next(self._responses)

    llm = _CaptureLLM([_paste_ready_listing(title="ReePlan 10 Pack Large Natural Scallop Shells")])

    # When: the optimizer resolves evidence before constructing the LLM request
    optimize_listing(SOURCE, llm=llm, review_request=request)

    # Then: rejected product research is absent from resolved facts and prompt data
    payload = json.loads(llm.users[0])
    assert "granite" not in json.dumps(payload, ensure_ascii=False)


def test_backend_search_terms_are_deterministic_utf8_byte_bounded() -> None:
    # Given: more multilingual allowlisted terms than the backend byte budget permits
    builder = getattr(simple_optimizer, "build_backend_search_terms", None)
    assert callable(builder)
    terms = tuple(f"绘画石头{i}" for i in range(40))

    # When: terms are normalized twice
    first = builder(terms, max_bytes=250)
    second = builder(terms, max_bytes=250)

    # Then: output is stable, whole-token, and at most 250 UTF-8 bytes
    assert first == second
    assert len(first.encode("utf-8")) <= 250
    assert first.split()[-1] in terms


def test_backend_search_terms_global_cap_overrides_custom_500_byte_rule() -> None:
    # Given: enough allowlisted terms to exceed 250 bytes and a 500-byte request
    terms = tuple(f"paintingterm{index:03d}" for index in range(40))

    # When: the deterministic builder receives the category-specific budget
    result = simple_optimizer.build_backend_search_terms(terms, max_bytes=500)

    # Then: the global machine-consumed field invariant remains 250 UTF-8 bytes
    assert len(result.encode("utf-8")) <= 250


def test_optimizer_clamps_category_search_budget_to_global_250_bytes() -> None:
    # Given: a review rule allows 500 bytes and provides more than 250 bytes of terms
    terms = tuple(f"paintingterm{index:03d}" for index in range(40))
    request = ListingReviewRequest(
        title=SOURCE.title,
        bullets=tuple(SOURCE.bullets),
        rules=MarketplaceRules(
            product_type="CRAFT_SHELL",
            backend_search_terms_max_bytes=500,
        ),
        primary_terms=terms,
    )
    llm = _SequenceLLM(
        [_paste_ready_listing(title="ReePlan 10 Pack Large Natural Scallop Shells")]
    )

    # When: the optimizer derives backend terms from the resolved request
    result = optimize_listing(SOURCE, llm=llm, review_request=request)

    # Then: output never exceeds the global cap
    assert len(result.backend_search_terms.encode("utf-8")) <= 250


def test_fact_poor_three_bullet_source_uses_supported_five_point_shape() -> None:
    # Given: three source bullets and no resolved product facts for expansion
    source = SourceListingCopy(
        title="Natural River Rocks for Painting",
        bullets=[
            "Smooth natural stones for prepared painting surfaces",
            "Natural shape and color vary from stone to stone",
            "Finished projects can become garden markers or desk decorations",
        ],
    )
    request = ListingReviewRequest(
        title=source.title,
        bullets=tuple(source.bullets),
        rules=MarketplaceRules(product_type="ART_CRAFT_MATERIAL", supported_bullet_count=5),
    )

    class _CaptureLLM(_SequenceLLM):
        def __init__(self, responses: list[str]) -> None:
            super().__init__(responses)
            self.payloads: list[dict[str, object]] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.payloads.append(json.loads(user))
            self._call_count += 1
            return next(self._responses)

    response = _paste_ready_listing(
        title="Natural River Rocks for Painting and Craft Projects",
        bullet_count=5,
    )
    llm = _CaptureLLM([response, response])

    # When: generation resolves the target count
    result = optimize_listing(source, llm=llm, review_request=request)

    # Then: existing facts are redistributed into the five-point upload shape
    assert llm.payloads[0]["target_bullet_count"] == 5
    assert len(result.bullets) == 5
    assert llm.call_count == 1


def test_five_distinct_resolved_fact_tasks_allow_expansion_to_five() -> None:
    # Given: three source bullets plus five priority-4 facts covering distinct decision tasks
    source = SourceListingCopy(
        title="Natural River Rocks for Painting",
        bullets=["Prepared painting surface", "Natural variation", "Garden display ideas"],
    )
    claims = tuple(
        FactClaim(
            key=key,
            value=value,
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        )
        for key, value in (
            ("surface", "smooth surface"),
            ("size", "2 inch stones"),
            ("method", "suitable for paint"),
            ("display", "garden decoration"),
            ("variation", "natural shape varies"),
        )
    )
    request = ListingReviewRequest(
        title=source.title,
        bullets=tuple(source.bullets),
        rules=MarketplaceRules(product_type="ART_CRAFT_MATERIAL", supported_bullet_count=5),
        claims=claims,
    )
    llm = _SequenceLLM(
        [
            _paste_ready_listing(
                title="Natural River Rocks for Painting and Craft Projects",
                bullet_count=5,
            )
        ]
    )

    # When: generation resolves the fact-supported target
    result = optimize_listing(source, llm=llm, review_request=request)

    # Then: expansion reaches the category-supported five bullets
    assert len(result.bullets) == 5


@pytest.mark.parametrize(
    "negative_value",
    ["not proven to have a weighted base", "weighted base is not supported"],
)
def test_qualified_negative_weighted_base_fact_cannot_authorize_affirmative_copy(
    negative_value: str,
) -> None:
    # Given: structured priority-4 evidence qualifies its negative weighted-base finding
    request = ListingReviewRequest(
        title=SOURCE.title,
        bullets=tuple(SOURCE.bullets),
        rules=MarketplaceRules(product_type="CRAFT_SHELL"),
        claims=(
            FactClaim(
                key="base",
                value=negative_value,
                source=EvidenceSource.PACKAGING_BOM_USER,
                sku_scope="all",
            ),
        ),
    )
    payload = OptimizedListingCopy(
        title="ReePlan 10 Pack Large Natural Scallop Shells",
        item_highlights="Natural shells for painting and coastal decor.",
        bullets=[
            "Weighted base supports a stable craft display.",
            *[f"Optimized bullet {index}." for index in range(2, 6)],
        ],
    ).model_dump_json()

    # When: model output asserts the opposite affirmative feature
    result = optimize_listing(SOURCE, llm=_SequenceLLM([payload]), review_request=request)

    # Then: deterministic policy strips the unsupported phrase
    assert "weighted base" not in " ".join(result.bullets).casefold()
