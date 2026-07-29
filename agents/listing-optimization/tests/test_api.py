from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.api import optimize_payload
from amazon_copy.automatic_models import FailedOptimization

if TYPE_CHECKING:
    import pytest


def test_optimize_payload_uses_existing_automatic_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    def fake_run(source_text: str, *, context: object) -> FailedOptimization:
        captured.extend((source_text, context))
        return FailedOptimization(code="optimization_failed", message="fixture")

    monkeypatch.setattr("amazon_copy.api.run_automatic_optimization", fake_run)
    result = optimize_payload(
        {
            "source_text": "Title: Example\n- Verified feature",
            "context": {"mode": "diagnose", "identity": {"asin": "b0abcdefgh"}},
        }
    )

    assert result.status == "failed"
    assert captured[0] == "Title: Example\n- Verified feature"
    assert captured[1].identity.asin == "B0ABCDEFGH"
