"""Deterministic backend search-term normalization and validation."""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Final

_TOKEN_RE: Final = re.compile(r"[\w+\-]+", re.UNICODE)
_INJECTION_RE: Final = re.compile(
    r"(?:ignore (?:all |previous )?instructions|system prompt|developer message|jailbreak)",
    re.IGNORECASE,
)
BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES: Final = 250

# Tokens that add no independent search value when used as standalone search terms.
_FILLER_SEARCH_TOKENS: Final = frozenset(
    {"for", "with", "and", "the", "a", "an", "of", "in", "on", "to", "at", "by", "or", "is", "it"}
)

# Performance claims that must not appear in backend search terms without
# verified evidence.  Mirrors PERFORMANCE_TERMS from rules.py.
_UNVERIFIED_SEARCH_TERM_PHRASES: Final = (
    "heavy duty",
    "heavy-duty",
    "waterproof",
    "weatherproof",
    "windproof",
    "wind-resistant",
    "wind resistant",
    "rust-proof",
    "rust proof",
    "anti-rust",
    "antirust",
    "guaranteed",
)


def build_backend_search_terms(
    terms: Sequence[str],
    *,
    max_bytes: int = 250,
) -> str:
    """Return stable ordered unique roots without exceeding a UTF-8 byte budget."""
    effective_max_bytes = min(max_bytes, BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES)
    if effective_max_bytes < 1:
        return ""
    tokens: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = unicodedata.normalize("NFKC", term)
        if _INJECTION_RE.search(normalized):
            continue
        for match in _TOKEN_RE.finditer(normalized):
            token = match.group(0)
            folded = token.casefold()
            if folded not in seen:
                seen.add(folded)
                tokens.append(token)
    accepted: list[str] = []
    for token in tokens:
        candidate = " ".join((*accepted, token))
        if len(candidate.encode("utf-8")) <= effective_max_bytes:
            accepted.append(token)
    return " ".join(accepted)


def _visible_field_tokens(
    title: str,
    item_highlights: str,
    bullets: Iterable[str],
) -> frozenset[str]:
    """Extract normalized tokens from every visible listing field."""
    visible_text = " ".join((title, item_highlights, *bullets)).casefold()
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(visible_text):
        token = match.group(0).casefold()
        if token not in _FILLER_SEARCH_TOKENS:
            tokens.add(token)
    return frozenset(tokens)


def search_term_duplication_pct(
    backend_search_terms: str,
    title: str,
    item_highlights: str,
    bullets: Iterable[str],
) -> float:
    """Return the percentage of search-term tokens already present in visible fields.

    Returns 0.0 when there are no search terms to evaluate.
    """
    if not backend_search_terms.strip():
        return 0.0
    visible = _visible_field_tokens(title, item_highlights, bullets)
    search_tokens = [
        token.casefold()
        for token in backend_search_terms.split()
        if token.casefold() not in _FILLER_SEARCH_TOKENS
    ]
    if not search_tokens:
        return 0.0
    duplicated = sum(1 for token in search_tokens if token in visible)
    return (duplicated / len(search_tokens)) * 100.0


def unverified_search_term_claims(
    backend_search_terms: str,
) -> tuple[str, ...]:
    """Return performance-claim phrases found in backend search terms."""
    folded = backend_search_terms.casefold()
    return tuple(
        phrase for phrase in _UNVERIFIED_SEARCH_TERM_PHRASES if phrase in folded
    )


def incremental_search_term_tokens(
    backend_search_terms: str,
    title: str,
    item_highlights: str,
    bullets: Iterable[str],
) -> tuple[str, ...]:
    """Return the subset of search-term tokens not already in visible fields."""
    if not backend_search_terms.strip():
        return ()
    visible = _visible_field_tokens(title, item_highlights, bullets)
    return tuple(
        token
        for token in backend_search_terms.split()
        if token.casefold() not in visible and token.casefold() not in _FILLER_SEARCH_TOKENS
    )


__all__ = [
    "BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES",
    "build_backend_search_terms",
    "incremental_search_term_tokens",
    "search_term_duplication_pct",
    "unverified_search_term_claims",
]
