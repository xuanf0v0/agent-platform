"""Paste-ready listing policy (UI optimize path): 75/125 length + claim bans.

Separate from Studio SOP SEO title bands (100–200). Pure validation and
deterministic sanitize only — no I/O, no LLM. Callers pass
``allow_weighted_base=True`` only when verified facts explicitly support a
weighted base.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from amazon_create.utils.text_metrics import plain_len, strip_md_bold

PASTE_TITLE_MIN: Final[int] = 10
PASTE_TITLE_MAX: Final[int] = 75
PASTE_ITEM_HIGHLIGHTS_MAX: Final[int] = 125

# Prefer word-boundary trim; never shrink below this fraction of the budget.
_WORD_TRIM_FLOOR_RATIO: Final[float] = 0.55

# Casefold substring denylist (always error on paste-ready path).
# Longer phrases first so multi-word hits win over shorter overlaps.
_CLAIM_DENYLIST: Final[tuple[str, ...]] = (
    "long-term outdoor",
    "long term outdoor",
    "ensure long-term",
    "breezy conditions",
    "wind-resistant",
    "wind resistant",
    "windproof",
    "anti-rust",
    "antirust",
    "rust-proof",
    "rust proof",
    "dual-tone",
    "dual tone",
)

_WEIGHTED_BASE_PHRASE: Final[str] = "weighted base"

# Shared count across leather + water bags, e.g. "8 leather and water bags".
_ACCESSORY_AMBIGUITY_RE: Final[re.Pattern[str]] = re.compile(
    r"\d+\s+leather\s+and\s+water\s+bags?",
    flags=re.IGNORECASE,
)

# Collapse whitespace left after phrase excision.
_MULTI_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE: Final[re.Pattern[str]] = re.compile(r"\s+([,.;:!?])")

# Dimension triples first, then pairs (pair pattern skips start of a triple).
_DIM_TRIPLE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*"
    r"(\d+(?:\.\d+)?)(?![\d.])",
)
_DIM_PAIR_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)(?![\d.]|\s*[xX×])",
)

# Incomplete title/IH tails left by length clamp (e.g. "... Frame with 8").
_HANGING_WITH_COUNT_RE: Final[re.Pattern[str]] = re.compile(
    r"\s+(?:with|and|plus|including)\s+\d+\s*$",
    flags=re.IGNORECASE,
)
_HANGING_PREPOSITION_RE: Final[re.Pattern[str]] = re.compile(
    r"\s+(?:with|and|for|in|of|the|a|an|to|or|on|at|by|from|as|plus|"
    r"including|includes|into|onto)\s*$",
    flags=re.IGNORECASE,
)
_TRAILING_PUNCT: Final[str] = " \t,;:-|/\\"

# Fixed high-risk absolute stability phrasing (light rewrite, not hard errors).
_STABILITY_REWRITES: Final[tuple[tuple[str, str], ...]] = (
    ("ensures reliable stability", "helps improve stability"),
    ("ensure reliable stability", "help improve stability"),
    ("ensures stability", "helps improve stability"),
    ("ensure stability", "help improve stability"),
    ("various surfaces", "level surfaces"),
)

# Item Highlights fragment indicators — a complete product phrase never starts
# with these patterns (lowercase, orphan conjunction, standalone component noun).
_IH_FRAGMENT_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:[a-z]|\s*(?:and|or|with|for|but|,)\b)",
)
_IH_FRAGMENT_PATTERNS: Final[tuple[str, ...]] = (
    "screws,",
    "straps,",
    "water bags,",
    "anchors,",
    "hardware,",
    "and a",
    "with a",
    "also includes",
)

# Vague filler phrases that add no decision value and harm readability.
_BULLET_FILLER_PHRASES: Final[tuple[str, ...]] = (
    "and more",
    "and much more",
    "etc.",
    "and so on",
    "year-round reuse",
    "perfect for any occasion",
)

# Bullet must not end with an obvious mid-sentence truncation.
_BULLET_TRUNCATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:under|with|in|for|at|by|near|without|during|before|after|while)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PasteReadyResult:
    """Outcome of paste-ready listing validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _field_label(name: str) -> str:
    return name


def _scan_claim_denylist(text: str, field_name: str, errors: list[str]) -> None:
    folded = text.casefold()
    for phrase in _CLAIM_DENYLIST:
        if phrase in folded:
            errors.append(
                f"{_field_label(field_name)}: banned claim phrase {phrase!r}",
            )


def _scan_weighted_base(
    text: str,
    field_name: str,
    errors: list[str],
    *,
    allow_weighted_base: bool,
) -> None:
    if allow_weighted_base:
        return
    if _WEIGHTED_BASE_PHRASE in text.casefold():
        errors.append(
            f"{_field_label(field_name)}: banned claim phrase "
            f"{_WEIGHTED_BASE_PHRASE!r} (set allow_weighted_base when verified)",
        )


def _scan_accessory_ambiguity(text: str, field_name: str, errors: list[str]) -> None:
    if _ACCESSORY_AMBIGUITY_RE.search(text) is not None:
        errors.append(
            f"{_field_label(field_name)}: accessory ambiguity "
            f"(split leather straps and water bags; avoid 'N leather and water bags')",
        )


def _scan_text_fields(
    text: str,
    field_name: str,
    errors: list[str],
    *,
    allow_weighted_base: bool,
) -> None:
    if not text:
        return
    _scan_claim_denylist(text, field_name, errors)
    _scan_weighted_base(
        text,
        field_name,
        errors,
        allow_weighted_base=allow_weighted_base,
    )
    _scan_accessory_ambiguity(text, field_name, errors)


def _scan_ih_fragment(text: str, errors: list[str]) -> None:
    """Add an error when the Item Highlights is an obvious sentence fragment."""
    stripped = text.strip()
    if _IH_FRAGMENT_START_RE.match(stripped):
        errors.append(
            "item_highlights: starts with lowercase or orphan conjunction "
            f"({stripped[:40]!r}); must be a complete product phrase or pack list"
        )
        return
    folded = stripped.casefold()
    for pattern in _IH_FRAGMENT_PATTERNS:
        if folded.startswith(pattern.casefold()):
            errors.append(
                f"item_highlights: begins with fragment indicator {pattern!r}; "
                "write a complete sentence or structured pack list"
            )
            return


def _scan_bullet_quality(bullet: str, index: int, errors: list[str]) -> None:
    """Flag filler phrases and mid-sentence truncation in a bullet."""
    folded = bullet.casefold()
    for phrase in _BULLET_FILLER_PHRASES:
        if phrase.casefold() in folded:
            errors.append(
                f"bullet[{index}]: contains empty filler {phrase!r}; "
                "replace with a specific supported fact"
            )
            break
    if _BULLET_TRUNCATION_RE.search(bullet.rstrip(".,;: ")):
        errors.append(
            f"bullet[{index}]: ends mid-sentence with dangling preposition; "
            "complete the sentence or remove the trailing fragment"
        )


def normalize_dimension_spacing(text: str) -> str:
    """Rewrite compact dimensions to ``N x N`` / ``N x N x N`` with spaces."""
    if not text:
        return text
    out = _DIM_TRIPLE_RE.sub(r"\1 x \2 x \3", text)
    return _DIM_PAIR_RE.sub(r"\1 x \2", out)


def strip_trailing_incomplete_tail(text: str) -> str:
    """Drop hanging prepositions / ``with N`` tails left by length clamping."""
    if not text:
        return text
    out = text.strip()
    for _ in range(8):
        prev = out
        out = out.rstrip(_TRAILING_PUNCT)
        out = _HANGING_WITH_COUNT_RE.sub("", out)
        out = _HANGING_PREPOSITION_RE.sub("", out)
        out = out.rstrip(_TRAILING_PUNCT)
        if out == prev:
            break
    return out.strip()


def rewrite_stability_absolutes(text: str) -> str:
    """Soft-rewrite fixed absolute stability phrases (not hard validation)."""
    if not text:
        return text
    out = text
    for src, dst in _STABILITY_REWRITES:
        folded = out.casefold()
        needle = src.casefold()
        if needle not in folded:
            continue
        pieces: list[str] = []
        start = 0
        pos = folded.find(needle, start)
        while pos != -1:
            pieces.append(out[start:pos])
            pieces.append(dst)
            start = pos + len(needle)
            pos = folded.find(needle, start)
        pieces.append(out[start:])
        out = "".join(pieces)
    return out


def clamp_plain_text(text: str, max_len: int) -> str:
    """Hard-cap plain length at *max_len*, preferring a word boundary.

    Strips markdown bold markers first (same metric as ``plain_len``). After the
    cut, hanging tails like ``with 8`` are stripped so titles stay complete.
    """
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    plain = strip_md_bold(text).strip()
    if len(plain) <= max_len:
        return strip_trailing_incomplete_tail(plain)
    cut = plain[:max_len]
    floor = max(1, int(max_len * _WORD_TRIM_FLOOR_RATIO))
    next_ch = plain[max_len : max_len + 1]
    if cut and not cut[-1].isspace() and next_ch and not next_ch.isspace():
        last_space = cut.rfind(" ")
        if last_space >= floor:
            cut = cut[:last_space]
    cut = strip_trailing_incomplete_tail(cut)
    if len(cut) > max_len:
        cut = strip_trailing_incomplete_tail(cut[:max_len])
    return cut


def clamp_paste_ready_lengths(
    title: str,
    item_highlights: str,
) -> tuple[str, str]:
    """Return title/IH clamped to paste-ready plain-length budgets (75 / 125)."""
    return (
        clamp_plain_text(title, PASTE_TITLE_MAX),
        clamp_plain_text(item_highlights, PASTE_ITEM_HIGHLIGHTS_MAX),
    )


def _excise_phrase_casefold(text: str, phrase: str) -> str:
    """Remove all case-insensitive occurrences of *phrase* from *text*."""
    if not phrase or not text:
        return text
    folded = text.casefold()
    needle = phrase.casefold()
    if needle not in folded:
        return text
    out: list[str] = []
    start = 0
    pos = folded.find(needle, start)
    while pos != -1:
        out.append(text[start:pos])
        start = pos + len(needle)
        pos = folded.find(needle, start)
    out.append(text[start:])
    return "".join(out)


def _cleanup_after_excise(text: str) -> str:
    cleaned = _MULTI_SPACE_RE.sub(" ", text)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)
    return cleaned.strip(_TRAILING_PUNCT)


def sanitize_paste_ready_text(
    text: str,
    *,
    allow_weighted_base: bool = False,
) -> str:
    """Normalize dims, strip bans, soften absolute stability, fix accessories."""
    if not text:
        return text
    out = strip_md_bold(text)
    out = normalize_dimension_spacing(out)
    for phrase in _CLAIM_DENYLIST:
        out = _excise_phrase_casefold(out, phrase)
    if not allow_weighted_base:
        out = _excise_phrase_casefold(out, _WEIGHTED_BASE_PHRASE)
    out = _ACCESSORY_AMBIGUITY_RE.sub("leather straps and water bags", out)
    out = rewrite_stability_absolutes(out)
    out = _cleanup_after_excise(out)
    # Re-capitalize first letter when ban removal left a lowercase start.
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return strip_trailing_incomplete_tail(out)


def sanitize_paste_ready_listing(
    title: str,
    item_highlights: str,
    bullets: Sequence[str],
    *,
    allow_weighted_base: bool = False,
) -> tuple[str, str, list[str]]:
    """Sanitize all listing fields, then clamp title/IH plain-length budgets."""
    clean_title = sanitize_paste_ready_text(
        title,
        allow_weighted_base=allow_weighted_base,
    )
    clean_ih = sanitize_paste_ready_text(
        item_highlights,
        allow_weighted_base=allow_weighted_base,
    )
    clean_bullets = [
        sanitize_paste_ready_text(b, allow_weighted_base=allow_weighted_base) for b in bullets
    ]
    clean_title, clean_ih = clamp_paste_ready_lengths(clean_title, clean_ih)
    clean_title = strip_trailing_incomplete_tail(clean_title)
    clean_ih = strip_trailing_incomplete_tail(clean_ih)
    return clean_title, clean_ih, clean_bullets


def validate_paste_ready_listing(
    title: str,
    item_highlights: str,
    bullets: Sequence[str],
    *,
    allow_weighted_base: bool = False,
) -> PasteReadyResult:
    """Validate a listing for the paste-ready (UI optimize) path.

    Checks title plain length [10, 75], non-blank item_highlights plain length
    ≤125, claim denylist (including dual-tone always), weighted base unless
    allowed, and accessory ambiguity patterns on title, IH, and each bullet.
    """
    errors: list[str] = []
    warnings: list[str] = []

    title_len = plain_len(title)
    if title_len < PASTE_TITLE_MIN:
        errors.append(
            f"title: plain length {title_len} is below minimum {PASTE_TITLE_MIN}",
        )
    elif title_len > PASTE_TITLE_MAX:
        errors.append(
            f"title: plain length {title_len} exceeds paste-ready maximum {PASTE_TITLE_MAX} (75)",
        )

    ih_stripped = item_highlights.strip()
    if not ih_stripped:
        errors.append("item_highlights: required and must be non-blank")
    else:
        ih_len = plain_len(item_highlights)
        if ih_len > PASTE_ITEM_HIGHLIGHTS_MAX:
            errors.append(
                f"item_highlights: plain length {ih_len} exceeds maximum "
                f"{PASTE_ITEM_HIGHLIGHTS_MAX}",
            )
        _scan_ih_fragment(ih_stripped, errors)

    _scan_text_fields(
        title,
        "title",
        errors,
        allow_weighted_base=allow_weighted_base,
    )
    _scan_text_fields(
        item_highlights,
        "item_highlights",
        errors,
        allow_weighted_base=allow_weighted_base,
    )
    for index, bullet in enumerate(bullets):
        _scan_text_fields(
            bullet,
            f"bullet[{index}]",
            errors,
            allow_weighted_base=allow_weighted_base,
        )
        _scan_bullet_quality(bullet, index, errors)

    return PasteReadyResult(errors=errors, warnings=warnings)
