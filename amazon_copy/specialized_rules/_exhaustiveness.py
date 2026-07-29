"""Compatibility shim — exhaustiveness helpers live in ``models``."""

from __future__ import annotations

from amazon_copy.specialized_rules.models import reject_variant, widen_variant

__all__ = ["reject_variant", "widen_variant"]
