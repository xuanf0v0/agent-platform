"""Typer delivery surface for the Amazon copywriting workflows."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from amazon_copy.config import Settings, apply_runtime_settings
from amazon_copy.exporters import export_package
from amazon_copy.orchestrator.asyncio_pipeline import run_pipeline
from amazon_copy.schemas import PipelineMode, PipelineStage, ProductInput

app = typer.Typer(
    name="amz-copy",
    help="Amazon listing copy optimizer: Title + five BP + SEO + scorecard.",
    no_args_is_help=True,
)
console = Console()

RequiredText = Annotated[str, typer.Option()]
OptionalText = Annotated[str | None, typer.Option()]
OutputPath = Annotated[Path, typer.Option(file_okay=False, dir_okay=True)]
MockFlag = Annotated[bool, typer.Option("--mock", help="Run offline with deterministic fixtures.")]
TitleModeOption = Annotated[str, typer.Option("--title-mode", help="sop_seo or strict_amazon")]

_EN_MARKETS = {
    "us",
    "usa",
    "unitedstates",
    "美国",
    "美國",
    "uk",
    "gb",
    "greatbritain",
    "unitedkingdom",
    "英国",
    "英國",
    "ca",
    "canada",
    "加拿大",
    "au",
    "australia",
    "澳大利亚",
    "澳洲",
}


def resolve_locale(market: str, locale: str | None) -> str:
    """Resolve v1 English marketplaces or require an explicit locale (R15)."""
    if locale and locale.strip():
        return locale.strip()
    normalized = "".join(character for character in market.casefold() if character.isalnum())
    if normalized in _EN_MARKETS:
        return "en"
    message = f"market {market!r} is not a v1 English alias; pass --locale explicitly"
    raise typer.BadParameter(message, param_hint="--locale")


def _runtime(*, mock: bool, title_mode: str, hitl: bool, locale: str) -> Settings:
    try:
        runtime = Settings.model_validate(
            {
                "mock": mock,
                "title_mode": title_mode,
                "hitl_confirm": hitl,
                "locale": locale,
            }
        )
    except ValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not runtime.mock and not runtime.effective_api_key:
        message = "OPENAI_API_KEY is required for real mode; use --mock for offline execution"
        raise typer.BadParameter(message, param_hint="--mock")
    return apply_runtime_settings(runtime)


def _product(  # noqa: PLR0913 - mirrors the explicit user-facing form fields
    *,
    product: str,
    seller_name: str | None,
    market: str,
    instruction: str,
    asin1: str | None,
    asin2: str | None,
    asin3: str | None,
    asin4: str | None,
    rootwords: str,
    keywords: str,
    locale: str,
) -> ProductInput:
    try:
        return ProductInput.model_validate(
            {
                "product": product,
                "seller_name": seller_name.strip() or None if seller_name else None,
                "market": market,
                "instruction": instruction,
                "asin1": asin1,
                "asin2": asin2,
                "asin3": asin3,
                "asin4": asin4,
                "rootwords": rootwords,
                "keywords": keywords,
                "locale": locale,
            }
        )
    except ValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _hitl(stage: PipelineStage, _payload: object) -> bool:
    labels = {
        PipelineStage.RESEARCH: "Research pack",
        PipelineStage.SELLING_POINTS: "Five selling points",
        PipelineStage.BP_WRITE: "Listing draft",
    }
    return typer.confirm(f"Approve {labels[stage]}?")


def _execute(  # noqa: PLR0913 - one adapter for all five commands
    product_input: ProductInput,
    *,
    mode: PipelineMode,
    output: Path,
    settings: Settings,
    title: str = "",
    bullets: list[str] | None = None,
    intents: list[str] | None = None,
    instruction: str = "",
    full_checks: bool = False,
) -> None:
    try:
        package = asyncio.run(
            run_pipeline(
                product_input,
                mode,
                title=title,
                bullets=bullets,
                intents=intents or (),
                instructions=instruction,
                full_checks=full_checks,
                settings=settings,
                hitl_callback=_hitl if settings.hitl_confirm else None,
            )
        )
        paths = export_package(package, output)
    except (ValidationError, ValueError, RuntimeError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Completed[/green] {mode.value}: {paths['json'].parent.resolve()}")


def _write_command(  # noqa: PLR0913 - keeps Typer parsing separate from orchestration
    mode: PipelineMode,
    product: str,
    seller_name: str | None,
    market: str,
    instruction: str,
    asin1: str | None,
    asin2: str | None,
    asin3: str | None,
    asin4: str | None,
    rootwords: str,
    keywords: str,
    output: Path,
    mock: bool,
    title_mode: str,
    hitl: bool,
    locale: str | None,
    full_checks: bool,
) -> None:
    resolved_locale = resolve_locale(market, locale)
    runtime = _runtime(mock=mock, title_mode=title_mode, hitl=hitl, locale=resolved_locale)
    product_input = _product(
        product=product,
        seller_name=seller_name,
        market=market,
        instruction=instruction,
        asin1=asin1,
        asin2=asin2,
        asin3=asin3,
        asin4=asin4,
        rootwords=rootwords,
        keywords=keywords,
        locale=resolved_locale,
    )
    _execute(
        product_input,
        mode=mode,
        output=output,
        settings=runtime,
        instruction=instruction,
        full_checks=full_checks,
    )


@app.command("run")
def run_cmd(  # noqa: PLR0913
    product: Annotated[str, typer.Option("--product", help="Product name/spec.")],
    market: Annotated[str, typer.Option("--market", help="US/UK/CA/AU or Chinese alias.")],
    seller_name: Annotated[
        str | None,
        typer.Option("--seller-name", help="Known seller identity to exclude from strict titles."),
    ] = None,
    instruction: Annotated[str, typer.Option("--instruction")] = "",
    asin1: OptionalText = None,
    asin2: OptionalText = None,
    asin3: OptionalText = None,
    asin4: OptionalText = None,
    rootwords: RequiredText = "",
    keywords: RequiredText = "",
    output: OutputPath = Path("outputs/latest"),
    mock: MockFlag = False,
    title_mode: TitleModeOption = "sop_seo",
    hitl: Annotated[
        bool, typer.Option("--hitl", help="Confirm exactly three pipeline gates.")
    ] = False,
    locale: Annotated[str | None, typer.Option("--locale")] = None,
    full_checks: Annotated[bool, typer.Option("--full-checks")] = False,
) -> None:
    """Research, write, optimize, audit SEO, score, and export."""
    _write_command(
        PipelineMode.RUN,
        product,
        seller_name,
        market,
        instruction,
        asin1,
        asin2,
        asin3,
        asin4,
        rootwords,
        keywords,
        output,
        mock,
        title_mode,
        hitl,
        locale,
        full_checks,
    )


@app.command("write")
def write_cmd(  # noqa: PLR0913
    product: Annotated[str, typer.Option("--product")],
    market: Annotated[str, typer.Option("--market")],
    seller_name: Annotated[
        str | None,
        typer.Option("--seller-name", help="Known seller identity to exclude from strict titles."),
    ] = None,
    instruction: Annotated[str, typer.Option("--instruction")] = "",
    asin1: OptionalText = None,
    asin2: OptionalText = None,
    asin3: OptionalText = None,
    asin4: OptionalText = None,
    rootwords: RequiredText = "",
    keywords: RequiredText = "",
    output: OutputPath = Path("outputs/latest"),
    mock: MockFlag = False,
    title_mode: TitleModeOption = "sop_seo",
    hitl: Annotated[bool, typer.Option("--hitl")] = False,
    locale: Annotated[str | None, typer.Option("--locale")] = None,
    full_checks: Annotated[bool, typer.Option("--full-checks")] = False,
) -> None:
    """Research and write five title candidates + five BP; optionally run full checks."""
    _write_command(
        PipelineMode.WRITE,
        product,
        seller_name,
        market,
        instruction,
        asin1,
        asin2,
        asin3,
        asin4,
        rootwords,
        keywords,
        output,
        mock,
        title_mode,
        hitl,
        locale,
        full_checks,
    )


def _listing_command(  # noqa: PLR0913 - shared listing-only CLI adapter
    mode: PipelineMode,
    product: str,
    market: str,
    instruction: str,
    title: str,
    bullet: list[str] | None,
    rootwords: str,
    keywords: str,
    output: Path,
    mock: bool,
    title_mode: str,
    hitl: bool,
    locale: str | None,
    full_checks: bool,
    intents: str,
) -> None:
    resolved_locale = resolve_locale(market, locale)
    runtime = _runtime(mock=mock, title_mode=title_mode, hitl=hitl, locale=resolved_locale)
    product_input = _product(
        product=product,
        seller_name=None,
        market=market,
        instruction=instruction,
        asin1=None,
        asin2=None,
        asin3=None,
        asin4=None,
        rootwords=rootwords,
        keywords=keywords,
        locale=resolved_locale,
    )
    parsed_intents = [
        value.strip() for value in intents.replace("\uff0c", ",").split(",") if value.strip()
    ]
    _execute(
        product_input,
        mode=mode,
        output=output,
        settings=runtime,
        title=title,
        bullets=bullet,
        intents=parsed_intents,
        instruction=instruction,
        full_checks=full_checks,
    )


@app.command("optimize")
def optimize_cmd(  # noqa: PLR0913
    product: Annotated[str, typer.Option("--product")],
    market: Annotated[str, typer.Option("--market")],
    instruction: Annotated[
        str, typer.Option("--instruction")
    ] = "Optimize for shopper intent and clarity",
    title: Annotated[str, typer.Option("--title")] = "",
    bullet: Annotated[list[str] | None, typer.Option("--bullet", "-b")] = None,
    rootwords: RequiredText = "",
    keywords: RequiredText = "",
    output: OutputPath = Path("outputs/latest"),
    mock: MockFlag = False,
    title_mode: TitleModeOption = "sop_seo",
    hitl: Annotated[bool, typer.Option("--hitl")] = False,
    locale: Annotated[str | None, typer.Option("--locale")] = None,
    full_checks: Annotated[bool, typer.Option("--full-checks")] = False,
) -> None:
    """Optimize exactly five existing bullet points."""
    _listing_command(
        PipelineMode.OPTIMIZE,
        product,
        market,
        instruction,
        title,
        bullet,
        rootwords,
        keywords,
        output,
        mock,
        title_mode,
        hitl,
        locale,
        full_checks,
        "",
    )


@app.command("seo")
def seo_cmd(  # noqa: PLR0913
    product: Annotated[str, typer.Option("--product")],
    market: Annotated[str, typer.Option("--market")],
    instruction: Annotated[str, typer.Option("--instruction")] = "",
    title: Annotated[str, typer.Option("--title")] = "",
    bullet: Annotated[list[str] | None, typer.Option("--bullet", "-b")] = None,
    intents: Annotated[str, typer.Option("--intents")] = "",
    rootwords: RequiredText = "",
    keywords: RequiredText = "",
    output: OutputPath = Path("outputs/latest"),
    mock: MockFlag = False,
    title_mode: TitleModeOption = "sop_seo",
    hitl: Annotated[bool, typer.Option("--hitl")] = False,
    locale: Annotated[str | None, typer.Option("--locale")] = None,
    full_checks: Annotated[bool, typer.Option("--full-checks")] = False,
) -> None:
    """Build deterministic SEO V/X tables for an existing listing."""
    _listing_command(
        PipelineMode.SEO,
        product,
        market,
        instruction,
        title,
        bullet,
        rootwords,
        keywords,
        output,
        mock,
        title_mode,
        hitl,
        locale,
        full_checks,
        intents,
    )


@app.command("analyze")
def analyze_cmd(  # noqa: PLR0913
    product: Annotated[str, typer.Option("--product")],
    market: Annotated[str, typer.Option("--market")],
    instruction: Annotated[str, typer.Option("--instruction")] = "",
    title: Annotated[str, typer.Option("--title")] = "",
    bullet: Annotated[list[str] | None, typer.Option("--bullet", "-b")] = None,
    rootwords: RequiredText = "",
    keywords: RequiredText = "",
    output: OutputPath = Path("outputs/latest"),
    mock: MockFlag = False,
    title_mode: TitleModeOption = "sop_seo",
    hitl: Annotated[bool, typer.Option("--hitl")] = False,
    locale: Annotated[str | None, typer.Option("--locale")] = None,
    full_checks: Annotated[bool, typer.Option("--full-checks")] = False,
) -> None:
    """Score an existing listing across the fixed nine dimensions."""
    _listing_command(
        PipelineMode.ANALYZE,
        product,
        market,
        instruction,
        title,
        bullet,
        rootwords,
        keywords,
        output,
        mock,
        title_mode,
        hitl,
        locale,
        full_checks,
        "",
    )


if __name__ == "__main__":
    app()
