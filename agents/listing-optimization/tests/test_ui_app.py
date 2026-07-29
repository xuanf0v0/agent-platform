from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    CompletedOptimization,
    EvidenceBundle,
    FailedOptimization,
    NeedsClarification,
)
from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.review.models import (
    ClarificationQuestion,
    EvidenceSource,
    FactClaim,
)
from amazon_copy.schemas import OptimizedListingCopy
from amazon_copy.ui.view_models import format_mcp_research_sections
from streamlit.proto.NewSession_pb2 import CustomThemeConfig
from streamlit.runtime.theme_util import parse_fonts_with_source
from streamlit.testing.v1 import AppTest

from tests.specialized_ui_support import (
    APP_PATH,
    SOURCE,
    SOURCE_CHANGED,
    completed,
    paused,
    report,
    research_cache,
    rule_context,
)

if TYPE_CHECKING:
    import pytest


_report = report
_cache = research_cache
_rule_context = rule_context
_completed = completed
_paused = paused


def test_streamlit_theme_fonts_parse_under_installed_runtime() -> None:
    config_path = Path(__file__).parents[1] / ".streamlit" / "config.toml"
    theme = tomllib.loads(config_path.read_text(encoding="utf-8"))["theme"]
    parsed = parse_fonts_with_source(
        CustomThemeConfig(),
        theme.get("font"),
        theme.get("codeFont"),
        theme.get("headingFont"),
        "theme",
    )
    assert parsed.body_font
    assert parsed.heading_font
    assert parsed.code_font


def test_ui_module_is_import_safe() -> None:
    module = importlib.import_module("amazon_copy.ui.app")
    assert callable(module.render_app)


def test_initial_has_one_chat_input_and_no_configuration_controls() -> None:
    at = AppTest.from_file(str(APP_PATH)).run()
    assert not at.exception
    assert not at.text_area
    assert len(at.chat_input) == 1
    assert [button.label for button in at.button] == ["新建对话"]
    # Control plane: optional ASIN + skip-approval only (no market/product config).
    assert any("跳过诊断" in str(item.label) for item in at.checkbox)
    assert any("ASIN" in str(item.label) for item in at.text_input)
    assert not at.selectbox
    rendered = " ".join(str(item.value) for item in (*at.markdown, *at.caption, *at.text))
    assert "实时运行层级" in rendered
    assert "美国本土化审核 Agent" in APP_PATH.read_text(encoding="utf-8")
    assert all(label not in rendered for label in ("目标市场", "Product Type"))


def test_header_wraps_only_complete_clauses_and_subtitle_units() -> None:
    module = importlib.import_module("amazon_copy.ui.app")
    css = module._THEME_CSS
    assert "display: inline-flex" in css
    assert "flex-wrap: wrap" in css
    assert "max-width: 100%" in css
    assert ".lithos-sub-unit" in css
    source = APP_PATH.read_text(encoding="utf-8")
    assert '<span class="lithos-eyebrow-clause">AMAZON COPY OPTIMIZER</span>' in source
    assert '<span class="lithos-eyebrow-clause">DIAGNOSE FIRST, THEN OPTIMIZE</span>' in source
    assert "<wbr>" in source


def test_theme_tokens_and_semantic_heading_hierarchy_are_regression_protected() -> None:
    module = importlib.import_module("amazon_copy.ui.app")
    css = module._THEME_CSS
    root_start = css.index(":root {")
    root_end = css.index("}", root_start) + 1
    outside_root = css[:root_start] + css[root_end:]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\s*\(", outside_root)
    assert "--lithos-font-heading" in css
    assert "--lithos-space-" in css
    assert "--lithos-radius" in css
    generic_heading = css.index('[data-testid="stMarkdownContainer"] h2')
    section_label = css.index("h2.lithos-section-label")
    clarification_heading = css.index('[data-testid="stMarkdownContainer"] h3')
    assert section_label > generic_heading
    assert clarification_heading > generic_heading

    source = APP_PATH.read_text(encoding="utf-8")
    assert 'st.markdown(f"## {heading}")' in source
    assert 'st.chat_message("assistant"' in source
    assert 'st.markdown(f"### {heading}")' not in source


def test_completed_one_click_shows_before_after_reviews_and_safe_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        assert source == SOURCE
        calls.append(context)
        return _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert not at.exception
    assert len(calls) == 1
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]
    labels = " ".join(str(item.label) for item in at.expander)
    text = " ".join(str(item.value) for item in (*at.markdown, *at.caption, *at.text))
    assert "原始 Listing 审核" in text
    assert "优化后审核" in text
    assert "10维独立评分" in labels
    assert "安全的 MCP / 市场研究依据" in labels
    assert "综合分" not in text
    assert any("跳过诊断" in str(item.label) for item in at.checkbox)


def test_clarification_resume_uses_chat_reply_and_cached_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = ClarificationQuestion(
        code="confirm_material",
        finding_code="unsupported_material",
        fact_key="material",
        question_zh="请确认材质是否来自包装标签。",
        evidence_needed="包装或BOM",
        claim_terms=("natural",),
    )
    paused = NeedsClarification(
        questions=(question,),
        source_review=_report(disposition="ask_user", questions=(question,)),
        rule_context=_rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=_cache(),
        cache_reused=False,
    )
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        assert source == SOURCE
        calls.append(context)
        return paused if len(calls) == 1 else _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert len(at.chat_message) == 2
    assert not at.selectbox
    # Optional ASIN text_input lives in the sidebar control plane.
    assert any("ASIN" in str(item.label) for item in at.text_input)
    assert not at.chat_input[0].disabled
    at.chat_input[0].set_value("无法确认，请删除 natural 材质宣称").run()
    assert len(calls) == 2
    assert calls[1] is not None
    assert calls[1].cached_research is not None
    assert calls[1].cached_research.source_fingerprint == source_fingerprint(SOURCE)
    assert calls[1].clarification_reply == "无法确认，请删除 natural 材质宣称"
    # Source-fact clarification resumes Stage1 diagnose (no postflight yet).
    assert calls[1].mode == "diagnose"
    assert calls[1].skip_approval is False
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]


def test_new_chat_message_replaces_source_bound_result_and_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: _completed(),
    )
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert len(at.text_area) == 1
    at.chat_input[0].set_value(SOURCE_CHANGED).run()
    assert not at.exception
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]
    assert at.session_state["conversation_source_text"] == SOURCE_CHANGED


def test_mcp_unavailable_is_degraded_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: _completed(unavailable=True),
    )
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    joined = " ".join(str(item.value) for item in (*at.caption, *at.text))
    assert "provider unavailable" in joined
    assert "sk-" not in joined


def test_provider_error_is_sanitized_and_retry_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        message = "authentication failed for sk-test-secret"
        raise RuntimeError(message)

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fail)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert at.error
    joined = " ".join(str(item.value) for item in at.error)
    assert "sk-test-secret" not in joined
    assert "authentication failed" not in joined
    assert any(button.label == "重试" for button in at.button)


def test_postflight_block_has_no_copy_area(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = FailedOptimization(
        code="postflight_blocked",
        message="Generated listing was suppressed by postflight review.",
        postflight_review=_report(),
        rule_context=_rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=_cache(),
    )
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: failed,
    )
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert not at.text_area
    assert not any("优化后 Listing" in str(item.label) for item in at.text_area)


def test_contradictory_completed_postflight_block_has_only_blocking_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = _completed()
    blocked = blocked.model_copy(
        update={
            "postflight_review": _report(status="BLOCK", can_optimize=False),
        }
    )
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: blocked,
    )
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert not at.text_area
    assert any("BLOCK" in str(item.value) for item in at.error)
    assert any("安全的 MCP" in str(item.label) for item in at.sidebar.expander)


def test_typed_failed_message_is_sanitized_before_render_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = FailedOptimization(
        code="optimization_failed",
        message="provider failed sk-test-secret at https://private.example.test/mcp?token=secret",
    )
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: failed,
    )
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    rendered = " ".join(str(item.value) for item in at.error)
    assert "sk-test-secret" not in rendered
    assert "private.example.test" not in rendered
    stored = at.session_state["automatic_workflow_result"]
    assert isinstance(stored, dict)
    assert "sk-test-secret" not in str(stored)
    assert "private.example.test" not in str(stored)


def test_safe_typed_failure_reason_is_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = FailedOptimization(
        code="optimization_failed",
        message="模型返回格式无效，请重新提交；若重复出现请检查模型服务。",
    )
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: failed,
    )

    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    rendered = " ".join(str(item.value) for item in at.error)
    assert "模型返回格式无效" in rendered


def test_provider_timeout_is_rendered_as_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> FailedOptimization:
        del source, context
        raise TimeoutError

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fail_run)

    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    rendered = " ".join(str(item.value) for item in at.error)
    assert "响应超时" in rendered
    assert "60秒" in rendered


def test_awaiting_approval_has_generate_button_without_copy_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.specialized_ui_support import awaiting_approval

    stage1 = awaiting_approval(token="b" * 64)
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        del source
        calls.append(context)
        if len(calls) == 1:
            return stage1
        return _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert not at.exception
    assert not at.text_area
    assert any(button.label == "生成上传稿" for button in at.button)
    main_text = " ".join(
        str(item.value)
        for message in at.chat_message
        for item in (*message.markdown, *message.caption, *message.info, *message.text)
    )
    assert "Stage 1" in main_text or "诊断" in main_text
    # Stage2 via generate button.
    generate = next(button for button in at.button if button.label == "生成上传稿")
    generate.click().run()
    assert len(calls) == 2
    assert calls[1] is not None
    assert calls[1].mode == "optimize"
    assert calls[1].approval_token == "b" * 64
    assert calls[1].skip_approval is False
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]


def test_research_cache_credentials_are_redacted_before_session_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = McpToolSnapshot(
        provider="sellersprite",
        status="error",
        tool_count=1,
        tools_sample=["Cookie: sessionid=session-secret"],
        calls=[
            {
                "tool": "keyword_miner",
                "ok": False,
                "summary_text": ("Authorization: Basic dXNlcjpwYXNz\nX-API-Key: api-secret"),
            }
        ],
    )
    result = _completed()
    cache = result.research_cache.model_copy(update={"snapshots": (snapshot,)})
    result = result.model_copy(update={"research_cache": cache})
    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        lambda source, *, context=None: result,
    )

    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    stored = at.session_state["automatic_workflow_result"]
    assert isinstance(stored, dict)
    serialized = str(stored)
    assert "dXNlcjpwYXNz" not in serialized
    assert "session-secret" not in serialized
    assert "api-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_mcp_formatter_defensively_redacts_malformed_snapshot_payload() -> None:
    malformed = [
        {
            "provider": "sellersprite",
            "status": "error",
            "tool_count": 1,
            "tools_sample": ["keyword_miner"],
            "error": "sk-test-secret at https://private.example.test/mcp?token=secret",
            "calls": [
                {
                    "tool": "keyword_miner",
                    "ok": False,
                    "summary_text": "raw sk-test-secret https://private.example.test/mcp",
                }
            ],
        }
    ]
    sections = format_mcp_research_sections(malformed)  # type: ignore[arg-type]
    rendered = " ".join(line for _, lines in sections for line in lines)
    assert "sk-test-secret" not in rendered
    assert "private.example.test" not in rendered


def test_repeated_clarification_resume_keeps_one_chat_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ClarificationQuestion(
        code="confirm_material",
        finding_code="unsupported_material",
        fact_key="material",
        question_zh="确认材质？",
        evidence_needed="包装",
        claim_terms=("natural",),
    )
    duplicate = first.model_copy(update={"question_zh": "确认材质（重复）？"})
    paused = _paused(first, duplicate)
    calls = 0

    def fake_run(source: str, *, context: AutomaticOptimizationContext | None = None) -> object:
        nonlocal calls
        calls += 1
        return paused if calls < 3 else _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert not at.selectbox
    assert len(at.chat_input) == 1
    at.chat_input[0].set_value("两项都无法确认，请删除").run()
    assert calls == 2
    assert not at.selectbox
    assert len(at.chat_input) == 1
    at.chat_input[0].set_value("认可保守删除原则").run()
    assert calls == 3
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]


def test_repeated_failed_retry_reruns_without_duplicate_retry_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    failed = FailedOptimization(code="optimization_failed", message="provider failed")

    def fake_run(source: str, *, context: AutomaticOptimizationContext | None = None) -> object:
        nonlocal calls
        calls += 1
        return failed if calls < 3 else _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    assert len([button for button in at.button if button.label == "重试"]) == 1
    next(button for button in at.button if button.label == "重试").click().run()
    assert calls == 2
    assert len([button for button in at.button if button.label == "重试"]) == 1
    next(button for button in at.button if button.label == "重试").click().run()
    assert calls == 3
    assert [widget.label for widget in at.text_area] == ["优化后 Listing"]


def test_quality_rounds_render_in_separate_right_panel_and_keep_last_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=(
            "Smooth Painting Surface: Use the stones for detailed craft projects.",
        ),
        backend_search_terms="river rocks painting",
    )
    failed = FailedOptimization(
        code="optimization_failed",
        message="语法与编辑校验未全部通过",
        last_candidate=candidate,
        last_candidate_text="Title: Natural River Rocks for Painting",
        quality_failures=("Bullet Point 1 [grammar]: issue -> correction",),
    )

    def fake_run(source: str, *, context: object, dependencies: object) -> object:
        del source, context
        callback = getattr(dependencies, "quality_callback")
        callback(1, 8, ("Title [truncation]: Rock s -> Rocks",), False)
        callback(2, 8, ("Bullet Point 1 [grammar]: issue -> correction",), False)
        return failed

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()

    labels = " ".join(str(item.value) for item in (*at.markdown, *at.caption, *at.text))
    assert "实时运行层级" in labels
    assert "未通过原因" in labels
    assert "Rock s -> Rocks" in labels
    assert [widget.label for widget in at.text_area] == ["最后一轮稿件（未通过）"]


def test_repeated_clarification_resume_preserves_fallback_rule_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a non-authoritative fallback context and a priority-4 user fact
    question = ClarificationQuestion(
        code="confirm_material",
        finding_code="unsupported_material",
        fact_key="material",
        question_zh="确认材质？",
        evidence_needed="包装",
        claim_terms=("natural",),
    )
    claim = FactClaim(
        key="material",
        value="natural stone",
        source=EvidenceSource.PACKAGING_BOM_USER,
        sku_scope="all",
    )
    paused = _paused(question).model_copy(
        update={"evidence_bundle": EvidenceBundle(user_claims=(claim,))}
    )
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        del source
        calls.append(context)
        return paused if len(calls) < 3 else _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)

    # When: two clarification turns resume the same paused workflow
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    at.chat_input[0].set_value("无法确认，请删除").run()
    at.chat_input[0].set_value("再次确认采用保守删除").run()

    # Then: every machine-consumed context keeps fallback authority, gaps, and facts
    assert len(calls) == 3
    for context in calls[1:]:
        assert context is not None
        assert context.rule_context == paused.rule_context
        assert context.rule_context.authoritative is False
        assert [gap.code for gap in context.rule_context.gaps] == ["authoritative_rules_missing"]
        assert context.rules is None
        assert context.user_claims == (claim,)


def test_repeated_retry_preserves_fallback_rule_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a retryable failure carrying a non-authoritative fallback context
    failed = FailedOptimization(
        code="optimization_failed",
        message="provider failed",
        rule_context=_rule_context(),
        evidence_bundle=EvidenceBundle(),
        research_cache=_cache(),
    )
    calls: list[AutomaticOptimizationContext | None] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> object:
        del source
        calls.append(context)
        return failed if len(calls) < 3 else _completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)

    # When: the user retries twice
    at = AppTest.from_file(str(APP_PATH)).run()
    at.chat_input[0].set_value(SOURCE).run()
    for _ in range(2):
        next(button for button in at.button if button.label == "重试").click().run()

    # Then: both retries pass the exact cached RuleContext instead of fallback rules
    assert len(calls) == 3
    for context in calls[1:]:
        assert context is not None
        assert context.rule_context == failed.rule_context
        assert context.rule_context.authoritative is False
        assert context.rules is None
