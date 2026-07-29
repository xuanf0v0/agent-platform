"""Narrow parser for untrusted marketplace keyword metadata."""

from __future__ import annotations

import unicodedata
from itertools import pairwise
from typing import Final

_MAX_KEYWORD_CHARS: Final = 72
_MAX_KEYWORD_BYTES: Final = 144
_MAX_KEYWORD_TOKENS: Final = 8
_MAX_TOKEN_CHARS: Final = 24
_ALLOWED_PUNCTUATION: Final = frozenset(" &+'-")
_TOKEN_TRANSLATION: Final = str.maketrans("&+'-", "    ")
_URL_MARKERS: Final = ("://", "www.", "mailto:", "data:")
_LEET_TRANSLATION: Final = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}
)
_FORBIDDEN_TOKENS: Final = frozenset(
    {
        "apikey",
        "authorization",
        "bearer",
        "bypass",
        "cookie",
        "credential",
        "credentials",
        "direction",
        "directions",
        "disclose",
        "disregard",
        "execute",
        "exfiltrate",
        "forget",
        "ignore",
        "instruction",
        "instructions",
        "jailbreak",
        "obey",
        "override",
        "passcode",
        "password",
        "passwords",
        "prompt",
        "prompts",
        "reveal",
        "rule",
        "rules",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)
_FORBIDDEN_TOKEN_PAIRS: Final = frozenset(
    {
        ("api", "key"),
        ("developer", "message"),
        ("internal", "context"),
        ("output", "internal"),
        ("system", "prompt"),
    }
)


def _allowed_character(char: str) -> bool:
    return char in _ALLOWED_PUNCTUATION or unicodedata.category(char)[0] in {"L", "M", "N"}


def parse_marketplace_keyword(raw: str | None) -> str | None:
    """Return one bounded product-search term, rejecting instruction-shaped text."""
    if raw is None:
        return None
    normalized = " ".join(
        unicodedata.normalize("NFKC", raw)
        .replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        .split()
    )
    if (
        not normalized
        or len(normalized) > _MAX_KEYWORD_CHARS
        or len(normalized.encode("utf-8")) > _MAX_KEYWORD_BYTES
        or any(marker in normalized.casefold() for marker in _URL_MARKERS)
        or any(not _allowed_character(char) for char in normalized)
    ):
        return None
    tokens = normalized.casefold().translate(_TOKEN_TRANSLATION).split()
    if (
        not tokens
        or len(tokens) > _MAX_KEYWORD_TOKENS
        or any(len(token) > _MAX_TOKEN_CHARS for token in tokens)
        or any(token.translate(_LEET_TRANSLATION) in _FORBIDDEN_TOKENS for token in tokens)
        or any(pair in _FORBIDDEN_TOKEN_PAIRS for pair in pairwise(tokens))
    ):
        return None
    return normalized


__all__ = ["parse_marketplace_keyword"]
