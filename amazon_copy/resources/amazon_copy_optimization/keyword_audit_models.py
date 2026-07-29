"""Compatibility shim — keyword audit models live in ``keyword_audit``."""

from __future__ import annotations

from amazon_copy.resources.amazon_copy_optimization.keyword_audit import (
    BackendSearchTermsAudit,
    CoverageSummary,
    KeywordAuditListing,
    KeywordEmbeddingAudit,
    KeywordEmbeddingAuditPayload,
    KeywordPhraseAudit,
    NamedCount,
)

__all__ = [
    "BackendSearchTermsAudit",
    "CoverageSummary",
    "KeywordAuditListing",
    "KeywordEmbeddingAudit",
    "KeywordEmbeddingAuditPayload",
    "KeywordPhraseAudit",
    "NamedCount",
]
