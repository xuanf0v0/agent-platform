"""Minimal listing models for vendored writing_mcp compatibility."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SourceListingCopy(BaseModel):
    """Source listing shape expected by writing_mcp."""

    model_config = ConfigDict(frozen=True)

    title: NonBlankText
    item_highlights: str = ""
    bullets: list[NonBlankText] = Field(min_length=1, max_length=10)
    backend_search_terms: str = ""


class OptimizedListingCopy(BaseModel):
    """Paste-ready listing shape expected by writing_mcp."""

    model_config = ConfigDict(frozen=True)

    title: NonBlankText
    item_highlights: NonBlankText
    bullets: list[NonBlankText] = Field(min_length=1, max_length=10)
    backend_search_terms: str = ""
