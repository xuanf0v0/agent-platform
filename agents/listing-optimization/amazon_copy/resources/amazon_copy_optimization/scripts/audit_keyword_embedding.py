"""Thin CLI for the typed keyword-embedding audit library."""

import json
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import ValidationError

from amazon_copy.resources.amazon_copy_optimization.keyword_audit import (
    audit_keyword_embedding,
    load_keywords,
)
from amazon_copy.resources.amazon_copy_optimization.keyword_audit_models import (
    KeywordAuditListing,
)

app = typer.Typer(add_completion=False)
_INVALID_LISTING_MESSAGE: Final = "listing JSON is invalid"
_UNREADABLE_KEYWORDS_MESSAGE: Final = "keywords file is unreadable"
_MISSING_KEYWORDS_MESSAGE: Final = "provide at least one --keyword or --keywords-file"


@app.command()
def run_audit(
    listing_json: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    keyword: Annotated[list[str] | None, typer.Option("--keyword")] = None,
    keywords_file: Annotated[
        Path | None,
        typer.Option("--keywords-file", exists=True, file_okay=True, dir_okay=False),
    ] = None,
) -> None:
    """Print the keyword-embedding audit as UTF-8 JSON."""
    try:
        listing = KeywordAuditListing.model_validate_json(listing_json.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise typer.BadParameter(
            _INVALID_LISTING_MESSAGE,
            param_hint="listing_json",
        ) from error
    try:
        keywords = load_keywords(keyword or (), keywords_file)
    except OSError as error:
        raise typer.BadParameter(
            _UNREADABLE_KEYWORDS_MESSAGE,
            param_hint="--keywords-file",
        ) from error
    if not keywords:
        raise typer.BadParameter(
            _MISSING_KEYWORDS_MESSAGE,
            param_hint="--keyword",
        )
    result = audit_keyword_embedding(listing, keywords)
    typer.echo(json.dumps(result.to_payload(), ensure_ascii=False, indent=2))


def main() -> None:
    """Run the installed command-line surface."""
    app(prog_name="audit-keyword-embedding")


if __name__ == "__main__":
    main()
