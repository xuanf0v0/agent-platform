"""Versioned studio report and separated seller/audit rendering boundary."""

from __future__ import annotations

import re
import unicodedata
from typing import ClassVar, Final, Literal, LiteralString, Never, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from amazon_copy.utils.text_metrics import plain_len, strip_md_bold

_TITLE_OPTION_COUNT: Final[int] = 3
_SENSITIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""(?isx)(?:
    -----BEGIN[ \t]+ (?P<private_key_label>(?:[A-Z0-9]+[ \t]+)*PRIVATE[ \t]+KEY)
    ----- .*? -----END[ \t]+ (?P=private_key_label) ----- |
    authorization[ \t]*:[ \t]*[^\r\n]+ |
    bearer\s+[^\s,;]+ |
    (?:api[_ -]?key|access[_ -]?token|secret|raw[_ -]?payload)\s*[:=]\s*[^\s,;]+ |
    secret[_ -]?sentinel
    )"""
)


def _redact_sensitive(value: str) -> str:
    return _SENSITIVE_PATTERN.sub("[REDACTED]", value)


def _invalid(code: LiteralString, message: LiteralString) -> Never:
    raise PydanticCustomError(code, message)


def _seller_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        _invalid("blank_seller_copy", "seller copy must not be blank")
    if _redact_sensitive(stripped) != stripped:
        _invalid("sensitive_seller_copy", "seller copy contains sensitive material")
    return stripped


def _private_text(value: str) -> str:
    stripped = _redact_sensitive(value.strip())
    if not stripped:
        _invalid("blank_private_text", "report text must not be blank")
    return stripped


class _FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class _CountedSellerText(_FrozenModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _parse_text(cls, value: str) -> str:
        return _seller_text(value)

    @computed_field
    @property
    def character_count(self) -> int:
        return plain_len(self.text)


class TitleOption(_CountedSellerText):
    """One seller-ready title option with a derived count."""


class BulletOption(_CountedSellerText):
    """One seller-ready bullet point with a derived count."""


class EvidenceGap(_FrozenModel):
    """One unsupported or missing report fact."""

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @field_validator("field", "reason")
    @classmethod
    def _redact_text(cls, value: str) -> str:
        return _private_text(value)


class KeywordAllocation(_FrozenModel):
    """Deterministic placement record for one keyword."""

    keyword: str = Field(min_length=1)
    placements: tuple[str, ...] = ()

    @field_validator("keyword")
    @classmethod
    def _redact_keyword(cls, value: str) -> str:
        return _private_text(value)

    @field_validator("placements")
    @classmethod
    def _redact_placements(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_private_text(value) for value in values)


class Citation(_FrozenModel):
    """Redacted provenance pointer without raw source content."""

    claim_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    locator: str = ""

    @field_validator("claim_id", "source_id")
    @classmethod
    def _redact_identifier(cls, value: str) -> str:
        return _private_text(value)

    @field_validator("locator")
    @classmethod
    def _redact_locator(cls, value: str) -> str:
        return _redact_sensitive(value.strip())


class AuditMetadata(_FrozenModel):
    """Allowlisted execution metadata safe for read-only output."""

    run_id: str = Field(min_length=1)
    request_hash: str = Field(min_length=1)
    graph_version: str = "2"
    prompt_version: str = ""
    model_version: str = ""
    provider_version: str = ""
    llm_calls: int = Field(default=0, ge=0)
    mcp_calls: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)

    @field_validator("run_id", "request_hash")
    @classmethod
    def _parse_identity(cls, value: str) -> str:
        return _private_text(value)

    @field_validator("graph_version", "prompt_version", "model_version", "provider_version")
    @classmethod
    def _redact_metadata(cls, value: str) -> str:
        return _redact_sensitive(value.strip())


class OptimizationReport(_FrozenModel):
    """Canonical version-two successful optimization payload."""

    schema_version: Literal[2] = 2
    title_options: tuple[TitleOption, TitleOption, TitleOption]
    bullets: tuple[BulletOption, BulletOption, BulletOption, BulletOption, BulletOption]
    description: str = Field(min_length=1)
    search_terms: str = Field(min_length=1)
    analysis: str = Field(min_length=1)
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    keyword_allocation: tuple[KeywordAllocation, ...] = ()
    compliance_notes: tuple[str, ...] = ()
    return_risk_notes: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    audit: AuditMetadata

    @field_validator("description")
    @classmethod
    def _parse_description(cls, value: str) -> str:
        return _seller_text(value)

    @field_validator("search_terms")
    @classmethod
    def _normalize_search_terms(cls, value: str) -> str:
        public_value = _seller_text(value)
        tokens = strip_md_bold(unicodedata.normalize("NFKC", public_value)).split()
        normalized = tuple(dict.fromkeys(token.casefold() for token in tokens))
        if not normalized:
            _invalid("blank_search_terms", "Search Terms must not be blank")
        return " ".join(normalized)

    @field_validator("analysis")
    @classmethod
    def _redact_analysis(cls, value: str) -> str:
        return _private_text(value)

    @field_validator("compliance_notes", "return_risk_notes")
    @classmethod
    def _redact_notes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_private_text(value) for value in values)

    @model_validator(mode="after")
    def _require_distinct_titles(self) -> Self:
        normalized = {
            " ".join(unicodedata.normalize("NFKC", strip_md_bold(option.text)).split()).casefold()
            for option in self.title_options
        }
        if len(normalized) != _TITLE_OPTION_COUNT:
            _invalid("duplicate_title_options", "title options must be distinct")
        return self


class SuccessOutcome(_FrozenModel):
    """Terminal outcome containing a complete report."""

    status: Literal["success"] = "success"
    report: OptimizationReport


class DegradedOutcome(_FrozenModel):
    """Terminal outcome containing safe copy with explicit limitations."""

    status: Literal["degraded"] = "degraded"
    report: OptimizationReport
    reasons: tuple[str, ...] = ()

    @field_validator("reasons")
    @classmethod
    def _redact_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_private_text(value) for value in values)


class _ReasonOutcome(_FrozenModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _redact_reason(cls, value: str) -> str:
        return _private_text(value)


class NoWinnerOutcome(_ReasonOutcome):
    """Terminal outcome produced when no candidate can safely ship."""

    status: Literal["no_winner"] = "no_winner"


class FailureOutcome(_ReasonOutcome):
    """Terminal outcome produced by an unrecoverable safe failure."""

    status: Literal["failure"] = "failure"


TerminalOutcome = SuccessOutcome | DegradedOutcome | NoWinnerOutcome | FailureOutcome


class RedactedAuditData(_FrozenModel):
    """Read-only report projection with no seller-editable or raw provider fields."""

    schema_version: Literal[2] = 2
    status: Literal["success", "degraded", "no_winner", "failure"]
    degraded_reasons: tuple[str, ...] = ()
    diagnostic: str | None = None
    title_character_counts: tuple[int, ...] = ()
    bullet_character_counts: tuple[int, ...] = ()
    analysis: str | None = None
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    keyword_allocation: tuple[KeywordAllocation, ...] = ()
    compliance_notes: tuple[str, ...] = ()
    return_risk_notes: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    audit: AuditMetadata | None = None


def _render_report(report: OptimizationReport) -> str:
    sections = [
        f"Title Option {index} ({option.character_count} characters):\n{strip_md_bold(option.text)}"
        for index, option in enumerate(report.title_options, start=1)
    ]
    sections.extend(
        f"Bullet Point {index} ({bullet.character_count} characters):\n{strip_md_bold(bullet.text)}"
        for index, bullet in enumerate(report.bullets, start=1)
    )
    sections.extend(
        (
            f"Description:\n{strip_md_bold(report.description)}",
            f"Search Terms:\n{report.search_terms}",
        )
    )
    return "\n\n".join(sections)


def _audit_report(
    report: OptimizationReport,
    status: Literal["success", "degraded"],
    reasons: tuple[str, ...],
) -> RedactedAuditData:
    return RedactedAuditData(
        status=status,
        degraded_reasons=reasons,
        title_character_counts=tuple(option.character_count for option in report.title_options),
        bullet_character_counts=tuple(bullet.character_count for bullet in report.bullets),
        analysis=report.analysis,
        evidence_gaps=report.evidence_gaps,
        keyword_allocation=report.keyword_allocation,
        compliance_notes=report.compliance_notes,
        return_risk_notes=report.return_risk_notes,
        citations=report.citations,
        audit=report.audit,
    )


def render_seller_ready(outcome: TerminalOutcome) -> str:
    """Render only seller-editable Amazon copy or a safe no-copy diagnostic."""
    match outcome:
        case SuccessOutcome(report=report) | DegradedOutcome(report=report):
            return _render_report(report)
        case NoWinnerOutcome():
            return "No seller copy was produced (no_winner)."
        case FailureOutcome():
            return "No seller copy was produced (failure)."
        case _:
            assert_never(outcome)


def render_redacted_audit(outcome: TerminalOutcome) -> RedactedAuditData:
    """Project a terminal outcome into allowlisted read-only audit data."""
    match outcome:
        case SuccessOutcome(report=report):
            return _audit_report(report, "success", ())
        case DegradedOutcome(report=report, reasons=reasons):
            return _audit_report(report, "degraded", reasons)
        case NoWinnerOutcome(reason=reason):
            return RedactedAuditData(status="no_winner", diagnostic=reason)
        case FailureOutcome(reason=reason):
            return RedactedAuditData(status="failure", diagnostic=reason)
        case _:
            assert_never(outcome)
