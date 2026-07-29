"""Narrow entry functions for Amazon BP optimize, SEO, and analyze modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from amazon_copy.agents.scorecard import ScorecardError, score_listing
from amazon_copy.agents.seo import check_seo
from amazon_copy.agents.writer import rewrite
from amazon_copy.schemas import BulletPoint, ProductInput, Scorecard, SEOCheck

if TYPE_CHECKING:
    from collections.abc import Sequence

    from amazon_copy.llm import LLMClient


class _ListingModeInput(BaseModel):
    """Validation boundary shared by the three listing-only workflows."""

    model_config = ConfigDict(frozen=True)

    title: str = ""
    bullets: list[str] = Field(min_length=5, max_length=5)

    @field_validator("bullets")
    @classmethod
    def _nonblank_bullets(cls, value: list[str]) -> list[str]:
        if any(not bullet.strip() for bullet in value):
            message = "bullets must contain exactly five non-empty BP strings"
            raise ValueError(message)
        return value


def _validate_listing(
    title: str,
    bullets: Sequence[str | BulletPoint] | None,
) -> _ListingModeInput:
    normalized = None
    if bullets is not None:
        normalized = [
            bullet.text if isinstance(bullet, BulletPoint) else bullet for bullet in bullets
        ]
    return _ListingModeInput.model_validate({"title": title, "bullets": normalized})


def optimize(
    product: ProductInput,
    bullets: Sequence[str | BulletPoint] | None,
    *,
    instructions: str = "Optimize these Amazon bullet points for shopper intent and clarity",
    llm: LLMClient | None = None,
) -> list[BulletPoint]:
    """Run only Workflow2's BP optimizer; source BP text is treated as data."""
    validated = _validate_listing("", bullets)
    source = [
        BulletPoint.model_validate(
            {"text": text, "text_zh": "待优化"},
            context={"skip_bp_length": True},
        )
        for text in validated.bullets
    ]
    effective_instruction = instructions.strip() or "Optimize for shopper intent and clarity"
    return rewrite(source, product, effective_instruction, llm=llm)


def seo(
    *,
    title: str = "",
    bullets: Sequence[str | BulletPoint] | None,
    intents: Sequence[str] = (),
    rootwords: Sequence[str] = (),
    keywords: Sequence[str] = (),
) -> SEOCheck:
    """Run only Workflow3's deterministic V/X tables (zero LLM calls)."""
    validated = _validate_listing(title, bullets)
    return check_seo(
        validated.title,
        validated.bullets,
        intents,
        rootwords,
        keywords,
    )


def analyze(
    *,
    product: ProductInput,
    title: str = "",
    bullets: Sequence[str | BulletPoint] | None,
    llm: LLMClient | None = None,
) -> Scorecard:
    """Run only Workflow4's one-call, nine-dimension listing review."""
    validated = _validate_listing(title, bullets)
    return score_listing(
        product,
        validated.title,
        validated.bullets,
        llm=llm,
    )


__all__ = ["ScorecardError", "analyze", "optimize", "seo"]
