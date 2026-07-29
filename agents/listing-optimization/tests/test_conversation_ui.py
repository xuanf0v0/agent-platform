from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.review.models import ClarificationQuestion
from streamlit.testing.v1 import AppTest

from tests.specialized_ui_support import (
    APP_PATH,
    SOURCE,
    completed,
    report,
)
from tests.specialized_ui_support import (
    paused as paused_result,
)

if TYPE_CHECKING:
    import pytest
    from amazon_copy.automatic_models import (
        AutomaticOptimizationContext,
        CompletedOptimization,
    )


def test_initial_surface_is_a_single_conversation_input() -> None:
    # Given: a fresh seller session.
    at = AppTest.from_file(str(APP_PATH)).run()

    # When/Then: the main surface starts as dialogue, not a separate listing form.
    assert not at.exception
    assert len(at.chat_input) == 1
    assert not at.text_area
    assert len(at.chat_message) == 1
    assert any("完整 Listing" in str(item.value) for item in at.chat_message[0].markdown)


def test_completed_conversation_keeps_review_layers_in_sidebar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one successful optimization response.
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        assert source == SOURCE
        calls.append(context)
        return completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()

    # When: the seller sends a complete Listing through chat.
    _ = at.chat_input[0].set_value(SOURCE).run()

    # Then: dialogue and copy stay in main while every diagnostic layer moves aside.
    assert not at.exception
    assert len(calls) == 1
    assert len(at.chat_message) == 2
    assert [area.label for area in at.text_area] == ["优化后 Listing"]
    main_text = " ".join(
        str(item.value)
        for message in at.chat_message
        for item in (*message.markdown, *message.caption, *message.text)
    )
    sidebar_text = " ".join(
        str(item.value)
        for item in (*at.sidebar.markdown, *at.sidebar.caption, *at.sidebar.text)
    )
    assert "原始 Listing 审核" not in main_text
    assert "优化后审核" not in main_text
    assert "原始 Listing 审核" in sidebar_text
    assert "优化后审核" in sidebar_text
    assert "流程与路由" in sidebar_text


def test_completed_pass_hides_resolved_source_blocks_from_sidebar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the source was blocked, but the rewritten Listing passes postflight.
    result = completed().model_copy(
        update={"source_review": report(status="BLOCK", can_optimize=False)}
    )

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        del source, context
        return result

    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        fake_run,
    )
    at = AppTest.from_file(str(APP_PATH)).run()

    # When: the completed result is rendered.
    _ = at.chat_input[0].set_value(SOURCE).run()

    # Then: historical source blocks are marked resolved instead of shown as active.
    assert not at.sidebar.error
    success_text = " ".join(str(item.value) for item in at.sidebar.success)
    assert "原始问题已由优化稿处理" in success_text
    assert "PASS · 未发现阻断项" in success_text


def test_pending_clarification_overrides_report_pass_in_sidebar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the deterministic report passes, but one seller fact is unanswered.
    question = ClarificationQuestion(
        code="confirm_material",
        finding_code="unsupported_material",
        fact_key="material",
        question_zh="请确认材质。",
        evidence_needed="包装或BOM",
    )
    result = paused_result(question)

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        del source, context
        return result

    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        fake_run,
    )
    at = AppTest.from_file(str(APP_PATH)).run()

    # When: the current clarification state is rendered.
    _ = at.chat_input[0].set_value(SOURCE).run()

    # Then: the live pending state takes precedence over the static PASS report.
    sidebar_success = " ".join(str(item.value) for item in at.sidebar.success)
    sidebar_warnings = " ".join(str(item.value) for item in at.sidebar.warning)
    sidebar_text = " ".join(
        str(item.value)
        for item in (*at.sidebar.markdown, *at.sidebar.caption, *at.sidebar.text)
    )
    assert "PASS · 未发现阻断项" not in sidebar_success
    assert "PASS" not in sidebar_text
    assert "待确认 · 1项" in sidebar_warnings


def test_second_clarification_keeps_every_sidebar_layer_non_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a second question is raised after a postflight report already exists.
    question = ClarificationQuestion(
        code="postflight_1_compatibility",
        finding_code="compatibility",
        fact_key="compatibility",
        question_zh="请确认兼容性。",
        evidence_needed="实测依据",
    )
    result = paused_result(question).model_copy(
        update={"postflight_review": report(status="BLOCK", can_optimize=False)}
    )

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        del source, context
        return result

    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        fake_run,
    )
    at = AppTest.from_file(str(APP_PATH)).run()

    # When: the second clarification state is rendered.
    _ = at.chat_input[0].set_value(SOURCE).run()

    # Then: no completed layer leaks PASS while the workflow is still pending.
    sidebar_text = " ".join(
        str(item.value)
        for item in (
            *at.sidebar.markdown,
            *at.sidebar.caption,
            *at.sidebar.text,
            *at.sidebar.success,
        )
    )
    assert "PASS" not in sidebar_text
    assert any("待确认 · 1项" in str(item.value) for item in at.sidebar.warning)
