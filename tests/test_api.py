from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.api import agents_payload, optimize_payload, workflow_payload
from amazon_copy.automatic_models import FailedOptimization

if TYPE_CHECKING:
    import pytest


def test_optimize_payload_validates_and_serializes_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    def fake_run(source_text: str, *, context: object) -> FailedOptimization:
        captured.extend((source_text, context))
        return FailedOptimization(code="optimization_failed", message="fixture")

    monkeypatch.setattr("amazon_copy.api.run_automatic_optimization", fake_run)
    result = optimize_payload(
        {
            "source_text": "Title: Example Product\n- First verified product feature",
            "context": {"mode": "diagnose", "identity": {"asin": "b0abcdefgh"}},
        }
    )
    assert result.status == "failed"
    assert captured[0] == "Title: Example Product\n- First verified product feature"
    assert captured[1].identity.asin == "B0ABCDEFGH"


def test_api_lists_both_managed_agents() -> None:
    assert [agent["id"] for agent in agents_payload()["agents"]] == [
        "safe-optimizer",
        "copy-studio",
    ]


def test_copy_workflow_endpoint_advances_serialized_state() -> None:
    result = workflow_payload(
        {
            "state": {"workflow": "write", "step": "basic_input", "revision": 0},
            "values": {"product_name": "USB Hub", "target_market": "US"},
        }
    )
    assert result["state"]["step"] == "market_research"
    assert result["state"]["revision"] == 1
