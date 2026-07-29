"""Compatibility shim — package_from_studio_state lives in ``state``."""

from __future__ import annotations

from amazon_copy.orchestrator.state import package_from_studio_state

__all__ = ["package_from_studio_state"]
