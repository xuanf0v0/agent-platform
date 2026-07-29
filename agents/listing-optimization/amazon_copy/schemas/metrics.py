"""SOP length validators (R4, R7, R8); plain helpers re-exported from utils.

Canonical ``strip_md_bold`` / ``plain_len`` live in
``amazon_copy.utils.text_metrics`` (R1 single source of truth).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, assert_never

from amazon_copy.schemas.enums import TitleMode
from amazon_copy.utils.text_metrics import plain_len, strip_md_bold

if TYPE_CHECKING:
    from amazon_copy.schemas.listing import BulletPoint

_TITLE_SOP_SEO_MIN: Final[int] = 100
_TITLE_SOP_SEO_MAX: Final[int] = 200
_TITLE_STRICT_MIN: Final[int] = 1
_TITLE_STRICT_MAX: Final[int] = 80
_BP_WRITE_MIN: Final[int] = 100
_BP_WRITE_MAX: Final[int] = 150
_BP_OPTIMIZE_MIN: Final[int] = 100
_BP_OPTIMIZE_MAX: Final[int] = 200

BpMode = Literal["write", "optimize"]

__all__ = [
    "BpMode",
    "parse_csv_terms",
    "plain_len",
    "strip_md_bold",
    "validate_bullet_length",
    "validate_bullets",
    "validate_no_trailing_period",
    "validate_title_length",
]


def parse_csv_terms(raw: str) -> list[str]:
    """Parse comma / fullwidth-comma separated terms; strip; drop empties."""
    if not raw or not raw.strip():
        return []
    # Fullwidth comma is intentional input separator (SOP CSV paste).
    normalized = raw.replace("\uff0c", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def validate_title_length(text: str, mode: TitleMode | str) -> None:
    """Raise ``ValueError`` if plain title length is outside mode bounds (R4)."""
    n = plain_len(text)
    resolved = mode if isinstance(mode, TitleMode) else TitleMode(mode)
    match resolved:
        case TitleMode.SOP_SEO:
            if n < _TITLE_SOP_SEO_MIN or n > _TITLE_SOP_SEO_MAX:
                msg = (
                    f"title plain_len {n} outside sop_seo range "
                    f"{_TITLE_SOP_SEO_MIN}-{_TITLE_SOP_SEO_MAX}"
                )
                raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary
        case TitleMode.STRICT_AMAZON:
            if n < _TITLE_STRICT_MIN or n > _TITLE_STRICT_MAX:
                msg = (
                    f"title plain_len {n} outside strict_amazon range "
                    f"{_TITLE_STRICT_MIN}-{_TITLE_STRICT_MAX}"
                )
                raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary
        case unreachable:
            assert_never(unreachable)


def validate_bullet_length(text: str, mode: BpMode) -> None:
    """Raise ``ValueError`` if plain BP length is outside mode bounds (R7/R8)."""
    n = plain_len(text)
    match mode:
        case "write":
            lo, hi = _BP_WRITE_MIN, _BP_WRITE_MAX
        case "optimize":
            lo, hi = _BP_OPTIMIZE_MIN, _BP_OPTIMIZE_MAX
        case unreachable:
            assert_never(unreachable)
    if n < lo or n > hi:
        msg = f"bullet plain_len {n} outside {mode} range {lo}-{hi}"
        raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary


def validate_no_trailing_period(text: str) -> None:
    """Raise if plain text ends with ``.`` (R7/R8)."""
    if strip_md_bold(text).endswith("."):
        msg = "bullet plain text must not end with '.'"
        raise ValueError(msg)  # noqa: GENERIC_ERR_OK — pydantic boundary


def validate_bullets(
    bullets: list[BulletPoint],
    mode: BpMode = "write",
) -> list[BulletPoint]:
    """Validate each bullet for trailing period + mode length; return unchanged."""
    for bp in bullets:
        validate_no_trailing_period(bp.text)
        validate_bullet_length(bp.text, mode)
    return bullets
