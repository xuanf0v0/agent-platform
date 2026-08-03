"""Server-side settings for the product research service."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        # Shared credentials/models are loaded from the existing business agents.
        # Later files win, so optimization is preferred and a private local file
        # remains an optional emergency override without exposing secrets in UI.
        env_file=("../listing-creation/.env", "../listing-optimization/.env", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        # Keep environment loading alias-only.  Shared agent env files contain
        # generic names such as MAX_LLM_CALLS; accepting Python field names here
        # would accidentally apply those values to this agent's bounded budget.
        populate_by_name=False,
    )

    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")
    openai_api_base: str = Field(default="https://api.deepseek.com", alias="OPENAI_API_BASE")
    analysis_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("ANALYSIS_MODEL", "WRITER_MODEL"),
    )
    review_model: str = Field(default="deepseek-v4-flash", alias="REVIEW_MODEL")
    sorftime_mcp_key: SecretStr = Field(default=SecretStr(""), alias="SORFTIME_MCP_KEY")
    sellersprite_mcp_key: SecretStr = Field(default=SecretStr(""), alias="SELLERSPRITE_MCP_KEY")
    sif_mcp_key: SecretStr = Field(default=SecretStr(""), alias="SIF_MCP_KEY")
    sorftime_mcp_url: str = Field(default="https://mcp.sorftime.com", alias="SORFTIME_MCP_URL")
    sellersprite_mcp_url: str = Field(
        default="https://mcp.sellersprite.com/mcp", alias="SELLERSPRITE_MCP_URL"
    )
    sif_mcp_url: str = Field(default="https://mcp.sif.com/mcp", alias="SIF_MCP_URL")
    remote_mcp_timeout_seconds: float = Field(
        default=35.0, ge=1, le=120, alias="PRODUCT_RESEARCH_MCP_TIMEOUT_SECONDS"
    )
    max_mcp_calls: int = Field(default=60, ge=1, le=100, alias="PRODUCT_RESEARCH_MAX_MCP_CALLS")
    max_llm_calls: int = Field(default=4, ge=1, le=8, alias="PRODUCT_RESEARCH_MAX_LLM_CALLS")
    run_deadline_seconds: int = Field(
        default=300, ge=10, le=900, alias="PRODUCT_RESEARCH_DEADLINE_SECONDS"
    )
    checkpoint_path: Path = Field(
        default=Path(".product_research/runs.sqlite3"),
        alias="PRODUCT_RESEARCH_CHECKPOINT_PATH",
    )

    def provider_keys(self) -> dict[str, str]:
        return {
            "sorftime": self.sorftime_mcp_key.get_secret_value(),
            "sellersprite": self.sellersprite_mcp_key.get_secret_value(),
            "sif": self.sif_mcp_key.get_secret_value(),
        }

    def has_provider(self) -> bool:
        return any(self.provider_keys().values())
