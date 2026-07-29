"""OpenAI-compatible sync and async chat-completion adapters."""

from __future__ import annotations

from typing import Any

from openai import APITimeoutError, AsyncOpenAI, OpenAI

from amazon_copy.llm.base import ConfigError

_REQUEST_TIMEOUT_SECONDS = 60.0
_DEEPSEEK_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}


def _build_chat_request(
    model: str,
    system: str,
    user: str,
    *,
    json_mode: bool,
    temperature: object,
    extra: dict[str, Any],
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        **extra,
    }
    if json_mode:
        request["response_format"] = {"type": "json_object"}
        if model in _DEEPSEEK_MODELS:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
    return request


class OpenAILLM:
    """Small adapter supporting OpenAI-compatible base URLs."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        """Initialize the adapter with one model and provider endpoint."""
        if not api_key:
            message = "OpenAI API key is required when MOCK=false"
            raise ConfigError(message)
        self._model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of completion calls made by this adapter."""
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Create one chat completion, requesting JSON output by default."""
        self._call_count += 1
        json_mode = bool(kwargs.pop("json_mode", True))
        temperature = kwargs.pop("temperature", 0.4)
        request = _build_chat_request(
            self._model,
            system,
            user,
            json_mode=json_mode,
            temperature=temperature,
            extra=dict(kwargs),
        )
        try:
            response = self._client.chat.completions.create(**request)
        except APITimeoutError as exc:
            raise TimeoutError from exc
        return response.choices[0].message.content or ""


class AsyncOpenAILLM:
    """Async adapter supporting OpenAI-compatible base URLs (e.g. DeepSeek)."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        """Initialize the adapter with one model and provider endpoint."""
        if not api_key:
            message = "OpenAI API key is required when MOCK=false"
            raise ConfigError(message)
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of completion calls made by this adapter."""
        return self._call_count

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Create one async chat completion, requesting JSON output by default."""
        self._call_count += 1
        json_mode = bool(kwargs.pop("json_mode", True))
        temperature = kwargs.pop("temperature", 0.4)
        request = _build_chat_request(
            self._model,
            system,
            user,
            json_mode=json_mode,
            temperature=temperature,
            extra=dict(kwargs),
        )
        try:
            response = await self._client.chat.completions.create(**request)
        except APITimeoutError as exc:
            raise TimeoutError from exc
        return response.choices[0].message.content or ""
