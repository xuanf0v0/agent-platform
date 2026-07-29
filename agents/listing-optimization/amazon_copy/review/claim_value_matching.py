"""Normalization and matching helpers for structured product facts."""

import re
from collections import Counter
from decimal import Decimal
from typing import Final, TypeAlias

from amazon_copy.review.fact_candidates import fact_tokens, normalized_fact_text
from amazon_copy.review.models import EvidenceSource, FactCategory, ResolvedFact

_KEY_MARKERS: Final = {
    FactCategory.BOM: frozenset(
        {
            "accessory",
            "bom",
            "component",
            "content",
            "hardware",
            "included",
            "package",
            "screw",
            "strap",
        }
    ),
    FactCategory.COUNT: frozenset({"count", "number", "pack", "piece", "quantity"}),
    FactCategory.DIMENSION: frozenset(
        {
            "age",
            "capacity",
            "depth",
            "dimension",
            "height",
            "length",
            "range",
            "size",
            "thickness",
            "weight",
            "width",
        }
    ),
    FactCategory.MATERIAL: frozenset({"coating", "finish", "material"}),
    FactCategory.COMPATIBILITY: frozenset({"age", "compatibility", "compatible", "fit", "surface"}),
    FactCategory.SAFETY: frozenset({"safety", "supervision", "warning"}),
    FactCategory.PERFORMANCE: frozenset(
        {"capacity", "durability", "outdoor", "performance", "resistance", "stability"}
    ),
    FactCategory.CERTIFICATION: frozenset(
        {"approval", "certification", "certified", "compliance", "cpc", "cpsc", "uscg"}
    ),
    FactCategory.VARIATION: frozenset({"child", "parent", "variation", "variant"}),
    FactCategory.EXCLUSION: frozenset({"excluded", "exclusion", "included"}),
}
_SINGULAR_FACT_KEYS: Final = {
    "ages": "age",
    "capacities": "capacity",
    "counts": "count",
    "depths": "depth",
    "dimensions": "dimension",
    "heights": "height",
    "lengths": "length",
    "numbers": "number",
    "packs": "pack",
    "pieces": "piece",
    "quantities": "quantity",
    "ranges": "range",
    "sizes": "size",
    "thicknesses": "thickness",
    "weights": "weight",
    "widths": "width",
}
_DIMENSION_UNIT_ALIASES: Final = {
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "cm": "cm",
    "mm": "mm",
    "ft": "ft",
    "feet": "ft",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "oz": "oz",
    "gsm": "gsm",
    "mil": "mil",
}
_DimensionExpression: TypeAlias = tuple[tuple[Decimal, ...], str]


def _combine_pattern(*parts: str) -> str:
    return "".join(parts)


_DIMENSION_EXPRESSION_RE: Final[re.Pattern[str]] = re.compile(
    _combine_pattern(
        r"(?P<numbers>\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?){0,2})\s*",
        r"(?P<unit>in(?:ch(?:es)?)?|cm|mm|ft|feet|lb|lbs|pounds?|oz|gsm|mil)",
        r"(?![a-z])",
    ),
    re.IGNORECASE,
)


def singular_fact_key(value: str) -> str:
    """Normalize plural fact-key tokens to their singular matching forms."""
    return " ".join(
        _SINGULAR_FACT_KEYS.get(token, token) for token in normalized_fact_text(value).split()
    )


def dimension_values(value: str) -> tuple[_DimensionExpression, ...]:
    """Extract ordered numeric dimensions and canonicalize their units."""
    dimensions: list[_DimensionExpression] = []
    for match in _DIMENSION_EXPRESSION_RE.finditer(value):
        unit = _DIMENSION_UNIT_ALIASES[match.group("unit").casefold()]
        numbers = re.split(r"\s*[x×]\s*", match.group("numbers"))
        dimensions.append((tuple(Decimal(number) for number in numbers), unit))
    return tuple(dimensions)


def fact_category_matches(fact: ResolvedFact, category: FactCategory) -> bool:
    """Return whether a first-party fact key belongs to a candidate category."""
    if fact.source > EvidenceSource.AMAZON_FIRST_PARTY_DATA:
        return False
    key = frozenset(singular_fact_key(token) for token in fact_tokens(fact.key))
    if singular_fact_key(fact.key).startswith(("keyword", "market.")):
        return False
    return bool(key & _KEY_MARKERS[category])


def value_matches(candidate: str, fact: ResolvedFact) -> bool:
    """Return whether a candidate value is authorized by a structured fact."""
    candidate_dimensions = dimension_values(candidate)
    fact_dimensions = dimension_values(fact.value)
    if candidate_dimensions or fact_dimensions:
        if not candidate_dimensions or not fact_dimensions:
            return False
        candidate_composites = Counter(
            dimension for dimension in candidate_dimensions if len(dimension[0]) > 1
        )
        fact_composites = Counter(
            dimension for dimension in fact_dimensions if len(dimension[0]) > 1
        )
        if candidate_composites - fact_composites:
            return False
        candidate_scalars = Counter(
            (number, unit)
            for numbers, unit in candidate_dimensions
            if len(numbers) == 1
            for number in numbers
        )
        fact_components = Counter(
            (number, unit) for numbers, unit in fact_dimensions for number in numbers
        )
        return not (candidate_scalars - fact_components)
    candidate_tokens = fact_tokens(candidate)
    combined_tokens = fact_tokens(f"{fact.key} {fact.value}")
    numbers = {token for token in candidate_tokens if token[0].isdigit()}
    if numbers:
        return numbers <= combined_tokens
    return bool(candidate_tokens) and candidate_tokens <= combined_tokens
