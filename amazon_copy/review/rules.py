"""Deterministic listing review rules."""

import re
from collections import Counter
from collections.abc import Iterable
from typing import Final

from amazon_copy.review.models import ReviewFinding

_WORD_RE: Final = re.compile(r"[A-Za-z][A-Za-z'-]*")
_WRITTEN_NUMBER_RE: Final = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
    re.IGNORECASE,
)
_INCOMPLETE_TITLE_RE: Final = re.compile(
    r"(?:\b(?:with|and|for|including|plus)\s*(?:\d+)?|[,;:\-/])\s*$",
    re.IGNORECASE,
)
_PRICE_RE: Final = re.compile(r"(?:[$£€]\s*\d|\b\d+%\s*off\b)", re.IGNORECASE)
_CONTACT_RE: Final = re.compile(
    r"(?:https?://|www\.|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|\b(?:call|text)\s+\d)",
    re.IGNORECASE,
)
_CONTENT_EXEMPT: Final = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
)
_MAX_TITLE_CONTENT_REPETITIONS: Final = 2
_DUPLICATE_SIMILARITY: Final = 0.72
_PROMO_TERMS: Final = (
    "best seller",
    "hot item",
    "perfect gift",
    "free shipping",
    "free delivery",
    "limited time",
    "act now",
    "top rated",
    "viral trend",
)
_REFUND_REVIEW_TERMS: Final = (
    "money back",
    "refund",
    "risk free",
    "positive review",
    "five star review",
    "guaranteed satisfaction",
)
_PERFORMANCE_TERMS: Final = (
    "waterproof",
    "wind-resistant",
    "wind resistant",
    "windproof",
    "rust-proof",
    "rust proof",
    "anti-rust",
    "heavy duty",
    "weatherproof",
    "stable in any wind",
    "securely holds",
    "supportive buoyancy",
    "stay in position",
    "natural arm movement",
    "float effortlessly",
    "maximum flotation",
    "guaranteed",
    "ensures",
)
_SAFETY_TERMS: Final = ("safe", "non-toxic", "nontoxic", "gentle on hands", "child safe")
_COMPATIBILITY_TERMS: Final = (
    "fits any",
    "work with all",
    "works with all",
    "compatible with all",
)
_TASK_TERMS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("core_advantage", ("advantage", "benefit", "surface", "smooth", "stability", "easy")),
    ("specification", ("size", "material", "inch", "includes", "count", "piece", "set")),
    ("method_compatibility", ("use", "suitable", "compatible", "paint", "assemble", "apply")),
    ("scene_outcome", ("display", "garden", "desk", "event", "home", "project", "decoration")),
    ("expectation", ("variation", "vary", "natural", "limit", "package", "contents", "included")),
)


def finding(
    code: str,
    severity: str,
    field: str,
    message_zh: str,
    evidence_required: str = "",
) -> ReviewFinding:
    """Build a typed finding from a deterministic rule."""
    return ReviewFinding.model_validate(
        {
            "code": code,
            "severity": severity,
            "field": field,
            "message_zh": message_zh,
            "evidence_required": evidence_required,
        }
    )


def contains_any(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    """Return whole-token/phrase hits without matching inside larger words."""
    hits: list[str] = []
    for term in terms:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(term)
    return tuple(hits)


def title_repeated_content_words(title: str) -> tuple[str, ...]:
    """Return title content words occurring more than twice."""
    words = [match.group(0).casefold() for match in _WORD_RE.finditer(title)]
    counts = Counter(word for word in words if word not in _CONTENT_EXEMPT)
    return tuple(
        sorted(word for word, count in counts.items() if count > _MAX_TITLE_CONTENT_REPETITIONS)
    )


def written_numbers(title: str) -> tuple[str, ...]:
    """Return spelled-out numbers that should normally be Arabic digits."""
    return tuple(match.group(0) for match in _WRITTEN_NUMBER_RE.finditer(title))


def title_is_incomplete(title: str) -> bool:
    """Detect a dangling title tail such as 'with 8'."""
    return _INCOMPLETE_TITLE_RE.search(title.strip()) is not None


def has_price(text: str) -> bool:
    """Detect price or discount syntax."""
    return _PRICE_RE.search(text) is not None


def price_claims(text: str) -> tuple[str, ...]:
    """Return exact price fragments that can be removed safely."""
    return tuple(match.group(0) for match in _PRICE_RE.finditer(text))


def has_external_contact(text: str) -> bool:
    """Detect external URLs, email addresses, or phone invitations."""
    return _CONTACT_RE.search(text) is not None


def external_contact_claims(text: str) -> tuple[str, ...]:
    """Return exact contact fragments that can be removed safely."""
    return tuple(match.group(0) for match in _CONTACT_RE.finditer(text))


def duplicate_bullet_pairs(bullets: tuple[str, ...]) -> tuple[tuple[int, int], ...]:
    """Detect bullet pairs with high lexical overlap."""
    pairs: list[tuple[int, int]] = []
    word_sets = [
        {match.group(0).casefold() for match in _WORD_RE.finditer(bullet)} for bullet in bullets
    ]
    for left in range(len(word_sets)):
        for right in range(left + 1, len(word_sets)):
            union = word_sets[left] | word_sets[right]
            similarity = len(word_sets[left] & word_sets[right]) / len(union) if union else 0.0
            if similarity >= _DUPLICATE_SIMILARITY:
                pairs.append((left + 1, right + 1))
    return tuple(pairs)


def covered_bullet_tasks(bullets: tuple[str, ...]) -> tuple[str, ...]:
    """Classify the five shopper decision tasks covered by bullets."""
    joined = " ".join(bullets).casefold()
    return tuple(name for name, terms in _TASK_TERMS if any(term in joined for term in terms))


PROMO_TERMS = _PROMO_TERMS
REFUND_REVIEW_TERMS = _REFUND_REVIEW_TERMS
PERFORMANCE_TERMS = _PERFORMANCE_TERMS
SAFETY_TERMS = _SAFETY_TERMS
COMPATIBILITY_TERMS = _COMPATIBILITY_TERMS
BULLET_TASK_COUNT: Final = len(_TASK_TERMS)
