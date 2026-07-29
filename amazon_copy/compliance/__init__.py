"""Amazon hard-ban / wordlist scanner (R10) and paste-ready policy."""

from __future__ import annotations

from amazon_copy.compliance.check import (
    ComplianceHit,
    ValidationResult,
    load_wordlist,
    scan_title_hard_bans,
    validate_bullets,
    validate_title,
)
from amazon_copy.compliance.paste_ready import (
    PASTE_ITEM_HIGHLIGHTS_MAX,
    PASTE_TITLE_MAX,
    PASTE_TITLE_MIN,
    PasteReadyResult,
    clamp_paste_ready_lengths,
    clamp_plain_text,
    normalize_dimension_spacing,
    rewrite_stability_absolutes,
    sanitize_paste_ready_listing,
    sanitize_paste_ready_text,
    strip_trailing_incomplete_tail,
    validate_paste_ready_listing,
)

__all__ = [
    "ComplianceHit",
    "PASTE_ITEM_HIGHLIGHTS_MAX",
    "PASTE_TITLE_MAX",
    "PASTE_TITLE_MIN",
    "PasteReadyResult",
    "ValidationResult",
    "clamp_paste_ready_lengths",
    "clamp_plain_text",
    "load_wordlist",
    "normalize_dimension_spacing",
    "rewrite_stability_absolutes",
    "sanitize_paste_ready_listing",
    "sanitize_paste_ready_text",
    "scan_title_hard_bans",
    "strip_trailing_incomplete_tail",
    "validate_bullets",
    "validate_paste_ready_listing",
    "validate_title",
]
