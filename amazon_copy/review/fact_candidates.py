"""Closed extraction patterns for concrete listing fact candidates."""

import re
from dataclasses import dataclass
from typing import Final

from amazon_copy.review.models import FactCategory, ListingReviewRequest

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z]+|\d+(?:\.\d+)?", re.IGNORECASE)
_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_STOP_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "display",
        "displays",
        "for",
        "is",
        "of",
        "or",
        "product",
        "the",
        "to",
        "up",
        "with",
    }
)


def _combine_pattern(*parts: str) -> str:
    return "".join(parts)


_CANDIDATE_PATTERNS: Final[tuple[tuple[FactCategory, re.Pattern[str]], ...]] = (
    (
        FactCategory.BOM,
        re.compile(
            _combine_pattern(
                r"\b(?:includes?|comes? with)\b[^.;\n]{1,60}|",
                r"\bwith\s+(?:mounting\s+)?(?:screws?|straps?|water bags?|",
                r"anchors?|hardware|tools?)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.COUNT,
        re.compile(
            _combine_pattern(
                r"\b(?:pack(?:age)?|set) of \d+\b|",
                r"\b\d+(?:\s*[-\u2010-\u2015\u2212]\s*|\s+)?",
                r"(?:pack|count|pieces?|pcs|tiers?|compartments?)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.DIMENSION,
        re.compile(
            _combine_pattern(
                r"\b\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?){0,2}\s*",
                r"(?:in(?:ch(?:es)?)?|cm|mm|ft|feet|lb|lbs|pounds?|oz|gsm|g/m²|mil)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.MATERIAL,
        re.compile(
            _combine_pattern(
                r"\b(?:acrylic|aluminum|cardboard|cellophane|cotton|epe foam|fabric|felt|",
                r"kraft paper|leather|lycra|mdf|metal|mesh|nylon|opp|paper|pet|polyester|",
                r"polypropylene|pvc|rubber|steel|stone|velvet|wood)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.COMPATIBILITY,
        re.compile(
            r"\b(?:compatible with|fits?|works? with|suitable for)\b[^.;\n]{1,55}",
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.SAFETY,
        re.compile(
            _combine_pattern(
                r"\b(?:adult supervision|required supervision|child safe|food safe|",
                r"gentle on hands|non[ -]?toxic|safe for|safety device)\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.PERFORMANCE,
        re.compile(
            _combine_pattern(
                r"\b(?:airtight|anti[ -]?rust|biodegradable|durable|fade[ -]?resistant|",
                r"greaseproof|heavy[ -]?duty|leakproof|recyclable|rust[ -]?proof|",
                r"rust[ -]?resistant|tear[ -]?proof|waterproof|weatherproof|",
                r"wind[ -]?resistant|windproof|supervised outdoor (?:displays?|setups?|use))\b",
            ),
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.CERTIFICATION,
        re.compile(
            r"\b(?:approved|certified|CPC|CPSC|FDA|food grade|USCG|Coast Guard)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.VARIATION,
        re.compile(
            r"\b(?:parent|child|sibling) (?:ASIN|listing|variation)|\bvariant-specific\b",
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.EXCLUSION,
        re.compile(r"\b[a-z][a-z -]{0,35} (?:is |are )?not included\b", re.IGNORECASE),
    ),
)


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """One located product-fact phrase and its stable baseline signature."""

    category: FactCategory
    field: str
    text: str
    signature: str


def normalized_fact_text(value: str) -> str:
    """Normalize one fact key or candidate without inferring authority."""
    normalized = value.casefold().replace("_", " ").replace("×", "x")
    normalized = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " x ", normalized)
    normalized = re.sub(r"(?<=\d)(?=(?:inches?|feet|ft|lbs?|pounds?)\b)", " ", normalized)
    normalized = re.sub(r"\binches?\b", "inch", normalized)
    normalized = re.sub(r"\bfeet\b", "ft", normalized)
    normalized = re.sub(r"\b(?:lbs?|pounds?)\b", "lb", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def fact_tokens(value: str) -> frozenset[str]:
    """Return meaningful normalized tokens for exact structured matching."""
    return frozenset(
        match.group(0)
        for match in _TOKEN_RE.finditer(normalized_fact_text(value))
        if match.group(0) not in _STOP_TOKENS
    )


def fact_candidates(request: ListingReviewRequest) -> tuple[FactCandidate, ...]:
    """Extract closed-category candidates from machine-reviewed listing fields."""
    fields = (
        ("title", request.title),
        ("item_highlights", request.item_highlights),
        *(("bullets", bullet) for bullet in request.bullets),
    )
    candidates: list[FactCandidate] = []
    seen: set[str] = set()
    for field, text in fields:
        for category, pattern in _CANDIDATE_PATTERNS:
            for match in pattern.finditer(text):
                candidate_text = match.group(0).strip()
                signature = f"{category.value}:{normalized_fact_text(candidate_text)}"
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append(FactCandidate(category, field, candidate_text, signature))
    return tuple(candidates)


def fact_signatures(request: ListingReviewRequest) -> tuple[str, ...]:
    """Return stable signatures for concrete facts already present at source."""
    return tuple(candidate.signature for candidate in fact_candidates(request))


__all__ = [
    "FactCandidate",
    "fact_candidates",
    "fact_signatures",
    "fact_tokens",
    "normalized_fact_text",
]
