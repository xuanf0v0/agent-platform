"""Title, bullet-point, and listing-draft domain models (R4, R7, R8)."""

from __future__ import annotations

from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    model_validator,
)

from amazon_copy.schemas.enums import TitleMode
from amazon_copy.schemas.metrics import (
    BpMode,
    strip_md_bold,
    validate_bullet_length,
    validate_no_trailing_period,
    validate_title_length,
)


class TitleCandidate(BaseModel):
    """One of five title candidates before winner selection."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    text_zh: str = ""
    score_hint: float | None = Field(default=None, ge=0)

    @computed_field
    def plain_len(self) -> int:
        """Plain character count of the English title."""
        return len(strip_md_bold(self.text))


class BulletPoint(BaseModel):
    """Single bullet with bilingual text; trailing-period hard fail (R7).

    Length bounds are mode-aware: pass ``context={"bp_mode": "write"|"optimize"}``
    to ``model_validate``, or call ``validate_bullet_length`` /
    ``validate_bullets`` explicitly. Default context mode is ``write``.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, description="Target-locale bullet body")
    text_zh: str = Field(default="", description="Chinese translation")
    change_rationale: str = Field(
        default="",
        description="Optimize-mode explanation; bold markdown is retained for review",
    )

    @computed_field
    def plain_len(self) -> int:
        """Plain character count of the target-locale bullet."""
        return len(strip_md_bold(self.text))

    @model_validator(mode="after")
    def _enforce_bp_rules(self, info: ValidationInfo) -> Self:
        validate_no_trailing_period(self.text)
        ctx = info.context or {}
        if ctx.get("skip_bp_length"):
            return self
        raw_mode = ctx.get("bp_mode", "write")
        mode: BpMode = raw_mode if raw_mode in ("write", "optimize") else "write"
        validate_bullet_length(self.text, mode)
        return self


class ListingDraft(BaseModel):
    """Winner title + five bullets (+ candidates).

    Title length: ``context={"title_mode": TitleMode.SOP_SEO|STRICT_AMAZON}``.
    BP length: ``context={"bp_mode": "write"|"optimize"}`` (use with
    ``validate_bullets`` for pre-built bullets).
    """

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    title_zh: str = ""
    title_candidates: list[TitleCandidate] = Field(default_factory=list)
    bullets: list[BulletPoint] = Field(min_length=5, max_length=5)

    @computed_field
    def title_plain_len(self) -> int:
        """Plain character count of the winner title."""
        return len(strip_md_bold(self.title))

    @model_validator(mode="after")
    def _enforce_title_len(self, info: ValidationInfo) -> Self:
        ctx = info.context or {}
        if ctx.get("skip_title_length"):
            return self
        raw_mode = ctx.get("title_mode", TitleMode.SOP_SEO)
        mode = raw_mode if isinstance(raw_mode, TitleMode) else TitleMode(raw_mode)
        validate_title_length(self.title, mode)
        return self
