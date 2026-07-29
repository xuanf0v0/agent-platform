"""Unit tests for post-optimize L1–L6 audit layers (offline)."""

from __future__ import annotations

import json

from amazon_copy.llm import MockLLM
from amazon_copy.schemas import SCORE_DIMENSIONS, OptimizedListingCopy, SourceListingCopy
from amazon_copy.schemas.metrics import plain_len as plain_len_title
from amazon_copy.ui.audit_pipeline import (
    LayerOutput,
    layer_to_dict,
    layers_from_session,
    run_listing_audit_layers,
)
from amazon_copy.ui.view_models import format_layer_sections


def _source() -> SourceListingCopy:
    return SourceListingCopy(
        title="Wireless Earbuds Pro Noise Cancelling",
        bullets=[
            "Bluetooth 5.3 stable connection for daily commute",
            "Active noise cancelling reduces cabin and street noise",
            "24 hour battery life with charging case support",
        ],
    )


def _optimized() -> OptimizedListingCopy:
    return OptimizedListingCopy(
        title="Wireless Earbuds Pro Noise Cancelling Bluetooth 5.3",
        item_highlights="Stable commute audio with ANC and long battery",
        bullets=[
            "Bluetooth 5.3 stable connection for daily commute use",
            "Active noise cancelling reduces cabin and street noise",
            "24 hour battery life with charging case support included",
        ],
    )


class _ScoreLLM:
    """Deterministic scorecard payload matching R11 dimension order."""

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        assert "untrusted" in user.casefold() or "product_input" in user
        scores = [7, 8, 9, 6, 8, 7, 9, 6, 10]
        return json.dumps(
            {
                "dimensions": [
                    {"key": key, "score": score, "rationale": "grounded offline"}
                    for key, score in zip(SCORE_DIMENSIONS, scores, strict=True)
                ],
                "overall": 0,
            }
        )


def test_run_listing_audit_layers_order_and_labels() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    assert [layer.layer_id for layer in layers] == ["L1", "L2", "L3", "L4", "L5", "L6"]
    assert layers[0].title_zh == "L1 输入解析"
    assert layers[1].title_zh == "L2 MCP 市场数据"
    assert layers[2].title_zh == "L3 优化结果摘要"
    assert layers[3].title_zh == "L4 合规审核细则"
    assert layers[4].title_zh == "L5 SEO 检查"
    assert layers[5].title_zh == "L6 九维打分"
    assert layers[1].status == "skipped"
    assert any("跳过" in line for line in layers[1].lines)


def test_l1_and_l3_plain_lengths() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l1 = layers[0]
    l3 = layers[2]
    assert l1.status == "ok"
    assert any("bullet count: 3" in line for line in l1.lines)
    assert any("plain_len" in line for line in l1.lines)
    assert l3.status == "ok"
    assert any("optimized title:" in line for line in l3.lines)
    assert any("bullets: 3" in line for line in l3.lines)
    assert any("title limit: 75" in line for line in l3.lines)
    assert any("item_highlights limit: 125" in line for line in l3.lines)


def test_l4_compliance_lists_rules() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l4 = layers[3]
    assert l4.layer_id == "L4"
    assert any("促销" in line or "规则" in line or "通过" in line for line in l4.lines)
    assert any("已检查规则" in line for line in l4.lines)
    assert any("75" in line for line in l4.lines)


def test_l4_flags_promo_and_trailing_period() -> None:
    dirty = OptimizedListingCopy(
        title="Best Seller Wireless Earbuds Free Shipping!!!",
        item_highlights="Promo heavy",
        bullets=[
            "Amazing quality guaranteed for everyone.",
            "Second bullet without period",
            "Third bullet without period",
        ],
    )
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=dirty,
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l4 = layers[3]
    joined = "\n".join(l4.lines).casefold()
    assert "不通过" in joined or "促销" in joined or "警告" in joined or "fail" in joined
    # Promo/decorative hard-bans or trailing period → hard error on paste-ready L4.
    assert l4.status in {"warn", "error"}


def test_l4_paste_ready_title_over_75_is_error() -> None:
    """Optimized title plain_len 133 → L4 error with length finding (not SOP 100-200)."""
    long_title = ("Wedding Welcome Sign Stand Metal Easel " * 4).strip()
    # Force exact over-cap length used in plan acceptance (133).
    long_title = (long_title + " X")[:133] if plain_len_title(long_title) != 133 else long_title
    if plain_len_title(long_title) != 133:
        long_title = ("W" * 133)
    assert plain_len_title(long_title) == 133
    over = OptimizedListingCopy(
        title=long_title,
        item_highlights="Stable metal easel for acrylic welcome boards at events",
        bullets=[
            "Metal frame supports acrylic welcome signs at ceremonies",
            "Height adjusts for aisles and reception entryways",
            "Folds flat for storage after bridal showers",
        ],
    )
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=over,
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l4 = layers[3]
    assert l4.status == "error"
    joined = "\n".join(l4.lines)
    assert "75" in joined or "长度" in joined
    assert "不通过" in joined or "exceeds" in joined.casefold()
    # Must not treat short-of-SOP-100 as the length gate for this path.
    assert "100-200" not in joined
    assert "sop_seo" not in joined.casefold()


def test_l4_paste_ready_title_70_clean_passes_length() -> None:
    """Title ~70 with no banned claims does not fail paste length."""
    title_70 = "Wedding Welcome Sign Stand Black Metal Easel 60 Inch Adjustable Frame"
    clean = OptimizedListingCopy(
        title=title_70,
        item_highlights=(
            "Adjustable metal easel holds acrylic welcome boards for ceremony "
            "display and photo backdrops."
        ),
        bullets=[
            "Sturdy metal frame supports acrylic welcome signs at events",
            "Height adjusts for ceremony aisles and reception entryways",
            "Includes eight leather straps in black white green and brown",
            "Two fillable water bags add stability on flat indoor floors",
            "Folds flat for storage after bridal showers and seating charts",
        ],
    )
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=clean,
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l4 = layers[3]
    paste_errors = []
    if l4.data is not None:
        raw = l4.data.get("paste_errors", [])
        if isinstance(raw, list):
            paste_errors = [str(e) for e in raw]
    length_hits = [
        e
        for e in paste_errors
        if "length" in e.casefold() or "exceeds" in e.casefold() or "below" in e.casefold()
    ]
    assert length_hits == []
    # Clean paste-ready listing should not be hard-error solely for length.
    assert l4.status in {"ok", "warn"}
    joined = "\n".join(l4.lines)
    assert "标题超过 75" not in joined


def test_l5_seo_vx_rows() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    l5 = layers[4]
    assert l5.status in {"ok", "warn"}
    joined = "\n".join(l5.lines)
    assert "提取意图词" in joined or "提取关键词" in joined
    assert "已覆盖" in joined or "未覆盖" in joined
    assert "覆盖摘要" in joined
    assert "✓" in joined or "✗" in joined


def test_l6_scorecard_with_injected_llm() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
        summary_llm=MockLLM("score_summary_zh"),
    )
    l6 = layers[5]
    assert l6.status == "ok"
    assert any("综合分" in line or "overall" in line.casefold() for line in l6.lines)
    assert l6.data is not None
    assert l6.data.get("overall") == 7.8
    # Chinese dimension labels should appear
    joined = "\n".join(l6.lines)
    assert "合规" in joined or "SEO" in joined
    # Chinese summary should appear
    assert any("【中文总评】" in line for line in l6.lines)
    assert any("【优势】" in line for line in l6.lines)
    assert any("【短板】" in line for line in l6.lines)
    assert any("【建议】" in line for line in l6.lines)


def test_l6_error_does_not_abort_other_layers() -> None:
    class BoomLLM:
        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, user, kwargs
            msg = "scorecard provider sk-secret-key failed"
            raise RuntimeError(msg)

    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=BoomLLM(),
    )
    assert len(layers) == 6
    assert layers[0].status == "ok"
    assert layers[5].status == "error"
    joined = "\n".join(layers[5].lines).casefold()
    assert "sk-secret" not in joined
    assert "layer error" in joined


def test_mockllm_scorecard_role_works() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=MockLLM("scorecard"),
        summary_llm=MockLLM("score_summary_zh"),
    )
    assert layers[5].status == "ok"
    assert any(
        "综合分" in line or "overall" in line.casefold() for line in layers[5].lines
    )
    assert any("【中文总评】" in line for line in layers[5].lines)


def test_layer_session_roundtrip_and_format_sections() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
    )
    serialized = [layer_to_dict(layer) for layer in layers]
    restored = layers_from_session(serialized)
    assert [layer.layer_id for layer in restored] == ["L1", "L2", "L3", "L4", "L5", "L6"]
    sections = format_layer_sections(restored)
    titles = [title for title, _ in sections]
    assert titles[3].startswith("L4 合规审核细则")
    assert "·" in titles[3]
    assert any(isinstance(layer, LayerOutput) for layer in restored)


def test_l4_and_l6_chinese_advice_and_score_summary() -> None:
    layers = run_listing_audit_layers(
        source=_source(),
        optimized=_optimized(),
        mcp_snapshots=[],
        llm=_ScoreLLM(),
        summary_llm=MockLLM("score_summary_zh"),
        advice_llm=MockLLM("compliance_advice_zh"),
    )
    l4 = next(layer for layer in layers if layer.layer_id == "L4")
    l6 = next(layer for layer in layers if layer.layer_id == "L6")
    assert any("【合规结论】" in line for line in l4.lines)
    assert any("【中文总评】" in line for line in l6.lines)
    assert any("建议" in line or "通过" in line or "风险" in line or "合规" in line for line in l4.lines)
    assert any("优势" in line or "短板" in line or "总评" in line for line in l6.lines)
