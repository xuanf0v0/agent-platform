"""OpenAI-compatible response parsing without network access."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from amazon_copy.llm import openai_compat

if TYPE_CHECKING:
    import pytest


class _FakeCompletions:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.request: dict[str, object] | None = None

    def create(self, **request: object) -> object:
        self.request = request
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    completions: _FakeCompletions
    init: dict[str, str | float | int]

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 600.0,
        max_retries: int = 2,
    ) -> None:
        type(self).init = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        type(self).completions = _FakeCompletions('{"titles": []}')
        self.chat = SimpleNamespace(completions=type(self).completions)


def test_openai_compat_passes_deepseek_base_and_parses_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openai_compat, "OpenAI", _FakeOpenAI)
    client = openai_compat.OpenAILLM("deepseek-v4-flash", "test-key", "https://api.deepseek.com")

    content = client.complete("Return JSON.", "Generate titles.", max_tokens=64)

    assert content == '{"titles": []}'
    assert _FakeOpenAI.init == {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
        "timeout": 60.0,
        "max_retries": 1,
    }
    assert _FakeOpenAI.completions.request == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Generate titles."},
        ],
        "temperature": 0.4,
        "max_tokens": 64,
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert client.call_count == 1


def test_openai_compat_returns_empty_string_for_null_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openai_compat, "OpenAI", _FakeOpenAI)
    client = openai_compat.OpenAILLM("deepseek-chat", "test-key", "https://api.deepseek.com")
    _FakeOpenAI.completions.content = None

    assert client.complete("system", "user", json_mode=False) == ""
    assert "response_format" not in (_FakeOpenAI.completions.request or {})
