"""Compatibility shim — contract resource types live in ``manifest``."""

from __future__ import annotations

from amazon_copy.resources.amazon_copy_optimization.manifest import (
    AuthorityClass,
    ContractMarketplace,
    ContractResource,
    ContractResourceKind,
)

__all__ = [
    "AuthorityClass",
    "ContractMarketplace",
    "ContractResource",
    "ContractResourceKind",
]
