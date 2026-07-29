"""LLM and settings resolution for the simple optimizer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.config import Settings
from amazon_copy.llm import LLMClient, get_llm
from amazon_copy.llm.base import ConfigError

if TYPE_CHECKING:
    from pydantic import SecretStr


class SimpleOptimizerError(ValueError):
    """Typed failure safe to show at the optimizer boundary."""


def _settings_real(key: SecretStr, base: Settings) -> Settings:
    return Settings(
        MOCK=False,
        OPENAI_API_KEY=key,
        OPENAI_API_BASE=base.openai_api_base,
        WRITER_MODEL=base.writer_model,
        REVIEW_MODEL=base.review_model,
        VOTE_MODEL=base.vote_model,
    )


def production_settings(settings: Settings | None) -> Settings:
    """Return settings with mock forced off for the listing-optimizer path."""
    runtime = settings or Settings()
    if not runtime.mock and runtime.effective_api_key:
        return runtime
    key = runtime.openai_api_key
    secret = key.get_secret_value()
    if not secret:
        env = Settings()
        key = env.openai_api_key
        secret = key.get_secret_value()
        if not secret:
            message = (
                "未配置 OPENAI_API_KEY, 无法调用真实模型 / "
                "OPENAI_API_KEY is required; mock is disabled for listing optimizer"
            )
            raise SimpleOptimizerError(message)
        return _settings_real(key, env)
    return _settings_real(key, runtime)


def resolve_client(
    llm: LLMClient | None,
    settings: Settings | None,
) -> LLMClient:
    """Prefer an injected client, otherwise resolve the production role."""
    if llm is not None:
        return llm
    try:
        return get_llm("listing_optimizer", settings=production_settings(settings))
    except ConfigError as exc:
        raise SimpleOptimizerError(str(exc)) from exc


__all__ = ["SimpleOptimizerError", "production_settings", "resolve_client"]
