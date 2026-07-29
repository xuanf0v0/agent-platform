#!/usr/bin/env python3
"""Lint post-July-27-2026 Amazon listing fields from JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


TITLE_MAX = 75
HIGHLIGHT_MAX = 125
SEARCH_TERMS_MAX_BYTES = 250
RESTRICTED_TITLE_CHARS = set("!$?_{}^¬¦")
WORD_RE = re.compile(r"[A-Za-z0-9À-ÖØ-öø-ÿĀ-ž]+(?:['’][A-Za-z]+)?")
ASIN_RE = re.compile(r"\bB0[A-Z0-9]{8}\b", re.IGNORECASE)
PUNCT_RE = re.compile(r"[,\.;:|/\\()\[\]{}!?_+=*&%$#@~^]")
STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "de", "der", "des", "die", "das",
    "en", "et", "for", "from", "in", "la", "le", "les", "of", "on", "or",
    "para", "per", "the", "to", "und", "von", "with", "y",
}
PROMO_PATTERNS = {
    "free shipping": re.compile(r"\bfree\s+shipping\b", re.IGNORECASE),
    "quality guarantee": re.compile(r"\b100%\s+quality\s+guaranteed\b", re.IGNORECASE),
    "best seller": re.compile(r"\bbest\s*seller\b", re.IGNORECASE),
    "hot item": re.compile(r"\bhot\s+item\b", re.IGNORECASE),
    "limited time": re.compile(r"\blimited\s+time\b", re.IGNORECASE),
}
REFUND_PATTERNS = {
    "refund guarantee": re.compile(r"\b(?:refund|money[- ]back)\s+guarantee", re.IGNORECASE),
    "satisfaction guarantee": re.compile(r"\bsatisfaction\s+guarantee", re.IGNORECASE),
}


def normalized_words(text: str) -> list[str]:
    return [match.group(0).lower().replace("’", "'") for match in WORD_RE.finditer(text)]


def has_emoji(text: str) -> bool:
    for char in text:
        if unicodedata.category(char) in {"So", "Cs"} and char not in {"®", "™", "©"}:
            return True
    return False


def add_issue(issues: list[dict[str, Any]], field: str, code: str, message: str) -> None:
    issues.append({"field": field, "code": code, "message": message})


def lint(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title", "")).strip()
    highlight = str(data.get("item_highlights", "")).strip()
    bullets = data.get("bullets", [])
    search_terms = str(data.get("search_terms", "")).strip()
    brand = str(data.get("brand", "")).strip()
    media = bool(data.get("media_category", False))
    competitor_brands = [str(x).strip() for x in data.get("competitor_brands", []) if str(x).strip()]

    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(x).strip() for x in bullets if str(x).strip()]

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not title:
        add_issue(errors, "title", "missing", "Title is required.")
    if title and not media and len(title) > TITLE_MAX:
        add_issue(errors, "title", "length", f"Title is {len(title)} characters; maximum is {TITLE_MAX}.")
    restricted = sorted(set(title) & RESTRICTED_TITLE_CHARS)
    if restricted:
        add_issue(errors, "title", "restricted_characters", f"Restricted characters: {' '.join(restricted)}")

    counts = Counter(word for word in normalized_words(title) if word not in STOPWORDS)
    repeated = {word: count for word, count in counts.items() if count > 2}
    if repeated:
        add_issue(errors, "title", "word_repetition", f"Words repeated more than twice: {repeated}")

    for label, pattern in PROMO_PATTERNS.items():
        if pattern.search(title):
            add_issue(errors, "title", "promotional_phrase", f"Remove promotional phrase: {label}")

    if highlight and len(highlight) > HIGHLIGHT_MAX:
        add_issue(errors, "item_highlights", "length", f"Item Highlights are {len(highlight)} characters; maximum is {HIGHLIGHT_MAX}.")
    if highlight and PUNCT_RE.sub("", highlight).strip() and highlight.count(",") >= 4:
        add_issue(warnings, "item_highlights", "keyword_list_risk", "Item Highlights may be a comma-joined keyword list.")

    if len(bullets) > 5:
        add_issue(errors, "bullets", "count", f"{len(bullets)} bullets supplied; maximum available is 5.")
    if len(bullets) < 5:
        add_issue(warnings, "bullets", "count", f"Only {len(bullets)} bullets supplied; use all 5 when the category supports them and facts are available.")
    for index, bullet in enumerate(bullets, 1):
        field = f"bullets[{index}]"
        if bullet and bullet[0].isalpha() and not bullet[0].isupper():
            add_issue(warnings, field, "capitalization", "Begin the bullet with a capital letter.")
        if has_emoji(bullet):
            add_issue(errors, field, "emoji", "Remove emoji or decorative symbol.")
        for label, pattern in {**PROMO_PATTERNS, **REFUND_PATTERNS}.items():
            if pattern.search(bullet):
                add_issue(errors, field, "prohibited_phrase", f"Remove prohibited/risky phrase: {label}")

    search_bytes = len(search_terms.encode("utf-8"))
    if search_bytes > SEARCH_TERMS_MAX_BYTES:
        add_issue(errors, "search_terms", "byte_length", f"Search Terms use {search_bytes} UTF-8 bytes; maximum is {SEARCH_TERMS_MAX_BYTES}.")
    if search_terms and search_terms != search_terms.lower():
        add_issue(warnings, "search_terms", "case", "Use lowercase Search Terms.")
    if PUNCT_RE.search(search_terms):
        add_issue(warnings, "search_terms", "punctuation", "Remove unnecessary punctuation from Search Terms.")
    if ASIN_RE.search(search_terms):
        add_issue(errors, "search_terms", "asin", "Remove ASINs from Search Terms.")

    search_words = normalized_words(search_terms)
    duplicate_search_words = sorted(word for word, count in Counter(search_words).items() if count > 1)
    if duplicate_search_words:
        add_issue(warnings, "search_terms", "duplicate_tokens", f"Duplicate tokens: {duplicate_search_words}")

    visible_words = set(normalized_words(title))
    brand_words = set(normalized_words(brand))
    redundant = sorted((set(search_words) & (visible_words | brand_words)) - STOPWORDS)
    if redundant:
        add_issue(warnings, "search_terms", "visible_duplicates", f"Words already in Title/brand: {redundant}")

    prohibited_brands = []
    normalized_terms = f" {' '.join(search_words)} "
    for competitor in competitor_brands:
        normalized_competitor = " ".join(normalized_words(competitor))
        if normalized_competitor and f" {normalized_competitor} " in normalized_terms:
            prohibited_brands.append(competitor)
    if prohibited_brands:
        add_issue(errors, "search_terms", "competitor_brands", f"Remove competitor brands: {prohibited_brands}")

    all_visible = " ".join([title, highlight, *bullets])
    for label, pattern in PROMO_PATTERNS.items():
        if pattern.search(all_visible):
            add_issue(errors, "visible_copy", "promotional_phrase", f"Remove promotional phrase: {label}")

    return {
        "status": "BLOCK" if errors else ("WARN" if warnings else "PASS"),
        "stats": {
            "title_characters": len(title),
            "item_highlights_characters": len(highlight),
            "bullet_count": len(bullets),
            "search_terms_utf8_bytes": search_bytes,
        },
        "errors": errors,
        "warnings": warnings,
        "manual_checks": [
            "Verify marketplace/category/media status and live field validators.",
            "Verify every specification, compatibility, performance, and regulated claim against evidence.",
            "Verify parent/child scope, structured attributes, images, and copy are consistent.",
            "Verify review, Q&A, and variation actions do not manipulate customer reviews.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", nargs="?", help="Listing JSON file; omit to read stdin.")
    args = parser.parse_args()
    try:
        if args.json_file:
            data = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        else:
            data = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCK", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    result = lint(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
