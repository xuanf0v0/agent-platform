"""Role-aware LLM client factory — sync and async (studio)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import amazon_copy.config as config_module
from amazon_copy.llm.base import AsyncLLMClient, ConfigError, LLMClient
from amazon_copy.llm.mock import ROLES, MockLLM, STUDIO_ROLES

if TYPE_CHECKING:
    from amazon_copy.config import Settings


def get_llm(role: str, *, settings: Settings | None = None) -> LLMClient:
    """Build the configured client for a known orchestration role."""
    if role not in ROLES:
        message = f"Unknown LLM role: {role!r}. Valid roles: {list(ROLES)}"
        raise ConfigError(message)
    if settings is None:
        settings = config_module.settings
    if settings.mock:
        return MockLLM(role)
    if not settings.effective_api_key:
        message = "OpenAI API key is required when MOCK=false"
        raise ConfigError(message)
    review_roles = {
        "seo_check",
        "scorecard",
        "score_summary_zh",
        "compliance_advice_zh",
        "listing_diagnosis_zh",
        "product_type_classifier",
    }
    model = settings.review_model if role in review_roles else settings.writer_model
    from amazon_copy.llm.openai_compat import OpenAILLM  # noqa: PLC0415

    return OpenAILLM(model, settings.effective_api_key, settings.openai_api_base)


def route_model(role: str, settings: Settings) -> str:
    """Return the model name for *role* based on *settings*.

    Routing rules
    -------------
    * writers / reviser / integrator → ``settings.writer_model``
    * critic                       → ``settings.review_model``
    * judge                        → ``settings.vote_model``
    """
    if role in {"writer_seo", "writer_differentiation", "writer_clarity", "reviser", "integrator"}:
        return settings.writer_model
    if role == "critic":
        return settings.review_model
    if role == "judge":
        return settings.vote_model
    message = f"Unknown studio role for routing: {role!r}"
    raise ConfigError(message)


def get_async_llm(role: str, *, settings: Settings | None = None) -> AsyncLLMClient:
    """Build an async LLM client for a studio role (mock or real OpenAI-compatible)."""
    if role not in STUDIO_ROLES:
        message = f"Unknown studio role: {role!r}. Valid roles: {list(STUDIO_ROLES)}"
        raise ConfigError(message)
    if settings is None:
        settings = config_module.settings
    if settings.mock:
        from amazon_copy.llm.mock import AsyncMockLLM  # noqa: PLC0415

        return AsyncMockLLM(role)
    if not settings.effective_api_key:
        message = "OpenAI API key is required when MOCK=false"
        raise ConfigError(message)
    from amazon_copy.llm.openai_compat import AsyncOpenAILLM  # noqa: PLC0415

    model = route_model(role, settings)
    return AsyncOpenAILLM(model, settings.effective_api_key, settings.openai_api_base)


__all__ = [
    "ROLES",
    "STUDIO_ROLES",
    "ConfigError",
    "LLMClient",
    "AsyncLLMClient",
    "MockLLM",
    "get_llm",
    "get_async_llm",
    "route_model",
]
