"""Byte and field ceilings for seller-controlled optimization input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from typing_extensions import override

MAX_LISTING_INPUT_BYTES: Final[int] = 64_000
MAX_LISTING_INPUT_CHARS: Final[int] = 32_000
MAX_LISTING_TITLE_BYTES: Final[int] = 4_096
MAX_LISTING_HIGHLIGHTS_BYTES: Final[int] = 8_192
MAX_LISTING_POINT_BYTES: Final[int] = 8_192
MAX_STUDIO_INPUT_BYTES: Final[int] = 64_000
MAX_CLARIFICATION_INPUT_BYTES: Final[int] = 8_000

InputLimitCode: TypeAlias = Literal[
    "listing_too_large",
    "listing_field_too_large",
    "studio_input_too_large",
    "clarification_too_large",
]


@dataclass(frozen=True, slots=True)
class InputSecurityError(ValueError):
    """A seller-controlled input crossed a fixed byte or field ceiling."""

    code: InputLimitCode

    @override
    def __str__(self) -> str:
        """Return the stable boundary code without seller-controlled text."""
        return self.code


def _require_bytes(text: str, *, limit: int, code: InputLimitCode) -> None:
    if len(text.encode("utf-8")) > limit:
        raise InputSecurityError(code)


def require_listing_input(text: str) -> None:
    """Reject an oversized Listing before normalization or parsing."""
    _require_bytes(text, limit=MAX_LISTING_INPUT_BYTES, code="listing_too_large")


def require_listing_fields(
    *,
    title: str,
    item_highlights: str,
    points: list[str],
) -> None:
    """Reject oversized parsed Listing fields before model construction."""
    _require_bytes(title, limit=MAX_LISTING_TITLE_BYTES, code="listing_field_too_large")
    _require_bytes(
        item_highlights,
        limit=MAX_LISTING_HIGHLIGHTS_BYTES,
        code="listing_field_too_large",
    )
    for point in points:
        _require_bytes(point, limit=MAX_LISTING_POINT_BYTES, code="listing_field_too_large")


def require_studio_input(text: str) -> None:
    """Reject an oversized Studio request before normalization or hashing."""
    _require_bytes(text, limit=MAX_STUDIO_INPUT_BYTES, code="studio_input_too_large")


def require_clarification_input(text: str) -> None:
    """Reject an oversized clarification before it enters session state."""
    _require_bytes(text, limit=MAX_CLARIFICATION_INPUT_BYTES, code="clarification_too_large")


__all__ = [
    "MAX_CLARIFICATION_INPUT_BYTES",
    "MAX_LISTING_INPUT_BYTES",
    "MAX_LISTING_INPUT_CHARS",
    "MAX_LISTING_POINT_BYTES",
    "MAX_LISTING_TITLE_BYTES",
    "MAX_STUDIO_INPUT_BYTES",
    "InputSecurityError",
    "require_clarification_input",
    "require_listing_fields",
    "require_listing_input",
    "require_studio_input",
]
