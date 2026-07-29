"""OpenAI-compatible synchronous chat-completion adapter."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from openai import APITimeoutError, OpenAI

from amazon_create.llm.base import ConfigError

_REQUEST_TIMEOUT_SECONDS = 60.0


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
        request = self._request(system, user, kwargs)
        try:
            response = self._client.chat.completions.create(**request)
        except APITimeoutError as exc:
            raise TimeoutError from exc
        return response.choices[0].message.content or ""

    def stream(self, system: str, user: str, **kwargs: object) -> Iterator[str]:
        """Yield text deltas from an OpenAI-compatible streaming response."""
        self._call_count += 1
        request = self._request(system, user, kwargs)
        request["stream"] = True
        try:
            response = self._client.chat.completions.create(**request)
            for chunk in response:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield text
        except APITimeoutError as exc:
            raise TimeoutError from exc

    def _request(
        self,
        system: str,
        user: str,
        kwargs: dict[str, object],
    ) -> dict[str, Any]:
        options = dict(kwargs)
        json_mode = options.pop("json_mode", True)
        images = options.pop("images", ())
        user_content: str | list[dict[str, Any]] = user
        if isinstance(images, (list, tuple)) and images:
            user_content = [{"type": "text", "text": user}]
            for image in images[:8]:
                if isinstance(image, str) and image.startswith("data:image/"):
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image, "detail": "auto"},
                        }
                    )
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": options.pop("temperature", 0.4),
            **options,
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
            if self._model in {"deepseek-v4-flash", "deepseek-v4-pro"}:
                request["extra_body"] = {"thinking": {"type": "disabled"}}
        return request
