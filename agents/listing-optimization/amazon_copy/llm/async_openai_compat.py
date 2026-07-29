"""Compatibility shim — AsyncOpenAILLM lives in ``amazon_copy.llm.openai_compat``."""

from __future__ import annotations

from amazon_copy.llm.openai_compat import AsyncOpenAILLM

__all__ = ["AsyncOpenAILLM"]
