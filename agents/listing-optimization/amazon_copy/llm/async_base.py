"""Compatibility shim — AsyncLLMClient lives in ``amazon_copy.llm.base``."""

from __future__ import annotations

from amazon_copy.llm.base import AsyncLLMClient

__all__ = ["AsyncLLMClient"]
