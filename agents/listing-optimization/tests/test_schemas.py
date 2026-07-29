"""Schema validators: R1 plain length, R4 title, R7/R8 BP, R11 scorecard."""

from __future__ import annotations

import pytest
from amazon_copy.schemas import (
    SCORE_DIMENSIONS,
    SCORE_LABELS_ZH,
    AudienceProfile,
    BulletPoint,
    CompetitorAnalysis,
    EmbedRow,
    FeedbackPack,
    FinalPackage,
    ListingDraft,
    PipelineMode,
    PipelineStage,
    PipelineState,
    ProductInput,
    ResearchPack,
    Scorecard,
    ScoreDimension,
    ScoreDimKey,
    SelectionTrace,
    SellingPoint,
    SEOCheck,
    TitleCandidate,
    TitleMode,
    parse_csv_terms,
    plain_len,
    strip_md_bold,
    validate_bullet_length,
    validate_bullets,
    validate_no_trailing_period,
    validate_title_length,
)
from pydantic import ValidationError

# ── helpers ──────────────────────────────────────────────────────────────────


def _repeat(ch: str, n: int) -> str:
    return ch * n


def _title_of_len(n: int) -> str:
    return _repeat("a", n)


def _bp_of_len(n: int, *, trailing_period: bool = False) -> str:
    body = _repeat("b", n)
    return body if not trailing_period else body[:-1] + "."


def _five_bullets(length: int = 120) -> list[BulletPoint]:
    return [
        BulletPoint.model_validate(
            {"text": _bp_of_len(length), "text_zh": f"卖点{i}"},
            context={"bp_mode": "write"},
        )
        for i in range(5)
    ]


def _scorecard(scores: list[float] | None = None) -> Scorecard:
    vals = scores if scores is not None else [8.0] * 9
    dims = [
        ScoreDimension(key=key, score=val, rationale="ok")
        for key, val in zip(SCORE_DIMENSIONS, vals, strict=True)
    ]
    overall = round(sum(vals) / 9, 1)
    return Scorecard(dimensions=dims, overall=overall)


# ── R1 plain length ──────────────────────────────────────────────────────────


class TestPlainLenWhenMarkdownBold:
    def test_strips_double_star_and_underscore(self) -> None:
        # Given
        marked = "**usb** hub __cable__"
        # When
        plain = strip_md_bold(marked)
        # Then
        assert plain == "usb hub cable"
        assert plain_len(marked) == len("usb hub cable")

    def test_spaces_count(self) -> None:
        assert plain_len("a b") == 3


class TestParseCsvTerms:
    def test_splits_ascii_and_fullwidth_commas(self) -> None:
        assert parse_csv_terms("usb, hub，cable") == ["usb", "hub", "cable"]

    def test_empty_and_whitespace_only(self) -> None:
        assert parse_csv_terms("") == []
        assert parse_csv_terms("  ,  ， ") == []


# ── ProductInput ─────────────────────────────────────────────────────────────


class TestProductInput:
    def test_requires_product(self) -> None:
        with pytest.raises(ValidationError):
            ProductInput(
                product="",
                market="US",
                rootwords=["a"],
                keywords=["b"],
            )

    def test_empty_asin_becomes_none(self) -> None:
        # Given / When
        pi = ProductInput(
            product="USB Hub",
            market="US",
            asin1="",
            asin2="   ",
            asin3="B00TEST",
            asin4=None,
            rootwords=["hub"],
            keywords=["usb"],
        )
        # Then
        assert pi.asin1 is None
        assert pi.asin2 is None
        assert pi.asin3 == "B00TEST"
        assert pi.asin4 is None

    @pytest.mark.parametrize("seller_name", [None, "", "   "])
    def test_empty_seller_name_becomes_none(self, seller_name: str | None) -> None:
        pi = ProductInput(
            product="USB Hub",
            seller_name=seller_name,
            market="US",
            rootwords=["hub"],
            keywords=["usb"],
        )
        assert pi.seller_name is None

    def test_seller_name_is_stripped_without_changing_asin_text(self) -> None:
        pi = ProductInput(
            product="USB Hub",
            seller_name=" USB ",
            market="US",
            asin1=" B00TEST ",
            rootwords=["hub"],
            keywords=["usb"],
        )
        assert pi.seller_name == "USB"
        assert pi.asin1 == " B00TEST "

    def test_rootwords_keywords_min_one(self) -> None:
        with pytest.raises(ValidationError):
            ProductInput(
                product="X",
                market="US",
                rootwords=[],
                keywords=["k"],
            )
        with pytest.raises(ValidationError):
            ProductInput(
                product="X",
                market="US",
                rootwords=["r"],
                keywords=[],
            )

    def test_instruction_missing_flag(self) -> None:
        blank = ProductInput(
            product="X",
            market="US",
            instruction="",
            rootwords=["r"],
            keywords=["k"],
        )
        filled = ProductInput(
            product="X",
            market="US",
            instruction="focus on office",
            rootwords=["r"],
            keywords=["k"],
        )
        assert blank.instruction_missing is True
        assert filled.instruction_missing is False

    def test_csv_coerce_for_rootwords_keywords(self) -> None:
        pi = ProductInput.model_validate(
            {
                "product": "X",
                "market": "US",
                "rootwords": "a, b，c",
                "keywords": "k1，k2",
            },
        )
        assert pi.rootwords == ["a", "b", "c"]
        assert pi.keywords == ["k1", "k2"]


# ── R4 title length ──────────────────────────────────────────────────────────


class TestTitleLengthSopSeo:
    def test_reject_plain_99(self) -> None:
        with pytest.raises(ValueError, match="sop_seo"):
            validate_title_length(_title_of_len(99), TitleMode.SOP_SEO)

    def test_accept_100_and_200(self) -> None:
        validate_title_length(_title_of_len(100), TitleMode.SOP_SEO)
        validate_title_length(_title_of_len(200), TitleMode.SOP_SEO)

    def test_reject_201(self) -> None:
        with pytest.raises(ValueError, match="sop_seo"):
            validate_title_length(_title_of_len(201), TitleMode.SOP_SEO)

    def test_listing_draft_rejects_99_under_sop_seo(self) -> None:
        with pytest.raises(ValidationError):
            ListingDraft.model_validate(
                {
                    "title": _title_of_len(99),
                    "bullets": [{"text": _bp_of_len(120), "text_zh": "x"} for _ in range(5)],
                },
                context={"title_mode": TitleMode.SOP_SEO, "bp_mode": "write"},
            )

    def test_listing_draft_accepts_100(self) -> None:
        draft = ListingDraft(
            title=_title_of_len(100),
            bullets=_five_bullets(120),
        )
        assert draft.title_plain_len == 100

    def test_bold_markers_not_counted_toward_title_len(self) -> None:
        # 100 plain chars wrapped in bold markers → still valid
        body = _title_of_len(100)
        marked = f"**{body}**"
        assert plain_len(marked) == 100
        validate_title_length(marked, TitleMode.SOP_SEO)


class TestTitleLengthStrictAmazon:
    def test_accept_within_1_80(self) -> None:
        validate_title_length(_title_of_len(1), TitleMode.STRICT_AMAZON)
        validate_title_length(_title_of_len(80), TitleMode.STRICT_AMAZON)

    def test_reject_81(self) -> None:
        with pytest.raises(ValueError, match="strict_amazon"):
            validate_title_length(_title_of_len(81), TitleMode.STRICT_AMAZON)


# ── R7 / R8 bullet points ────────────────────────────────────────────────────


class TestBulletPointWriteMode:
    def test_reject_plain_99(self) -> None:
        with pytest.raises(ValidationError):
            BulletPoint.model_validate(
                {"text": _bp_of_len(99)},
                context={"bp_mode": "write"},
            )
        with pytest.raises(ValueError, match="write"):
            validate_bullet_length(_bp_of_len(99), "write")

    def test_reject_plain_151(self) -> None:
        with pytest.raises(ValidationError):
            BulletPoint.model_validate(
                {"text": _bp_of_len(151)},
                context={"bp_mode": "write"},
            )

    def test_accept_100_and_150(self) -> None:
        bp100 = BulletPoint.model_validate(
            {"text": _bp_of_len(100), "text_zh": "百"},
            context={"bp_mode": "write"},
        )
        bp150 = BulletPoint.model_validate(
            {"text": _bp_of_len(150), "text_zh": "百五"},
            context={"bp_mode": "write"},
        )
        assert bp100.plain_len == 100
        assert bp150.plain_len == 150

    def test_reject_trailing_period(self) -> None:
        with pytest.raises(ValidationError):
            BulletPoint.model_validate(
                {"text": _bp_of_len(120, trailing_period=True)},
                context={"bp_mode": "write"},
            )
        with pytest.raises(ValueError, match="must not end"):
            validate_no_trailing_period(_bp_of_len(120, trailing_period=True))

    def test_internal_period_ok(self) -> None:
        # "USB 3.0 " + padding, no trailing period
        core = "USB 3.0 feature pack "
        text = core + _repeat("x", 120 - len(core))
        assert not text.endswith(".")
        assert plain_len(text) == 120
        bp = BulletPoint.model_validate(
            {"text": text},
            context={"bp_mode": "write"},
        )
        assert bp.plain_len == 120


class TestBulletPointOptimizeMode:
    def test_accept_200(self) -> None:
        validate_bullet_length(_bp_of_len(200), "optimize")
        bp = BulletPoint.model_validate(
            {"text": _bp_of_len(200)},
            context={"bp_mode": "optimize"},
        )
        assert bp.plain_len == 200

    def test_reject_201_optimize(self) -> None:
        with pytest.raises(ValueError, match="optimize"):
            validate_bullet_length(_bp_of_len(201), "optimize")

    def test_write_rejects_151_but_optimize_accepts(self) -> None:
        text = _bp_of_len(151)
        with pytest.raises(ValueError, match="write"):
            validate_bullet_length(text, "write")
        validate_bullet_length(text, "optimize")


class TestValidateBulletsHelper:
    def test_validate_bullets_write(self) -> None:
        bullets = _five_bullets(120)
        assert validate_bullets(bullets, "write") is bullets


# ── ListingDraft ─────────────────────────────────────────────────────────────


class TestListingDraft:
    def test_requires_exactly_five_bullets(self) -> None:
        with pytest.raises(ValidationError):
            ListingDraft(
                title=_title_of_len(120),
                bullets=_five_bullets(120)[:4],
            )
        with pytest.raises(ValidationError):
            ListingDraft(
                title=_title_of_len(120),
                bullets=_five_bullets(120) + _five_bullets(120)[:1],
            )

    def test_happy_valid_fixture(self) -> None:
        draft = ListingDraft(
            title=_title_of_len(150),
            title_zh="标题",
            title_candidates=[TitleCandidate(text=_title_of_len(140), text_zh="候选")],
            bullets=_five_bullets(130),
        )
        assert draft.title_plain_len == 150
        assert len(draft.bullets) == 5


# ── Scorecard R11 ────────────────────────────────────────────────────────────


class TestScorecard:
    def test_requires_nine_dims_in_order(self) -> None:
        assert len(SCORE_DIMENSIONS) == 9
        assert SCORE_LABELS_ZH[ScoreDimKey.COMPLIANCE] == "合规性"
        assert SCORE_LABELS_ZH[ScoreDimKey.CTA] == "号召性"

        # wrong count
        with pytest.raises(ValidationError):
            Scorecard(
                dimensions=[ScoreDimension(key=ScoreDimKey.COMPLIANCE, score=5)],
                overall=5.0,
            )

        # wrong order
        shuffled = list(SCORE_DIMENSIONS)
        shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
        dims = [ScoreDimension(key=k, score=5.0) for k in shuffled]
        with pytest.raises(ValidationError):
            Scorecard(dimensions=dims, overall=5.0)

    def test_overall_is_mean_one_decimal(self) -> None:
        scores = [10, 9, 8, 7, 6, 5, 4, 3, 2]  # mean 6.0
        card = _scorecard([float(s) for s in scores])
        assert card.overall == 6.0

        # 1/9 → 0.111… → 0.1
        scores2 = [1.0] + [0.0] * 8
        card2 = _scorecard(scores2)
        assert card2.overall == 0.1

    def test_wrong_overall_rejected(self) -> None:
        dims = [ScoreDimension(key=k, score=9.0) for k in SCORE_DIMENSIONS]
        with pytest.raises(ValidationError):
            Scorecard(dimensions=dims, overall=5.0)

    def test_score_bounds_0_10(self) -> None:
        with pytest.raises(ValidationError):
            ScoreDimension(key=ScoreDimKey.SEO, score=10.1)
        with pytest.raises(ValidationError):
            ScoreDimension(key=ScoreDimKey.SEO, score=-0.1)


# ── Research / SEO / package smoke ───────────────────────────────────────────


class TestResearchAndPackageSmoke:
    def test_empty_competitor_ok(self) -> None:
        pack = ResearchPack(
            audience=AudienceProfile(summary="office workers"),
            competitor=CompetitorAnalysis(),
            feedback=FeedbackPack(),
        )
        assert pack.competitor.parameters == []

    def test_final_package_and_pipeline_state(self) -> None:
        pi = ProductInput(
            product="USB Hub",
            market="US",
            rootwords=["hub"],
            keywords=["usb"],
        )
        sp = SellingPoint(rank=1, text_en="Fast", text_zh="快", rationale="r")
        listing = ListingDraft(
            title=_title_of_len(120),
            bullets=_five_bullets(120),
        )
        seo = SEOCheck(
            intent_rows=[EmbedRow(item="gift", present=True)],
            rootword_rows=[EmbedRow(item="hub", present=True)],
            keyword_rows=[EmbedRow(item="usb", present=False)],
        )
        card = _scorecard()
        final = FinalPackage(
            product_input=pi,
            selling_points=[sp],
            listing=listing,
            seo=seo,
            scorecard=card,
            selection=SelectionTrace(winner_index=0, rationale="seo"),
        )
        assert final.listing is not None
        assert final.scorecard is not None

        state = PipelineState(
            product_input=pi,
            stage=PipelineStage.COMPLETED,
            mode=PipelineMode.RUN,
            listing=listing,
            scorecard=card,
        )
        state.warnings.append("soft")
        assert state.stage == PipelineStage.COMPLETED
        assert TitleMode.SOP_SEO == "sop_seo"
