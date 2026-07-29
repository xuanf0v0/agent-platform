"""Optional CLI surface for listing creation."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from amazon_create.config import Settings
from amazon_create.pipeline.creation_pipeline import (
    apply_user_message,
    new_session,
    parse_brief_message,
    run_fast_path,
)

app = typer.Typer(name="amz-create", help="Amazon listing creation (staged / fast).")
console = Console()


@app.command("fast")
def fast(
    product: str = typer.Option(..., "--product"),
    market: str = typer.Option("US", "--market"),
    specs: str = typer.Option("", "--specs"),
    brand: str = typer.Option("", "--brand"),
    mock: bool = typer.Option(True, "--mock/--live"),
) -> None:
    """One-shot create core fields from brief."""
    settings = Settings(mock=mock)
    session = new_session(fast_path=True)
    session.brief = parse_brief_message(
        f"产品: {product}\n站点: {market}\n规格: {specs}\n品牌: {brand}"
    )
    session = run_fast_path(session, settings=settings)
    if session.deliverable is None:
        console.print(f"[red]failed: {session.error or session.last_message_zh}")
        raise typer.Exit(1)
    d = session.deliverable
    auth = session.claim_authorization
    console.print(
        json.dumps(
            {
                "title": d.title,
                "item_highlights": d.item_highlights,
                "bullets": [b.text for b in d.bullets],
                "search_terms": d.search_terms,
                "policy_status": d.policy_status,
                "evidence_allowed": None if auth is None else auth.allowed,
                "blocked_claims": [] if auth is None else list(auth.blocked_claims),
                "stage": session.stage.value,
                "counts": {
                    "title_chars": d.title_chars,
                    "item_highlights_chars": d.item_highlights_chars,
                    "search_terms_bytes": d.search_terms_bytes,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("chat")
def chat(
    message: str = typer.Argument(...),
    mock: bool = typer.Option(True, "--mock/--live"),
) -> None:
    """Single-turn pipeline step (stateless demo)."""
    settings = Settings(mock=mock)
    session = new_session()
    session = apply_user_message(session, message, settings=settings)
    console.print(session.last_message_zh)
    console.print(f"stage={session.stage} status={session.status}")


if __name__ == "__main__":
    app()
