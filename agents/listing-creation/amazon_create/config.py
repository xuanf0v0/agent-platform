"""Application settings for listing creation (self-contained, vendored MCP)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CHECKPOINT_PATH: Final[Path] = Path(".amazon_create/checkpoints.sqlite3")


class Settings(BaseSettings):
    """Server-side configuration; credentials never enter the browser."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        populate_by_name=True,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY", repr=False)
    openai_api_base: str = Field(default="https://api.deepseek.com", alias="OPENAI_API_BASE")
    writer_model: str = Field(default="deepseek-v4-flash", alias="WRITER_MODEL")
    review_model: str = Field(default="deepseek-v4-flash", alias="REVIEW_MODEL")
    vision_model: str = Field(default="", alias="VISION_MODEL")

    mock: bool = Field(default=False, alias="MOCK")
    locale: str = Field(default="en", alias="LOCALE")

    sellersprite_mcp_key: SecretStr = Field(
        default=SecretStr(""), alias="SELLERSPRITE_MCP_KEY", repr=False
    )
    sorftime_mcp_key: SecretStr = Field(
        default=SecretStr(""), alias="SORFTIME_MCP_KEY", repr=False
    )
    sif_mcp_key: SecretStr = Field(default=SecretStr(""), alias="SIF_MCP_KEY", repr=False)
    sellersprite_mcp_url: str = Field(
        default="https://mcp.sellersprite.com/mcp", alias="SELLERSPRITE_MCP_URL"
    )
    sorftime_mcp_url: str = Field(default="https://mcp.sorftime.com", alias="SORFTIME_MCP_URL")
    sif_mcp_url: str = Field(default="https://mcp.sif.com/mcp", alias="SIF_MCP_URL")
    remote_mcp_timeout_seconds: float = Field(
        default=25.0, ge=0.01, le=30.0, alias="REMOTE_MCP_TIMEOUT_SECONDS"
    )

    writing_tools_mcp_enabled: bool = Field(default=False, alias="WRITING_TOOLS_MCP_ENABLED")
    writing_tools_mcp_command: str = Field(default="", alias="WRITING_TOOLS_MCP_COMMAND")
    writing_editor_mcp_enabled: bool = Field(default=False, alias="WRITING_EDITOR_MCP_ENABLED")
    writing_editor_mcp_command: str = Field(default="", alias="WRITING_EDITOR_MCP_COMMAND")
    writing_editor_mcp_polish: bool = Field(default=False, alias="WRITING_EDITOR_MCP_POLISH")
    writing_mcp_timeout_seconds: float = Field(
        default=20.0, ge=0.5, le=60.0, alias="WRITING_MCP_TIMEOUT_SECONDS"
    )

    max_llm_calls: int = Field(default=12, ge=1, le=24, alias="MAX_LLM_CALLS")
    max_mcp_calls: int = Field(default=20, ge=1, le=40, alias="MAX_MCP_CALLS")
    run_deadline_seconds: int = Field(default=120, ge=1, le=300, alias="RUN_DEADLINE_SECONDS")
    checkpoint_path: Path = Field(default=_DEFAULT_CHECKPOINT_PATH, alias="CHECKPOINT_PATH")

    @property
    def effective_api_key(self) -> str | None:
        """Return API key, or None when MOCK and empty."""
        api_key = self.openai_api_key.get_secret_value()
        if self.mock and not api_key:
            return None
        return api_key or None


settings = Settings()


def apply_runtime_settings(new: Settings) -> Settings:
    """Replace the module-level settings singleton."""
    global settings  # noqa: PLW0603
    settings = new
    return settings
