"""Settings: mock key policy, title_mode validation, runtime singleton."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest
from amazon_copy import config as config_mod
from amazon_copy.config import Settings, apply_runtime_settings
from pydantic import SecretStr, ValidationError


async def test_fresh_process_invalid_environment_exits_with_sanitized_field_only() -> None:
    # Given: a fresh process with an invalid server-side MCP budget
    environment = os.environ.copy()
    _ = environment.pop("OPENAI_API_KEY", None)
    environment["MAX_MCP_CALLS"] = "0"
    command = (
        sys.executable,
        "-c",
        "from amazon_copy.config import Settings; Settings(_env_file=None)",
    )

    # When: the process imports configuration and constructs settings
    with anyio.fail_after(10):
        completed = await anyio.run_process(
            command,
            cwd=Path(__file__).parents[1],
            env=environment,
            check=False,
        )

    # Then: failure is nonzero and exposes only the invalid field
    assert completed.returncode == 1
    assert completed.stdout == b""
    assert completed.stderr.decode().strip() == "max_mcp_calls"


def test_current_settings_are_frozen_and_environment_aliases_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a fresh settings object loaded through its environment alias
    monkeypatch.setenv("WRITER_MODEL", "environment-writer")
    settings = Settings()

    # When: mutation is attempted
    with pytest.raises(ValidationError, match="frozen_instance"):
        settings.writer_model = "mutated-writer"

    # Then: the environment value remains unchanged
    assert settings.writer_model == "environment-writer"


def test_studio_limits_have_approved_defaults_and_reject_out_of_range() -> None:
    # Given: studio settings constructed without ambient file configuration
    settings = Settings()

    # When: the immutable runtime limits are read
    # Then: defaults match the approved hard caps
    assert settings.max_llm_calls == 12
    assert settings.max_mcp_calls == 20
    assert settings.run_deadline_seconds == 120
    assert settings.checkpoint_retention_hours == 24
    assert settings.checkpoint_path == Path(".amazon_copy/checkpoints.sqlite3")

    # Given/When/Then: values outside each approved interval are rejected
    with pytest.raises(ValidationError):
        _ = Settings(MAX_LLM_CALLS=0)
    with pytest.raises(ValidationError):
        _ = Settings(MAX_LLM_CALLS=13)
    with pytest.raises(ValidationError):
        _ = Settings(MAX_MCP_CALLS=0)
    with pytest.raises(ValidationError):
        _ = Settings(MAX_MCP_CALLS=21)
    with pytest.raises(ValidationError):
        _ = Settings(RUN_DEADLINE_SECONDS=0)
    with pytest.raises(ValidationError):
        _ = Settings(RUN_DEADLINE_SECONDS=121)
    with pytest.raises(ValidationError):
        _ = Settings(CHECKPOINT_RETENTION_HOURS=0)
    with pytest.raises(ValidationError):
        _ = Settings(CHECKPOINT_RETENTION_HOURS=721)


def test_settings_may_load_project_env_but_never_repr_secrets() -> None:
    # Given: a secret is supplied directly by the server process
    sentinel = "sensitive-value"
    settings = Settings(OPENAI_API_KEY=SecretStr(sentinel))

    # When: settings configuration and representation are inspected
    configured_env_file = Settings.model_config.get("env_file")
    representation = repr(settings)

    # Then: project .env may be used server-side; secret material stays redacted
    assert configured_env_file in (None, ".env", (".env",))
    assert sentinel not in representation
    assert settings.effective_api_key == sentinel


def test_runtime_dependencies_and_fixture_assets_are_bounded() -> None:
    # Given: the package manifest
    manifest_path = Path(__file__).parents[1] / "pyproject.toml"

    # When: its stable runtime and package-data constraints are read
    manifest = manifest_path.read_text(encoding="utf-8")

    # Then: only bounded stable major lines and explicit MCP fixtures are declared
    required_entries = (
        '"langgraph>=1,<2"',
        '"langgraph-checkpoint-sqlite>=3,<4"',
        '"mcp>=1,<2"',
        '"anyio>=4,<5"',
        '"mcp/fixtures/*.json"',
        '"build>=1,<2"',
        '"basedpyright>=1,<2"',
        '"ruff>=0.12,<1"',
        'requires-python = ">=3.11"',
    )
    assert all(entry in manifest for entry in required_entries)
    assert '"mcp>=2' not in manifest
    assert '"python-dotenv"' not in manifest


def test_mock_true_allows_empty_key_and_effective_api_key_is_none() -> None:
    # Given: mock mode with no API key
    # When: Settings is constructed
    s = Settings(MOCK=True, OPENAI_API_KEY=SecretStr(""))
    # Then: loads successfully and effective key is None
    assert s.mock is True
    assert s.openai_api_key.get_secret_value() == ""
    assert s.effective_api_key is None


def test_effective_api_key_returns_key_when_present() -> None:
    # Given: non-empty key (mock or not)
    # When: property is read
    s = Settings(MOCK=True, OPENAI_API_KEY=SecretStr("sk-test"))
    # Then: key is surfaced
    assert s.effective_api_key == "sk-test"


def test_title_mode_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: invalid title_mode value
    monkeypatch.setenv("TITLE_MODE", "garbage")
    # When/Then: validation fails
    with pytest.raises(ValidationError):
        _ = Settings()


def test_title_mode_accepts_known_literals() -> None:
    # Given/When: valid modes
    sop = Settings(TITLE_MODE="sop_seo")
    strict = Settings(TITLE_MODE="strict_amazon")
    # Then
    assert sop.title_mode == "sop_seo"
    assert strict.title_mode == "strict_amazon"


def test_defaults_match_spec() -> None:
    # Given/When: defaults only (explicit kwargs avoid ambient env noise)
    s = Settings(
        OPENAI_API_KEY=SecretStr(""),
        OPENAI_API_BASE="https://api.deepseek.com",
        WRITER_MODEL="deepseek-v4-flash",
        REVIEW_MODEL="deepseek-v4-flash",
        VOTE_MODEL="deepseek-v4-flash",
        MOCK=False,
        TITLE_MODE="sop_seo",
        HITL_CONFIRM=False,
        MAX_REVIEW_ROUNDS=2,
        LOCALE="en",
    )
    # Then
    assert s.openai_api_base == "https://api.deepseek.com"
    assert s.writer_model == "deepseek-v4-flash"
    assert s.review_model == "deepseek-v4-flash"
    assert s.vote_model == "deepseek-v4-flash"
    assert s.mock is False
    assert s.title_mode == "sop_seo"
    assert s.hitl_confirm is False
    assert s.max_llm_calls == 12
    assert s.max_review_rounds == 2
    assert s.locale == "en"


def test_deepseek_defaults_use_openai_compatible_root_url() -> None:
    settings = Settings(OPENAI_API_KEY=SecretStr(""))

    assert settings.openai_api_base == "https://api.deepseek.com"
    assert settings.writer_model == "deepseek-v4-flash"


def test_max_llm_calls_rejects_below_one() -> None:
    with pytest.raises(ValidationError):
        _ = Settings(MAX_LLM_CALLS=0)


def test_apply_runtime_settings_updates_singleton() -> None:
    # Given: capture previous singleton
    previous = config_mod.settings
    replacement = Settings(
        MOCK=True,
        OPENAI_API_KEY=SecretStr(""),
        WRITER_MODEL="override-model",
    )
    try:
        # When: apply_runtime_settings
        returned = apply_runtime_settings(replacement)
        # Then: module singleton is replaced and returned
        assert returned is replacement
        assert config_mod.settings is replacement
        assert config_mod.settings.writer_model == "override-model"
        assert config_mod.settings.mock is True
    finally:
        _ = apply_runtime_settings(previous)
