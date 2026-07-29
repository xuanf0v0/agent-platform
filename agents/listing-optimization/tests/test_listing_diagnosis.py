"""Unit tests for structured source-listing diagnosis reports."""

from __future__ import annotations

import json

from amazon_copy.agents.listing_diagnosis import diagnose_listing
from amazon_copy.review.diagnosis import build_rules_diagnosis
from amazon_copy.review.models import (
    ListingReviewRequest,
    MarketplaceRules,
    VariationRole,
)
from amazon_copy.review.service import review_listing
from amazon_copy.schemas.simple_listing import parse_listing_block


def _wedding_source() -> str:
    return """Wedding Welcome Sign Stand 68 x 31 x 20 Inch Adjustable
Item Highlights:
e water bags for stability
Elegant Gold-Finished Metal Frame: This display stand features a shimmering gold-finished metal frame that adds a touch of sophistication to any event, from weddings to corporate gatherings.
Adjustable Height Options: Choose between two heights— or —to suit your display needs. Simple assembly allows for quick setup and repeated use.
Stable Base: The 31 x 20 inch base, combined with two fillable water bags, helps improve stability when properly assembled on a level surface.
Leather Straps in Four Colors: ws, to securely hold signs up to 1 cm thick.

Backend Search Terms: sign holder easel poster frame display stand adjustable height metal gold finish indoor outdoor event decoration
"""


def _request_from_source(raw: str) -> ListingReviewRequest:
    source = parse_listing_block(raw)
    return ListingReviewRequest(
        title=source.title,
        item_highlights=source.item_highlights,
        bullets=tuple(source.bullets),
        backend_search_terms=source.backend_search_terms,
        rules=MarketplaceRules(marketplace="US", product_type="HOME"),
        variation_role=VariationRole.STANDALONE,
    )


def test_parse_listing_block_keeps_backend_search_terms() -> None:
    source = parse_listing_block(_wedding_source())
    assert "sign holder" in source.backend_search_terms
    assert source.item_highlights.startswith("e water bags")
    assert any("ws," in bullet for bullet in source.bullets)


def test_rules_diagnosis_flags_fragmented_fields() -> None:
    request = _request_from_source(_wedding_source())
    report = review_listing(request)
    diagnosis = build_rules_diagnosis(request, report)

    by_field = {row.field: row for row in diagnosis.field_checks}
    assert by_field["Item Highlights"].status == "BLOCK"
    assert any(row.field.startswith("Bullet") and row.status == "BLOCK" for row in diagnosis.field_checks)
    assert diagnosis.backend.bytes_used > 0
    assert diagnosis.backend.duplication_pct >= 0
    assert diagnosis.average_score >= 0
    assert len(diagnosis.scores) == 10
    assert diagnosis.scoring_source == "rules"
    assert any(issue.level == "P0" for issue in diagnosis.issues)
    assert diagnosis.fix_order


def test_diagnose_listing_merges_llm_editorial_scores() -> None:
    request = _request_from_source(_wedding_source())
    report = review_listing(request)

    class _DiagnosisLLM:
        call_count = 0

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, user, kwargs
            self.call_count += 1
            return json.dumps(
                {
                    "issues": [
                        {
                            "level": "P0",
                            "title": "Item Highlights 是残句",
                            "detail_zh": "e water bags for stability 缺少开头，不能上传。",
                        },
                        {
                            "level": "P1",
                            "title": "标题尺寸含义不够明确",
                            "detail_zh": "买家无法立即判断高度、宽度、深度。",
                        },
                    ],
                    "scores": [
                        {
                            "dimension": key,
                            "score": 6.0 if key != "grammar" else 4.0,
                            "rationale_zh": f"编辑说明 · {key}",
                        }
                        for key in (
                            "compliance",
                            "a9_seo",
                            "semantic_coverage",
                            "grammar",
                            "readability",
                            "selling_points",
                            "localization",
                            "technical_accuracy",
                            "emotional_appeal",
                            "purchase_motivation",
                        )
                    ],
                    "average_score": 5.8,
                    "fix_order": [
                        "立即修复残句和缺失参数——P0。",
                        "定稿可见字段后，重新生成去重的后台词。",
                    ],
                },
                ensure_ascii=False,
            )

    llm = _DiagnosisLLM()
    diagnosis = diagnose_listing(request, report, llm=llm)
    assert llm.call_count == 1
    assert diagnosis.scoring_source == "llm"
    assert diagnosis.issues[0].level == "P0"
    assert diagnosis.issues[0].title.startswith("Item Highlights")
    grammar = next(score for score in diagnosis.scores if score.dimension == "grammar")
    assert grammar.score == 4.0
    assert "编辑说明" in grammar.rationale_zh
    assert diagnosis.average_score == 5.8
    assert len(diagnosis.field_checks) >= 6


def test_diagnose_listing_falls_back_when_llm_fails() -> None:
    request = _request_from_source(_wedding_source())
    report = review_listing(request)

    class _BrokenLLM:
        call_count = 0

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, user, kwargs
            self.call_count += 1
            raise TimeoutError("provider timeout")

    diagnosis = diagnose_listing(request, report, llm=_BrokenLLM())
    assert diagnosis.scoring_source == "rules"
    assert len(diagnosis.scores) == 10
