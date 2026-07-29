from __future__ import annotations

# Streamlit AppTest calls intentionally return handles that are not consumed.
# pyright: reportUnusedCallResult=false
import hashlib
from typing import TYPE_CHECKING

from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationResult,
    CompletedOptimization,
    EvidenceBundle,
    NeedsClarification,
)
from amazon_copy.review.models import ClarificationQuestion
from amazon_copy.specialized_rules.models import (
    SpecializedRuleCache,
    SpecializedRuleGap,
    SpecializedRuleSnapshot,
)
from amazon_copy.ui.view_models import format_specialized_rule_sections
from streamlit.testing.v1 import AppTest

from tests.specialized_ui_support import (
    APP_PATH,
    SOURCE,
    completed,
    report,
    research_cache,
    rule_context,
)

if TYPE_CHECKING:
    import pytest


def _specialized_cache(*, degraded: bool = False) -> SpecializedRuleCache:
    profile = "us-adjustable-wedding-sign-stands.md"
    content = "# Product fact gate\n- Confirm dimensions before writing."
    snapshot = SpecializedRuleSnapshot(
        profile_filename=profile,
        content_markdown=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    return SpecializedRuleCache(
        source_fingerprint=source_fingerprint(SOURCE),
        route_fingerprint="b" * 64,
        requested_profiles=(profile,),
        snapshots=() if degraded else (snapshot,),
        gaps=(
            (SpecializedRuleGap(code="provider_timeout", profile_filename=profile),)
            if degraded
            else ()
        ),
        all_requested_loaded=not degraded,
    )


def test_specialized_profiles_hashes_gaps_and_distinct_review_states_are_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specialized = _specialized_cache()
    result = completed().model_copy(
        update={
            "specialized_rule_cache": specialized,
            "specialized_cache_reused": True,
            "source_review": report().model_copy(
                update={
                    "format_status": "WARN",
                    "fact_status": "BLOCK",
                    "release_disposition": "clarify",
                }
            ),
        }
    )

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        del source, context
        return result

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)

    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    rendered = " ".join(str(item.value) for item in (*at.markdown, *at.caption, *at.text))
    assert "原始格式状态：WARN" in rendered
    assert "原始事实状态：已解决" in rendered
    assert "原始发布处置：clarify" in rendered
    assert "事实状态：BLOCK" not in rendered
    assert specialized.requested_profiles[0] in rendered
    assert specialized.snapshots[0].content_sha256[:12] in rendered
    assert "Confirm dimensions before writing" not in rendered
    assert any("专业规则配置" in str(item.label) for item in at.expander)


def test_specialized_profile_failure_shows_generic_fallback_and_safe_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = completed().model_copy(
        update={"specialized_rule_cache": _specialized_cache(degraded=True)}
    )

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        del source, context
        return result

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)

    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    rendered = " ".join(str(item.value) for item in (*at.markdown, *at.caption, *at.text))
    assert "降级为通用门槛" in rendered
    assert "provider_timeout" in rendered
    assert "us-adjustable-wedding-sign-stands.md" in rendered
    assert "Confirm dimensions before writing" not in rendered


def test_specialized_formatter_rejects_unallowlisted_profile_labels() -> None:
    cache = SpecializedRuleCache(
        source_fingerprint="a" * 64,
        route_fingerprint="b" * 64,
        requested_profiles=("https://private.example/rules?token=secret",),
        gaps=(
            SpecializedRuleGap(
                code="provider_error",
                profile_filename="https://private.example/rules?token=secret",
            ),
        ),
    )

    lines = [line for _title, body in format_specialized_rule_sections(cache) for line in body]
    rendered = " ".join(lines)
    assert "private.example" not in rendered
    assert "token=secret" not in rendered
    assert "未指定规则文件" in rendered


def test_marketplace_and_product_type_clarification_resume_keeps_rule_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    questions = (
        ClarificationQuestion(
            code="confirm_marketplace",
            finding_code="MARKETPLACE_UNRESOLVED",
            fact_key="marketplace",
            question_zh="请确认目标 Amazon 站点 (US/UK)。",
            evidence_needed="Seller Central 目标站点或卖家确认",
        ),
        ClarificationQuestion(
            code="confirm_product_type",
            finding_code="PRODUCT_TYPE_UNRESOLVED",
            fact_key="product_type",
            question_zh="请确认此商品的 Amazon Product Type。",
            evidence_needed="Seller Central 类目或 Product Type 记录",
        ),
    )
    specialized = _specialized_cache()
    paused = NeedsClarification(
        questions=questions,
        source_review=report(
            disposition="ask_user",
            questions=questions,
            status="BLOCK",
        ).model_copy(
            update={
                "format_status": "PASS",
                "fact_status": "BLOCK",
                "release_disposition": "clarify",
            }
        ),
        rule_context=rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=research_cache(),
        cache_reused=False,
        specialized_rule_cache=specialized,
    )
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> AutomaticOptimizationResult:
        del source
        calls.append(context)
        return paused if len(calls) == 1 else completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    assert not at.selectbox
    # Optional control-plane ASIN field is the only sidebar text_input.
    assert all("ASIN" in str(item.label) for item in at.text_input)
    at.chat_input[0].set_value("站点是UK，Product Type是OFFICE_ORGANIZER").run()

    assert len(calls) == 2
    assert calls[1] is not None
    assert calls[1].cached_specialized_rules == specialized
    assert calls[1].clarification_reply == "站点是UK，Product Type是OFFICE_ORGANIZER"
