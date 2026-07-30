"""Strict parsing for identity fields that must never be inferred from reports."""

from __future__ import annotations

import re
from typing import Final

MARKET_ALIASES: Final[dict[str, str]] = {
    "美国": "US",
    "美国站": "US",
    "英国": "UK",
    "英国站": "UK",
    "德国": "DE",
    "德国站": "DE",
    "法国": "FR",
    "法国站": "FR",
    "意大利": "IT",
    "意大利站": "IT",
    "西班牙": "ES",
    "西班牙站": "ES",
    "日本": "JP",
    "日本站": "JP",
    "加拿大": "CA",
    "加拿大站": "CA",
    "墨西哥": "MX",
    "墨西哥站": "MX",
    "澳大利亚": "AU",
    "澳大利亚站": "AU",
    "阿联酋": "AE",
    "阿联酋站": "AE",
    "印度": "IN",
    "印度站": "IN",
    "巴西": "BR",
    "巴西站": "BR",
}
MARKET_CODES: Final[frozenset[str]] = frozenset(
    {"US", "UK", "DE", "FR", "IT", "ES", "JP", "CA", "MX", "AU", "AE", "IN", "BR"}
)
_MARKET_VALUE = "|".join(
    [*(re.escape(value) for value in sorted(MARKET_ALIASES, key=len, reverse=True)), *MARKET_CODES]
)
_LABELED_MARKET_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?im)^\s*(?:目标站点|站点|target\s+marketplace|marketplace)\s*(?:[:：=|]|\s+-\s+)\s*({_MARKET_VALUE})(?=\s*(?:$|[|,，;；]))",
    re.IGNORECASE,
)
_MARKET_PHRASE_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?i)(?:\bAmazon\s+({_MARKET_VALUE})\b|\b({_MARKET_VALUE})\s+(?:Amazon\s+)?marketplace\b)"
)
_LABELED_ASIN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:产品\s*ASIN|product\s*ASIN|ASIN)\s*(?:[:：=|]|\s+-\s+|\s+)\s*([A-Z0-9]{10})(?![A-Z0-9])",
    re.IGNORECASE,
)
_ASIN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{10}$")
_ASIN_IN_TEXT_RE: Final[re.Pattern[str]] = re.compile(r"\b(B0[A-Z0-9]{8})\b", re.IGNORECASE)


def normalize_marketplace(value: str) -> str:
    """Normalize one explicit marketplace token or return an empty string."""
    clean = value.strip()
    alias = MARKET_ALIASES.get(clean)
    if alias:
        return alias
    code = clean.upper()
    return code if code in MARKET_CODES else ""


def extract_explicit_marketplace(text: str) -> str:
    """Extract only a labeled marketplace or an explicit marketplace phrase."""
    labeled = _LABELED_MARKET_RE.search(text)
    if labeled:
        return normalize_marketplace(labeled.group(1))
    phrase = _MARKET_PHRASE_RE.search(text)
    if phrase:
        return normalize_marketplace(phrase.group(1) or phrase.group(2) or "")
    return ""


def normalize_asin(value: str) -> str:
    """Normalize an exact ten-character ASIN or return an empty string."""
    clean = value.strip().upper()
    return clean if _ASIN_RE.fullmatch(clean) else ""


def extract_labeled_product_asin(text: str) -> str:
    """Extract only an explicitly labeled product ASIN."""
    match = _LABELED_ASIN_RE.search(text)
    return normalize_asin(match.group(1)) if match else ""


def extract_short_marketplace_answer(text: str) -> str:
    """Recognize one marketplace from a conversational short answer only."""
    clean = " ".join(text.strip().split())
    direct = normalize_marketplace(clean)
    if direct:
        return direct
    matches = {
        normalized
        for alias, normalized in MARKET_ALIASES.items()
        if alias in clean
    }
    matches.update(
        match.upper()
        for match in re.findall(
            r"\b(?:US|UK|DE|FR|IT|ES|JP|CA|MX|AU|AE|IN|BR)\b",
            clean,
            re.IGNORECASE,
        )
    )
    return matches.pop() if len(matches) == 1 else ""


def extract_short_asin_answer(text: str) -> str:
    """Return a single ASIN from a short conversational answer."""
    matches = {normalize_asin(match) for match in _ASIN_IN_TEXT_RE.findall(text)}
    matches.discard("")
    return matches.pop() if len(matches) == 1 else ""


__all__ = [
    "MARKET_ALIASES",
    "MARKET_CODES",
    "extract_explicit_marketplace",
    "extract_labeled_product_asin",
    "extract_short_asin_answer",
    "extract_short_marketplace_answer",
    "normalize_asin",
    "normalize_marketplace",
]
