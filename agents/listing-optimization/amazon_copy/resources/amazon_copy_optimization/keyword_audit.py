"""Typed keyword-embedding audit behavior extracted from the downloaded CLI."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final, final

from pydantic import BaseModel, ConfigDict
from typing_extensions import TypedDict, override

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class CoveragePayload(TypedDict):
    """JSON shape for one coverage summary."""

    covered: int
    total: int
    percent: float
    note: str


class KeywordPayload(TypedDict):
    """JSON shape for one target phrase."""

    keyword: str
    exact_covered: bool
    exact_occurrences: int
    exact_by_field: dict[str, int]
    root_covered: bool
    missing_roots: list[str]


class BackendSearchTermsPayload(TypedDict):
    """JSON shape for backend-term incrementality."""

    token_count: int
    unique_token_count: int
    utf8_bytes: int
    incremental_tokens: list[str]
    incremental_percent: float
    visible_redundant_tokens: list[str]
    visible_redundant_percent: float


class KeywordEmbeddingAuditPayload(TypedDict):
    """Complete JSON-compatible audit result."""

    target_keyword_count: int
    exact_phrase_coverage: CoveragePayload
    root_set_coverage: CoveragePayload
    keywords: list[KeywordPayload]
    root_token_counts: dict[str, int]
    backend_search_terms: BackendSearchTermsPayload


class KeywordAuditListing(BaseModel):
    """Parsed listing fields accepted by the CLI boundary."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    title: str = ""
    item_highlights: str = ""
    bullets: tuple[str, ...] = ()
    description: str = ""
    search_terms: str = ""


@dataclass(frozen=True, slots=True)
class NamedCount:
    """One deterministic name/count pair."""

    name: str
    count: int


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Covered targets relative to the requested total."""

    covered: int
    total: int
    percent: float
    note: str

    def to_payload(self) -> CoveragePayload:
        """Serialize the immutable summary to its public JSON shape."""
        return {
            "covered": self.covered,
            "total": self.total,
            "percent": self.percent,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class KeywordPhraseAudit:
    """Exact phrase and conservative root coverage for one target."""

    keyword: str
    exact_covered: bool
    exact_occurrences: int
    exact_by_field: tuple[NamedCount, ...]
    root_covered: bool
    missing_roots: tuple[str, ...]

    def to_payload(self) -> KeywordPayload:
        """Serialize one phrase result to its public JSON shape."""
        return {
            "keyword": self.keyword,
            "exact_covered": self.exact_covered,
            "exact_occurrences": self.exact_occurrences,
            "exact_by_field": {item.name: item.count for item in self.exact_by_field},
            "root_covered": self.root_covered,
            "missing_roots": list(self.missing_roots),
        }


@dataclass(frozen=True, slots=True)
class BackendSearchTermsAudit:
    """Backend terms separated into incremental and visible-redundant roots."""

    token_count: int
    unique_token_count: int
    utf8_bytes: int
    incremental_tokens: tuple[str, ...]
    incremental_percent: float
    visible_redundant_tokens: tuple[str, ...]
    visible_redundant_percent: float

    def to_payload(self) -> BackendSearchTermsPayload:
        """Serialize backend analysis to its public JSON shape."""
        return {
            "token_count": self.token_count,
            "unique_token_count": self.unique_token_count,
            "utf8_bytes": self.utf8_bytes,
            "incremental_tokens": list(self.incremental_tokens),
            "incremental_percent": self.incremental_percent,
            "visible_redundant_tokens": list(self.visible_redundant_tokens),
            "visible_redundant_percent": self.visible_redundant_percent,
        }


@dataclass(frozen=True, slots=True)
class KeywordEmbeddingAudit:
    """Complete typed result of one keyword-embedding audit."""

    target_keyword_count: int
    exact_phrase_coverage: CoverageSummary
    root_set_coverage: CoverageSummary
    keywords: tuple[KeywordPhraseAudit, ...]
    root_token_counts: tuple[NamedCount, ...]
    backend_search_terms: BackendSearchTermsAudit

    def to_payload(self) -> KeywordEmbeddingAuditPayload:
        """Serialize the audit to the original script's JSON contract."""
        return {
            "target_keyword_count": self.target_keyword_count,
            "exact_phrase_coverage": self.exact_phrase_coverage.to_payload(),
            "root_set_coverage": self.root_set_coverage.to_payload(),
            "keywords": [keyword.to_payload() for keyword in self.keywords],
            "root_token_counts": {item.name: item.count for item in self.root_token_counts},
            "backend_search_terms": self.backend_search_terms.to_payload(),
        }


TOKEN_RE: Final = re.compile(r"[A-Za-z0-9À-ÖØ-öø-ÿĀ-ž]+(?:['\u2019][A-Za-z]+)?")
EXACT_NOTE: Final = (
    "Nested exact matches are mechanical matches, not independent keyword placements."
)
ROOT_NOTE: Final = (
    "Root coverage supports relevance analysis but does not guarantee indexing or rank."
)
_MIN_PLURAL_LENGTH: Final = 2
_MIN_SUFFIX_LENGTH: Final = 3


@final
class MissingKeywordsError(Exception):
    """Raised when an audit has no non-empty target phrases."""

    @override
    def __str__(self) -> str:
        """Render the stable CLI-compatible failure message."""
        return "provide at least one keyword"


def tokens(text: str) -> tuple[str, ...]:
    """Normalize searchable tokens while preserving apostrophe words."""
    return tuple(match.group(0).lower().replace("\u2019", "'") for match in TOKEN_RE.finditer(text))


def conservative_forms(token: str) -> frozenset[str]:
    """Return conservative singular and plural forms for root checks."""
    forms = {token}
    if token.endswith("y") and len(token) > _MIN_PLURAL_LENGTH:
        forms.add(f"{token[:-1]}ies")
    else:
        forms.add(f"{token}s")
        forms.add(f"{token}es")
    if token.endswith("ies") and len(token) > _MIN_SUFFIX_LENGTH:
        forms.add(f"{token[:-3]}y")
    elif token.endswith("es") and len(token) > _MIN_SUFFIX_LENGTH:
        forms.add(token[:-2])
    elif token.endswith("s") and not token.endswith("ss") and len(token) > _MIN_PLURAL_LENGTH:
        forms.add(token[:-1])
    return frozenset(forms)


def exact_count(text: str, phrase: str) -> int:
    """Count normalized contiguous phrase occurrences."""
    haystack = tokens(text)
    needle = tokens(phrase)
    if not needle:
        return 0
    width = len(needle)
    return sum(
        haystack[index : index + width] == needle for index in range(len(haystack) - width + 1)
    )


def _unique_keywords(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def load_keywords(values: Iterable[str], path: Path | None = None) -> tuple[str, ...]:
    """Merge CLI values and a UTF-8 line file while preserving first occurrence."""
    file_values: tuple[str, ...] = ()
    if path is not None:
        file_values = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return _unique_keywords((*values, *file_values))


def _percent(part: int, total: int) -> float:
    return round(part / total * 100, 2) if total else 0.0


def audit_keyword_embedding(
    listing: KeywordAuditListing,
    keywords: Iterable[str],
) -> KeywordEmbeddingAudit:
    """Audit exact phrases, root coverage, and backend-term incrementality."""
    targets = _unique_keywords(keywords)
    if not targets:
        raise MissingKeywordsError

    fields = (
        ("title", listing.title),
        ("item_highlights", listing.item_highlights),
        *((f"bullet_{index}", value) for index, value in enumerate(listing.bullets, 1)),
        ("description", listing.description),
        ("search_terms", listing.search_terms),
    )
    all_tokens = tokens(" ".join(text for _field, text in fields))
    all_token_set = frozenset(all_tokens)
    phrase_rows: list[KeywordPhraseAudit] = []
    exact_covered = 0
    root_covered = 0

    for phrase in targets:
        exact_by_field = tuple(
            NamedCount(field, count)
            for field, text in fields
            if (count := exact_count(text, phrase))
        )
        missing_roots = tuple(
            root
            for root in tokens(phrase)
            if not conservative_forms(root).intersection(all_token_set)
        )
        exact = bool(exact_by_field)
        roots_complete = not missing_roots
        exact_covered += int(exact)
        root_covered += int(roots_complete)
        phrase_rows.append(
            KeywordPhraseAudit(
                keyword=phrase,
                exact_covered=exact,
                exact_occurrences=sum(item.count for item in exact_by_field),
                exact_by_field=exact_by_field,
                root_covered=roots_complete,
                missing_roots=missing_roots,
            )
        )

    visible_tokens = frozenset(
        tokens(
            " ".join(
                (listing.title, listing.item_highlights, *listing.bullets, listing.description)
            )
        )
    )
    search_tokens = tokens(listing.search_terms)
    unique_search_tokens = frozenset(search_tokens)
    incremental = tuple(sorted(unique_search_tokens - visible_tokens))
    redundant = tuple(sorted(unique_search_tokens.intersection(visible_tokens)))
    root_counts = Counter(all_tokens)

    return KeywordEmbeddingAudit(
        target_keyword_count=len(targets),
        exact_phrase_coverage=CoverageSummary(
            exact_covered,
            len(targets),
            _percent(exact_covered, len(targets)),
            EXACT_NOTE,
        ),
        root_set_coverage=CoverageSummary(
            root_covered,
            len(targets),
            _percent(root_covered, len(targets)),
            ROOT_NOTE,
        ),
        keywords=tuple(phrase_rows),
        root_token_counts=tuple(
            NamedCount(name, count) for name, count in root_counts.most_common()
        ),
        backend_search_terms=BackendSearchTermsAudit(
            token_count=len(search_tokens),
            unique_token_count=len(unique_search_tokens),
            utf8_bytes=len(listing.search_terms.encode("utf-8")),
            incremental_tokens=incremental,
            incremental_percent=_percent(len(incremental), len(unique_search_tokens)),
            visible_redundant_tokens=redundant,
            visible_redundant_percent=_percent(len(redundant), len(unique_search_tokens)),
        ),
    )


__all__ = [
    "BackendSearchTermsAudit",
    "CoverageSummary",
    "KeywordAuditListing",
    "KeywordEmbeddingAudit",
    "KeywordEmbeddingAuditPayload",
    "KeywordPhraseAudit",
    "MissingKeywordsError",
    "NamedCount",
    "audit_keyword_embedding",
    "conservative_forms",
    "exact_count",
    "load_keywords",
    "tokens",
]
