"""Verified internal Amazon copy-optimization contract resources."""

from amazon_copy.resources.amazon_copy_optimization.errors import (
    ContractResourceError,
    ContractResourceErrorCode,
    ContractResourceErrorDetails,
)
from amazon_copy.resources.amazon_copy_optimization.keyword_audit import (
    KeywordAuditListing,
    KeywordEmbeddingAudit,
    KeywordEmbeddingAuditPayload,
    MissingKeywordsError,
    audit_keyword_embedding,
    conservative_forms,
    exact_count,
    load_keywords,
    tokens,
)
from amazon_copy.resources.amazon_copy_optimization.loader import (
    ContractResourceLoader,
    LoadedContractMarkdown,
)
from amazon_copy.resources.amazon_copy_optimization.manifest import (
    CONTRACT_MANIFEST,
    CONTRACT_VERSION,
    PROFILE_RESOURCES,
    AuthorityClass,
    ContractMarketplace,
    ContractResource,
    ContractResourceKind,
)

__all__ = [
    "CONTRACT_MANIFEST",
    "CONTRACT_VERSION",
    "PROFILE_RESOURCES",
    "AuthorityClass",
    "ContractMarketplace",
    "ContractResource",
    "ContractResourceError",
    "ContractResourceErrorCode",
    "ContractResourceErrorDetails",
    "ContractResourceKind",
    "ContractResourceLoader",
    "KeywordAuditListing",
    "KeywordEmbeddingAudit",
    "KeywordEmbeddingAuditPayload",
    "LoadedContractMarkdown",
    "MissingKeywordsError",
    "audit_keyword_embedding",
    "conservative_forms",
    "exact_count",
    "load_keywords",
    "tokens",
]
