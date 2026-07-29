"""Final creation deliverable."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BulletDeliverable(BaseModel):
    """One bilingual bullet."""

    model_config = ConfigDict(frozen=True)

    text: str
    text_zh: str = ""


class CreationDeliverable(BaseModel):
    """Upload-oriented core fields for a new listing."""

    model_config = ConfigDict(frozen=True)

    title: str
    title_zh: str = ""
    title_chars: int = 0
    item_highlights: str
    item_highlights_zh: str = ""
    item_highlights_chars: int = 0
    bullets: list[BulletDeliverable] = Field(min_length=1, max_length=5)
    search_terms: str = ""
    search_terms_bytes: int = 0
    unresolved: tuple[str, ...] = ()
    policy_status: Literal["PASS", "WARN", "BLOCK"] = "PASS"
    policy_issues: tuple[str, ...] = ()
    notes_zh: str = ""
