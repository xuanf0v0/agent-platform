"""Asyncio orchestration for the Amazon listing copywriting workflows.

The pipeline deliberately coordinates the existing narrow agents instead of
introducing a graph framework. Research is the only fan-out; every downstream
copy decision follows the SOP dependency order.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

import amazon_copy.config as config_module
from amazon_copy.agents.research import assemble_research_pack
from amazon_copy.agents.scorecard import score_listing
from amazon_copy.agents.selling_points import rank_selling_points
from amazon_copy.agents.seo import check_listing_seo
from amazon_copy.agents.writer import TitleGeneration, generate_bullets, generate_titles, rewrite
from amazon_copy.llm import LLMClient, get_llm
from amazon_copy.modes import analyze as analyze_mode
from amazon_copy.modes import optimize as optimize_mode
from amazon_copy.modes import seo as seo_mode
from amazon_copy.orchestrator._counter import CallCounter, CallLimitError
from amazon_copy.schemas import (
    BulletPoint,
    FinalPackage,
    ListingDraft,
    PipelineMode,
    PipelineStage,
    ProductInput,
    ResearchPack,
    Scorecard,
    SellingPoint,
    SEOCheck,
    TitleMode,
)

if TYPE_CHECKING:
    from amazon_copy.config import Settings

LLMFactory: TypeAlias = Callable[[str], LLMClient]  # noqa: UP040 - Python 3.11 supported
HITLCallback: TypeAlias = Callable[  # noqa: UP040 - Python 3.11 supported
    [PipelineStage, object], bool | None | Awaitable[bool | None]
]
_T = TypeVar("_T")
_MODE_DEFAULT_BUDGET = {
    PipelineMode.RUN: 40,
    PipelineMode.WRITE: 40,
    PipelineMode.OPTIMIZE: 15,
    PipelineMode.SEO: 10,
    PipelineMode.ANALYZE: 10,
}


class PipelineStageError(RuntimeError):
    """A stage-labelled failure carrying the safe partial package."""

    def __init__(
        self,
        stage: PipelineStage,
        cause: Exception,
        package: FinalPackage,
    ) -> None:
        """Retain the failed stage, original cause, and partial package."""
        self.stage = stage
        self.cause = cause
        self.package = package
        super().__init__(f"{stage.value} stage failed: {cause}")


class HITLRejectedError(RuntimeError):
    """Raised when a configured human gate rejects the current copy artifact."""


def _package(
    state: dict[str, Any],
    *,
    stage: PipelineStage = PipelineStage.COMPLETED,
    error: str | None = None,
) -> FinalPackage:
    return FinalPackage.model_validate(
        {
            "product_input": state["product_input"],
            "research": state.get("research"),
            "selling_points": state.get("selling_points", []),
            "listing": state.get("listing"),
            "seo": state.get("seo"),
            "seo2": state.get("seo2"),
            "scorecard": state.get("scorecard"),
            "selection": state.get("selection"),
            "warnings": state.get("warnings", []),
            "stage": stage,
            "stage_history": state.get("stage_history", []),
            "error": error,
        },
        context={"skip_title_length": True, "skip_bp_length": True},
    )


async def _execute_stage(  # noqa: UP047 - Python 3.11 supported
    stage: PipelineStage,
    state: dict[str, Any],
    operation: Callable[[], Awaitable[_T]],
) -> _T:
    state["stage_history"].append(stage)
    try:
        return await operation()
    except (asyncio.CancelledError, CallLimitError, PipelineStageError):
        raise
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise PipelineStageError(
            stage,
            exc,
            _package(state, stage=PipelineStage.FAILED, error=error),
        ) from exc


async def _confirm(
    settings: Settings,
    callback: HITLCallback | None,
    stage: PipelineStage,
    payload: object,
) -> None:
    if not settings.hitl_confirm:
        return
    if callback is None:
        message = (
            "HITL_CONFIRM=true requires an injected hitl_callback; input() belongs only "
            "in the CLI adapter"
        )
        raise HITLRejectedError(message)
    decision = callback(stage, payload)
    if inspect.isawaitable(decision):
        decision = await decision
    if decision is False:
        message = f"HITL rejected artifact after {stage.value}"
        raise HITLRejectedError(message)


def _source_listing(
    product: ProductInput,
    title: str,
    bullets: Sequence[str | BulletPoint] | None,
) -> ListingDraft:
    if bullets is None:
        message = "bullets must contain exactly five non-empty BP strings"
        raise ValueError(message)
    normalized = [
        item
        if isinstance(item, BulletPoint)
        else BulletPoint.model_validate(
            {"text": item, "text_zh": "用户提供"},
            context={"skip_bp_length": True},
        )
        for item in bullets
    ]
    return ListingDraft.model_validate(
        {
            "title": title.strip() or product.product,
            "title_zh": "",
            "title_candidates": [],
            "bullets": normalized,
        },
        context={"skip_title_length": True, "skip_bp_length": True},
    )


def _budget(mode: PipelineMode, settings: Settings, override: int | None) -> int:
    if override is not None:
        if override < 1:
            message = "max_llm_calls must be >= 1"
            raise ValueError(message)
        return override
    if "max_llm_calls" in settings.model_fields_set:
        return settings.max_llm_calls
    return _MODE_DEFAULT_BUDGET[mode]


async def run_pipeline(  # noqa: C901, PLR0912, PLR0913, PLR0915 - explicit SOP graph is clearer inline
    product_input: ProductInput,
    mode: PipelineMode | str = PipelineMode.RUN,
    *,
    title: str = "",
    bullets: Sequence[str | BulletPoint] | None = None,
    intents: Sequence[str] = (),
    instructions: str = "Optimize these Amazon bullets for shopper intent and clarity",
    full_checks: bool = False,
    settings: Settings | None = None,
    llm_factory: LLMFactory | None = None,
    hitl_callback: HITLCallback | None = None,
    max_llm_calls: int | None = None,
) -> FinalPackage:
    """Run one Amazon copy workflow and return its export-ready package.

    ``run`` executes the full write/check/optimize/check/score graph. ``write``
    stops after its first deterministic SEO audit unless ``full_checks`` is set.
    Listing-only modes never execute research or writer stages.
    """
    resolved_mode = mode if isinstance(mode, PipelineMode) else PipelineMode(mode)
    runtime = settings or config_module.settings
    factory = llm_factory or (lambda role: get_llm(role, settings=runtime))
    counter = CallCounter(_budget(resolved_mode, runtime, max_llm_calls))
    state: dict[str, Any] = {
        "product_input": product_input,
        "selling_points": [],
        "warnings": [],
        "stage_history": [],
    }

    # ── Route RUN and WRITE through StudioService ─────────────────────
    if resolved_mode in {PipelineMode.RUN, PipelineMode.WRITE}:
        from amazon_copy.orchestrator._studio_mapper import package_from_studio_state
        from amazon_copy.orchestrator.studio_graph import run_studio_pipeline

        text = str(product_input.product)
        if product_input.instruction and product_input.instruction.strip():
            text += f"\n{product_input.instruction.strip()}"
        if product_input.keywords:
            raw_kw = product_input.keywords
            kw = ", ".join(raw_kw) if isinstance(raw_kw, list) else str(raw_kw)
            text += f"\n{kw}"
        studio_state = await run_studio_pipeline(text, settings=runtime)
        # Post-check: enforce seller_name constraint if set on ProductInput
        if product_input.seller_name and studio_state.winner:
            seller_cf = product_input.seller_name.casefold().strip()
            if seller_cf:
                for idx, t in enumerate(studio_state.winner.titles):
                    if seller_cf in t.casefold():
                        seller = product_input.seller_name
                        msg = (
                            f"seller name {seller!r} found in "
                            f"studio candidate title[{idx}]"
                        )
                        raise ValueError(msg)
        pkg = package_from_studio_state(studio_state, product_input=product_input)
        if pkg is None:
            outcome = studio_state.outcome
            msg = f"Studio pipeline {outcome}: no eligible candidate produced"
            raise ValueError(msg)
        return pkg

    if resolved_mode in {PipelineMode.OPTIMIZE, PipelineMode.SEO, PipelineMode.ANALYZE}:
        source = _source_listing(product_input, title, bullets)
        state["listing"] = source
        if resolved_mode is PipelineMode.OPTIMIZE:

            async def optimize_only() -> list[BulletPoint]:
                client = counter.wrap(factory("optimize_bp"))
                return await asyncio.to_thread(
                    optimize_mode,
                    product_input,
                    source.bullets,
                    instructions=instructions,
                    llm=client,
                )

            optimized = await _execute_stage(PipelineStage.BP_OPTIMIZE, state, optimize_only)
            state["listing"] = ListingDraft.model_validate(
                source.model_copy(update={"bullets": optimized}),
                context={"skip_title_length": True, "bp_mode": "optimize"},
            )
        elif resolved_mode is PipelineMode.SEO:

            async def seo_only() -> SEOCheck:
                return seo_mode(
                    title=source.title,
                    bullets=source.bullets,
                    intents=intents,
                    rootwords=product_input.rootwords,
                    keywords=product_input.keywords,
                )

            state["seo"] = await _execute_stage(PipelineStage.SEO_CHECK, state, seo_only)
        else:

            async def analyze_only() -> Scorecard:
                client = counter.wrap(factory("scorecard"))
                return await asyncio.to_thread(
                    analyze_mode,
                    product=product_input,
                    title=source.title,
                    bullets=source.bullets,
                    llm=client,
                )

            state["scorecard"] = await _execute_stage(PipelineStage.SCORECARD, state, analyze_only)
        state["stage_history"].append(PipelineStage.COMPLETED)
        return _package(state)

    async def research() -> ResearchPack:
        return await assemble_research_pack(
            product_input,
            counter=counter,
            llm_factory=factory,
        )

    state["research"] = await _execute_stage(PipelineStage.RESEARCH, state, research)
    await _confirm(runtime, hitl_callback, PipelineStage.RESEARCH, state["research"])

    async def selling_points() -> list[SellingPoint]:
        return await rank_selling_points(
            product_input,
            state["research"],
            counter=counter,
            llm_factory=factory,
        )

    state["selling_points"] = await _execute_stage(
        PipelineStage.SELLING_POINTS, state, selling_points
    )
    await _confirm(
        runtime,
        hitl_callback,
        PipelineStage.SELLING_POINTS,
        state["selling_points"],
    )

    async def titles() -> TitleGeneration:
        client = counter.wrap(factory("title"))
        return await asyncio.to_thread(
            generate_titles,
            product_input,
            state["selling_points"],
            llm=client,
            mode=TitleMode(runtime.title_mode),
        )

    generated = await _execute_stage(PipelineStage.TITLE, state, titles)
    state["selection"] = generated.selection

    async def write_bullets() -> list[BulletPoint]:
        client = counter.wrap(factory("bullets"))
        return await asyncio.to_thread(
            generate_bullets,
            product_input,
            state["selling_points"],
            llm=client,
        )

    written = await _execute_stage(PipelineStage.BP_WRITE, state, write_bullets)
    state["listing"] = ListingDraft.model_validate(
        {
            "title": generated.winner.text,
            "title_zh": generated.winner.text_zh,
            "title_candidates": generated.candidates,
            "bullets": written,
        },
        context={"title_mode": runtime.title_mode, "bp_mode": "write"},
    )
    await _confirm(runtime, hitl_callback, PipelineStage.BP_WRITE, state["listing"])

    derived_intents = [point.text_en for point in state["selling_points"]]

    async def first_seo() -> SEOCheck:
        return check_listing_seo(
            state["listing"],
            derived_intents,
            product_input.rootwords,
            product_input.keywords,
        )

    state["seo"] = await _execute_stage(PipelineStage.SEO_CHECK, state, first_seo)
    if resolved_mode is PipelineMode.WRITE and not full_checks:
        state["stage_history"].append(PipelineStage.COMPLETED)
        return _package(state)

    async def optimize_full() -> list[BulletPoint]:
        client = counter.wrap(factory("optimize_bp"))
        return await asyncio.to_thread(
            rewrite,
            state["listing"].bullets,
            product_input,
            instructions,
            llm=client,
        )

    optimized = await _execute_stage(PipelineStage.BP_OPTIMIZE, state, optimize_full)
    state["listing"] = ListingDraft.model_validate(
        state["listing"].model_copy(update={"bullets": optimized}),
        context={"title_mode": runtime.title_mode, "bp_mode": "optimize"},
    )

    async def second_seo() -> SEOCheck:
        return check_listing_seo(
            state["listing"],
            derived_intents,
            product_input.rootwords,
            product_input.keywords,
        )

    state["seo2"] = await _execute_stage(PipelineStage.SEO_CHECK2, state, second_seo)

    async def score() -> Scorecard:
        client = counter.wrap(factory("scorecard"))
        return await asyncio.to_thread(
            score_listing,
            product_input,
            state["listing"].title,
            [bullet.text for bullet in state["listing"].bullets],
            llm=client,
        )

    state["scorecard"] = await _execute_stage(PipelineStage.SCORECARD, state, score)
    state["stage_history"].append(PipelineStage.COMPLETED)
    return _package(state)


__all__ = ["HITLCallback", "HITLRejectedError", "PipelineStageError", "run_pipeline"]
