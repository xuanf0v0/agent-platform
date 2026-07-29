from __future__ import annotations

from typing import TYPE_CHECKING, cast

from amazon_copy.automatic_models import EvidenceBundle
from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.mcp.live_research_types import ResearchBundle, ResearchItem
from streamlit.testing.v1 import AppTest

from tests.specialized_ui_support import APP_PATH, SOURCE, completed

if TYPE_CHECKING:
    import pytest
    from amazon_copy.automatic_models import (
        AutomaticOptimizationContext,
        CompletedOptimization,
    )


def test_one_megabyte_listing_is_rejected_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a provider spy and a one-megabyte Listing submission.
    calls: list[str] = []

    def fake_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        _ = context
        calls.append(source)
        return completed()

    monkeypatch.setattr("amazon_copy.simple_optimizer.run_automatic_optimization", fake_run)
    oversized = f"Safe title\n- {'x' * 1_000_000}"

    # When: the real Streamlit chat surface receives the submission.
    at = AppTest.from_file(str(APP_PATH)).run()
    _ = at.chat_input[0].set_value(oversized).run(timeout=15)

    # Then: the seller sees one stable localized error and no paid/provider call occurs.
    rendered = " ".join(str(item.value) for item in at.error)
    assert not at.exception
    assert calls == []
    assert "过长" in rendered
    assert "conversation_source_text" not in at.session_state
    assert "重试" not in {button.label for button in at.button}


def test_hundred_valid_research_items_degrade_without_streamlit_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a typed result whose otherwise valid aggregate cache exceeds its budget.
    items = tuple(
        ResearchItem(
            kind="keyword",
            key="keyword",
            value=f"usb hub {index}",
            provider="sellersprite",
            tool="keyword_miner",
        )
        for index in range(101)
    )
    snapshot = McpToolSnapshot(
        provider="sellersprite",
        status="ok",
        tool_count=1,
        research_items=items,
    )
    result = completed()
    cache = result.research_cache.model_copy(
        update={
            "snapshots": (snapshot,),
            "bundle": ResearchBundle(
                items=items,
                allowed_keywords=tuple(item.value for item in items),
            ),
        }
    )
    result = result.model_copy(
        update={
            "research_cache": cache,
            "evidence_bundle": EvidenceBundle(research=cache.bundle),
        }
    )

    def fake_result_run(
        source: str,
        *,
        context: AutomaticOptimizationContext | None = None,
    ) -> CompletedOptimization:
        _ = source, context
        return result

    monkeypatch.setattr(
        "amazon_copy.simple_optimizer.run_automatic_optimization",
        fake_result_run,
    )

    # When: the real Streamlit result/session boundary receives it.
    at = AppTest.from_file(str(APP_PATH)).run()
    _ = at.chat_input[0].set_value(SOURCE).run(timeout=15)

    # Then: no traceback widget appears and the stored cache is a typed gap.
    assert not at.exception
    stored = cast(
        "dict[str, object]",
        at.session_state["automatic_workflow_result"],
    )
    cache_payload = cast("dict[str, object]", stored["research_cache"])
    snapshots = cast("list[dict[str, object]]", cache_payload["snapshots"])
    bundle = cast("dict[str, object]", cache_payload["bundle"])
    gaps = cast("list[dict[str, object]]", bundle["gaps"])
    assert snapshots[0]["status"] == "skipped"
    assert bundle["items"] == []
    assert gaps[0]["code"] == "payload_too_large"
