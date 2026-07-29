"""Amazon hard-ban wordlist scanner and mode-aware title/BP validators (R10).

Promo and decorative hits always hard-fail. Subjective hits hard-fail under
``strict_amazon`` and become warnings under ``sop_seo``. Trailing-period and
length checks reuse plain-text helpers from ``amazon_copy.schemas.metrics``.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, assert_never

from amazon_copy.schemas.enums import TitleMode
from amazon_copy.schemas.listing import BulletPoint
from amazon_copy.schemas.metrics import (
    BpMode,
    plain_len,
    strip_md_bold,
    validate_bullet_length,
    validate_no_trailing_period,
    validate_title_length,
)

_WORDLIST_PATH: Final[Path] = Path(__file__).resolve().parent / "wordlist.txt"
_MIN_COLUMNS: Final[int] = 3
_TITLE_MIN_PLAIN: Final[int] = 10
_MIN_ALL_CAPS_WORDS: Final[int] = 4
_MIN_CASED_WORD_LENGTH: Final[int] = 2
_ALL_CAPS_RATIO: Final[float] = 0.8
_SMALL_TITLE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "nor",
        "of",
        "on",
        "or",
        "per",
        "the",
        "to",
        "via",
        "with",
    }
)
_TITLE_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")

# ASCII / special decorative set from R10; pipe cannot live in TSV (delimiter).
_DECORATIVE_CHARS: Final[frozenset[str]] = frozenset("~!*$?_{}#<>|;^¬¦")

ComplianceCategory = Literal["promo", "decorative", "subjective"]
_PHRASE_CATEGORIES: Final[frozenset[str]] = frozenset({"promo", "subjective"})


@dataclass(frozen=True, slots=True)
class ComplianceHit:
    """A single hard-ban / soft-ban match in scanned text."""

    phrase: str
    category: str
    severity: str
    span: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured validation outcome for title or bullet validators."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hits: list[ComplianceHit] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _WordlistEntry:
    phrase: str
    category: str
    severity: str
    casefold_phrase: str


def load_wordlist(path: Path | None = None) -> list[_WordlistEntry]:
    """Load ``phrase|category|severity`` TSV entries from the package wordlist."""
    resolved = path or _WORDLIST_PATH
    entries: list[_WordlistEntry] = []
    with resolved.open(encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="|")
        for row in reader:
            if not row or len(row) < _MIN_COLUMNS:
                continue
            phrase = row[0].strip()
            if not phrase or phrase.startswith("#"):
                continue
            category = row[1].strip()
            severity = row[2].strip()
            entries.append(
                _WordlistEntry(
                    phrase=phrase,
                    category=category,
                    severity=severity,
                    casefold_phrase=phrase.casefold(),
                ),
            )
    return entries


@lru_cache(maxsize=1)
def _cached_wordlist() -> tuple[_WordlistEntry, ...]:
    return tuple(load_wordlist())


def scan_title_hard_bans(title: str) -> list[ComplianceHit]:
    """Scan *title* for promo, decorative, and subjective hard-ban phrases.

    Multi-word promo/subjective phrases match case-insensitively. Decorative
    entries match by character presence. Longer phrases win over shorter ones
    when spans would overlap.
    """
    plain = strip_md_bold(title)
    if not plain:
        return []

    entries = sorted(
        _cached_wordlist(),
        key=lambda e: (-len(e.phrase), e.phrase),
    )
    plain_cf = plain.casefold()
    occupied: set[int] = set()
    hits: list[ComplianceHit] = []

    for entry in entries:
        if entry.category in _PHRASE_CATEGORIES:
            _scan_phrase(plain_cf, entry, occupied, hits)
        else:
            _scan_literal(plain, entry, occupied, hits)

    for index, ch in enumerate(plain):
        if ch not in _DECORATIVE_CHARS or index in occupied:
            continue
        hits.append(
            ComplianceHit(
                phrase=ch,
                category="decorative",
                severity="high",
                span=(index, index + 1),
            ),
        )
        occupied.add(index)

    hits.sort(key=lambda h: h.span[0] if h.span is not None else 0)
    return hits


def _scan_phrase(
    plain_cf: str,
    entry: _WordlistEntry,
    occupied: set[int],
    hits: list[ComplianceHit],
) -> None:
    needle = entry.casefold_phrase
    start = 0
    while True:
        pos = plain_cf.find(needle, start)
        if pos == -1:
            break
        end = pos + len(needle)
        span_idx = set(range(pos, end))
        if not span_idx & occupied:
            hits.append(
                ComplianceHit(
                    phrase=entry.phrase,
                    category=entry.category,
                    severity=entry.severity,
                    span=(pos, end),
                ),
            )
            occupied |= span_idx
        start = pos + 1


def _scan_literal(
    plain: str,
    entry: _WordlistEntry,
    occupied: set[int],
    hits: list[ComplianceHit],
) -> None:
    phrase = entry.phrase
    start = 0
    while True:
        pos = plain.find(phrase, start)
        if pos == -1:
            break
        end = pos + len(phrase)
        span_idx = set(range(pos, end))
        if not span_idx & occupied:
            hits.append(
                ComplianceHit(
                    phrase=entry.phrase,
                    category=entry.category,
                    severity=entry.severity,
                    span=(pos, end),
                ),
            )
            occupied |= span_idx
        start = pos + 1


def _hit_message(hit: ComplianceHit) -> str:
    return f"{hit.category}: banned phrase/char {hit.phrase!r}"


def _route_hit(
    hit: ComplianceHit,
    mode: TitleMode,
    errors: list[str],
    warnings: list[str],
    *,
    prefix: str = "",
) -> None:
    msg = f"{prefix}{_hit_message(hit)}" if prefix else _hit_message(hit)
    match hit.category:
        case "promo" | "decorative":
            errors.append(msg)
        case "subjective":
            match mode:
                case TitleMode.STRICT_AMAZON:
                    errors.append(msg)
                case TitleMode.SOP_SEO:
                    warnings.append(msg)
                case unreachable:
                    assert_never(unreachable)
        case _:
            errors.append(msg)


def _strict_style_errors(title: str, seller_name: str | None) -> list[str]:
    """Return deterministic strict-mode style failures without guessing identity."""
    plain = strip_md_bold(title)
    words = _TITLE_WORD_RE.findall(plain)
    cased_words = [word for word in words if len(word.replace("-", "")) >= _MIN_CASED_WORD_LENGTH]
    uppercase_words = [word for word in cased_words if word.isupper()]
    errors: list[str] = []

    if (
        len(cased_words) >= _MIN_ALL_CAPS_WORDS
        and len(uppercase_words) / len(cased_words) >= _ALL_CAPS_RATIO
    ):
        errors.append("strict_amazon title must not be ALL CAPS")

    for index, word in enumerate(words):
        parts = word.split("-")
        for part_index, part in enumerate(parts):
            if not part or part.isupper() or not part.isalpha():
                continue
            is_small = part.casefold() in _SMALL_TITLE_WORDS
            is_first = index == 0 and part_index == 0
            if (is_small and not is_first and part.islower()) or part[0].isupper():
                continue
            errors.append(f"strict_amazon Title Case heuristic failed at {word!r}")
            break
        if errors and "Title Case" in errors[-1]:
            break

    known_seller = (seller_name or "").strip()
    if known_seller:
        seller_pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(known_seller.casefold())}(?![A-Za-z0-9])"
        )
        if seller_pattern.search(plain.casefold()):
            errors.append(f"strict_amazon title must not contain seller name {known_seller!r}")
    return errors


def validate_title(
    title: str,
    mode: TitleMode | str,
    *,
    seller_name: str | None = None,
) -> ValidationResult:
    """Validate title hard bans + min length + mode length bounds (R4/R10).

    Promo/decorative -> errors always. Subjective -> error under
    ``strict_amazon``, warning under ``sop_seo``.
    """
    resolved = mode if isinstance(mode, TitleMode) else TitleMode(mode)
    hits = scan_title_hard_bans(title)
    errors: list[str] = []
    warnings: list[str] = []

    for hit in hits:
        _route_hit(hit, resolved, errors, warnings)

    n = plain_len(title)
    if n < _TITLE_MIN_PLAIN:
        errors.append(
            f"title plain_len {n} below min product-identifying length {_TITLE_MIN_PLAIN}",
        )

    try:
        validate_title_length(title, resolved)
    except ValueError as exc:
        errors.append(str(exc))

    if resolved is TitleMode.STRICT_AMAZON:
        errors.extend(_strict_style_errors(title, seller_name))

    return ValidationResult(errors=errors, warnings=warnings, hits=hits)


def validate_bullets(
    bullets: list[str | BulletPoint],
    mode: BpMode,
) -> ValidationResult:
    """Validate each bullet for trailing period + mode length (R7/R8).

    Promo/decorative wordlist hits on bullet text are hard errors; subjective
    hits are warnings (BP has no TitleMode).
    """
    errors: list[str] = []
    warnings: list[str] = []
    all_hits: list[ComplianceHit] = []

    for index, item in enumerate(bullets):
        text = _bullet_text(item)
        prefix = f"bullet[{index}]: "

        try:
            validate_no_trailing_period(text)
        except ValueError as exc:
            errors.append(f"{prefix}{exc}")

        try:
            validate_bullet_length(text, mode)
        except ValueError as exc:
            errors.append(f"{prefix}{exc}")

        hits = scan_title_hard_bans(text)
        all_hits.extend(hits)
        for hit in hits:
            match hit.category:
                case "promo" | "decorative":
                    errors.append(f"{prefix}{_hit_message(hit)}")
                case "subjective":
                    warnings.append(f"{prefix}{_hit_message(hit)}")
                case _:
                    errors.append(f"{prefix}{_hit_message(hit)}")

    return ValidationResult(errors=errors, warnings=warnings, hits=all_hits)


def _bullet_text(item: str | BulletPoint) -> str:
    match item:
        case str() as text:
            return text
        case BulletPoint() as bp:
            return bp.text
        case unreachable:
            assert_never(unreachable)
