from __future__ import annotations

import asyncio
import builtins
import json
import time

import pytest
from amazon_copy.config import Settings
from amazon_copy.llm import MockLLM
from amazon_copy.orchestrator import PipelineStageError, run_pipeline
from amazon_copy.orchestrator._counter import CallLimitError
from amazon_copy.schemas import PipelineStage, ProductInput


def _product(*, with_asin: bool = True) -> ProductInput:
    return ProductInput(
        product="USB C Hub",
        market="US",
        instruction="Write conversion-focused Amazon copy",
        asin1="Competitor title and five pasted bullets" if with_asin else None,
        rootwords=[
            "usb",
            "hub",
            "adapter",
            "hdmi",
            "macbook",
            "port",
            "multiport",
            "laptop",
            "apple",
            "usbc",
            "card",
            "mac",
            "dongle",
            "pd",
            "charging",
            "4k",
            "sd",
            "microsd",
            "chrome",
            "dell",
            "ipad",
        ],
        keywords=[
            "usb hub",
            "usb c hub",
            "usb-c hub",
            "multiport adapter",
            "hdmi hub",
            "pd charging",
            "4k hdmi",
            "macbook hub",
            "laptop hub",
            "sd card reader",
        ],
    )


class _RecordingFactory:
    def __init__(self) -> None:
        self.roles: list[str] = []

    def __call__(self, role: str) -> MockLLM:
        self.roles.append(role)
        return MockLLM(role)


@pytest.mark.asyncio
async def test_run_builds_complete_amazon_copy_package_in_graph_order() -> None:
    """RUN mode now routes through StudioService — package has listing but no legacy fields."""
    package = await run_pipeline(
        _product(),
        mode="run",
        settings=Settings(mock=True),
    )

    assert package.listing is not None
    assert len(package.listing.title_candidates) == 3  # studio produces 3 titles
    assert package.listing.title in {item.text for item in package.listing.title_candidates}
    assert len(package.listing.bullets) == 5
    # Studio package does not populate legacy fields
    assert package.research is None
    assert package.selling_points == []
    assert package.seo is None
    assert package.seo2 is None
    assert package.scorecard is None
    assert package.stage is PipelineStage.COMPLETED
    assert package.stage_history == [PipelineStage.COMPLETED]


@pytest.mark.asyncio
async def test_run_mode_invokes_studio_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify RUN mode routes through run_studio_pipeline."""
    import amazon_copy.orchestrator.studio_graph as sg
    call_record = {"called": False, "text": None}

    async def fake_studio(text: str, **kwargs: object) -> object:
        from amazon_copy.orchestrator.state import StudioState
        from amazon_copy.schemas.agents import CandidateArtifact, WriterLane
        call_record["called"] = True
        call_record["text"] = text
        winner = CandidateArtifact(
            candidate_id="fake-winner",
            lane=WriterLane.SEO,
            titles=["Test Title A", "Test Title B", "Test Title C"],
            bullets=["b1", "b2", "b3", "b4", "b5"],
        )
        return StudioState(
            request_text=text,
            run_id="test-run",
            outcome="success",
            winner=winner,
            llm_calls=3,
            mcp_calls=5,
        )

    monkeypatch.setattr(sg, "run_studio_pipeline", fake_studio)
    package = await run_pipeline(
        _product(with_asin=False),
        mode="run",
        settings=Settings(mock=True),
    )
    assert call_record["called"], "run_studio_pipeline was not called"
    assert "USB C Hub" in call_record["text"]
    assert package.listing is not None
    assert package.stage is PipelineStage.COMPLETED


@pytest.mark.asyncio
async def test_no_asin_skips_only_competitor_research_nodes() -> None:
    """Legacy OPTIMIZE path still respects asin-based competitor research gating."""
    factory = _RecordingFactory()
    title_source = json.loads(MockLLM("bullets").complete("", ""))["bullets"]
    await run_pipeline(
        _product(with_asin=False),
        mode="optimize",
        title="USB C Hub",
        bullets=[row["text"] for row in title_source],
        settings=Settings(mock=True),
        llm_factory=factory,
    )
    assert not any(role.startswith("research_competitor_") for role in factory.roles)
    assert "optimize_bp" in factory.roles
    assert "scorecard" not in factory.roles
    assert "title" not in factory.roles


@pytest.mark.asyncio
async def test_hitl_false_never_calls_input_or_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        builtins,
        "input",
        lambda *_: pytest.fail("pipeline must never own CLI input()"),
    )

    def callback(*_: object) -> bool:
        pytest.fail("HITL callback called while disabled")

    await run_pipeline(
        _product(with_asin=False),
        settings=Settings(mock=True, hitl_confirm=False),
        hitl_callback=callback,
    )


@pytest.mark.asyncio
async def test_hitl_true_studio_does_not_call_hitl() -> None:
    """Studio path (RUN/WRITE) does not invoke HITL callbacks."""
    seen: list[PipelineStage] = []

    async def confirm(stage: PipelineStage, payload: object) -> bool:
        assert payload is not None
        seen.append(stage)
        return True

    await run_pipeline(
        _product(with_asin=False),
        settings=Settings(mock=True, hitl_confirm=True),
        hitl_callback=confirm,
    )
    assert seen == [], "studio path should not invoke HITL callbacks"


@pytest.mark.asyncio
async def test_studio_no_winner_raises_value_error() -> None:
    """When studio pipeline returns no_winner, run_pipeline raises ValueError."""
    from unittest.mock import patch
    with patch("amazon_copy.orchestrator.studio_graph.run_studio_pipeline") as mock_run:
        from amazon_copy.orchestrator.state import StudioState
        mock_run.return_value = StudioState(
            request_text="test",
            run_id="mock-fail",
            outcome="no_winner",
            llm_calls=9,
            mcp_calls=5,
        )
        with pytest.raises(ValueError, match="no eligible candidate"):
            await run_pipeline(
                _product(with_asin=False),
                mode="run",
                settings=Settings(mock=True),
            )


@pytest.mark.asyncio
async def test_write_mode_goes_through_studio() -> None:
    """WRITE mode now routes through StudioService (same path as RUN)."""
    package = await run_pipeline(
        _product(with_asin=False),
        mode="write",
        settings=Settings(mock=True),
    )
    assert package.listing is not None
    assert len(package.listing.title_candidates) == 3
    assert package.stage is PipelineStage.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected", "forbidden"),
    [
        ("optimize", {"optimize_bp"}, {"research_audience", "title", "scorecard"}),
        ("seo", set(), {"research_audience", "title", "optimize_bp", "scorecard"}),
        ("analyze", {"scorecard"}, {"research_audience", "title", "optimize_bp"}),
    ],
)
async def test_modes_short_circuit_to_their_copywriting_workflow(
    mode: str,
    expected: set[str],
    forbidden: set[str],
) -> None:
    factory = _RecordingFactory()
    fixture = MockLLM("bullets").complete("", "")
    rows = json.loads(fixture)["bullets"]
    kwargs = {"title": "USB C Hub", "bullets": [row["text"] for row in rows]}
    package = await run_pipeline(
        _product(with_asin=False),
        mode=mode,
        settings=Settings(mock=True),
        llm_factory=factory,
        **kwargs,
    )
    assert expected <= set(factory.roles)
    assert forbidden.isdisjoint(factory.roles)
    assert package.stage is PipelineStage.COMPLETED


@pytest.mark.asyncio
async def test_stage_error_identifies_malformed_copywriting_stage() -> None:
    """OPTIMIZE (legacy) path wraps malformed LLM response in PipelineStageError."""
    class _Malformed(MockLLM):
        def complete(self, system: str, user: str, **kwargs: object) -> str:
            if self._role == "optimize_bp":
                return "not-json"
            return super().complete(system, user, **kwargs)

    title_source = json.loads(MockLLM("bullets").complete("", ""))["bullets"]
    with pytest.raises(PipelineStageError) as captured:
        await run_pipeline(
            _product(with_asin=False),
            mode="optimize",
            title="USB C Hub",
            bullets=[row["text"] for row in title_source],
            settings=Settings(mock=True),
            llm_factory=_Malformed,
        )
    assert captured.value.stage is PipelineStage.BP_OPTIMIZE
    assert captured.value.package.stage is PipelineStage.FAILED
    assert captured.value.package.error


@pytest.mark.asyncio
async def test_cancellation_is_not_relabelled_as_stage_failure() -> None:
    """CancelledError propagates cleanly from any pipeline path."""
    class _Hung(MockLLM):
        def complete(self, system: str, user: str, **kwargs: object) -> str:
            if self._role == "optimize_bp":
                time.sleep(5)
            return super().complete(system, user, **kwargs)

    title_source = json.loads(MockLLM("bullets").complete("", ""))["bullets"]
    task = asyncio.create_task(
        run_pipeline(
            _product(with_asin=False),
            mode="optimize",
            title="USB C Hub",
            bullets=[row["text"] for row in title_source],
            settings=Settings(mock=True),
            llm_factory=_Hung,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
