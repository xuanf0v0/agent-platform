"""LLM client factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import amazon_create.config as config_module
from amazon_create.llm.base import ConfigError, LLMClient
from amazon_create.llm.mock import MockLLM

if TYPE_CHECKING:
    from amazon_create.config import Settings


def get_llm(settings: Settings | None = None, *, role: str = "writer") -> LLMClient:
    """Return mock or OpenAI-compatible client based on settings."""
    runtime = settings or config_module.settings
    if runtime.mock:
        return MockLLM(role=role)
    from amazon_create.llm.openai_compat import OpenAILLM

    key = runtime.effective_api_key
    if not key:
        message = "OPENAI_API_KEY is required when MOCK=false"
        raise ConfigError(message)
    if role == "writer":
        model = runtime.writer_model
    elif role == "vision":
        model = runtime.vision_model or runtime.writer_model
    else:
        model = runtime.review_model
    return OpenAILLM(model=model, api_key=key, base_url=runtime.openai_api_base)


__all__ = ["ConfigError", "LLMClient", "MockLLM", "get_llm"]
