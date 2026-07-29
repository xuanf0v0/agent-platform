"""Application settings loaded from environment variables.

Uses pydantic-settings BaseSettings for typed, validated configuration.
When MOCK=true, missing OPENAI_API_KEY does not crash on load.

Server process may load a project-root ``.env`` (gitignored).
Credentials never enter the browser UI.

DeepSeek (OpenAI-compatible):
  OPENAI_API_KEY=<your deepseek key>
  OPENAI_API_BASE=https://api.deepseek.com
  WRITER_MODEL=deepseek-v4-flash
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Final, Literal, LiteralString
from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CHECKPOINT_PATH: Final[Path] = Path(".amazon_copy/checkpoints.sqlite3")
_SECURE_ENDPOINT_REQUIRED: Final[LiteralString] = "secure HTTPS endpoint required"
_UNSAFE_LISTING_OPTIMIZE_ENDPOINT: Final[LiteralString] = "unsafe_listing_optimize_endpoint"


class Settings(BaseSettings):
    """Immutable application configuration loaded from the process environment.

    Construct with either env-var aliases (e.g. ``OPENAI_API_KEY=...``)
    or Python field names (e.g. ``openai_api_key=...``).
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        populate_by_name=True,
        # Server-side only: load project .env when present (never browser-entered secrets).
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    # ── LLM credentials ──────────────────────────────────────────
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        alias="OPENAI_API_KEY",
        repr=False,
    )
    openai_api_base: str = Field(
        default="https://api.deepseek.com",
        alias="OPENAI_API_BASE",
    )

    # ── Model overrides ──────────────────────────────────────────
    writer_model: str = Field(
        default="deepseek-v4-flash",
        alias="WRITER_MODEL",
    )
    review_model: str = Field(
        default="deepseek-v4-flash",
        alias="REVIEW_MODEL",
    )
    vote_model: str = Field(
        default="deepseek-v4-flash",
        alias="VOTE_MODEL",
    )

    # ── Runtime flags ────────────────────────────────────────────
    mock: bool = Field(default=False, alias="MOCK")
    title_mode: Literal["sop_seo", "strict_amazon"] = Field(
        default="sop_seo",
        alias="TITLE_MODE",
    )
    hitl_confirm: bool = Field(default=False, alias="HITL_CONFIRM")
    locale: str = Field(default="en", alias="LOCALE")

    # ── Remote MCP providers (optional; empty → fixture path) ────
    sellersprite_mcp_key: SecretStr = Field(
        default=SecretStr(""),
        alias="SELLERSPRITE_MCP_KEY",
        repr=False,
    )
    sorftime_mcp_key: SecretStr = Field(
        default=SecretStr(""),
        alias="SORFTIME_MCP_KEY",
        repr=False,
    )
    sif_mcp_key: SecretStr = Field(
        default=SecretStr(""),
        alias="SIF_MCP_KEY",
        repr=False,
    )
    sellersprite_mcp_url: str = Field(
        default="https://mcp.sellersprite.com/mcp",
        alias="SELLERSPRITE_MCP_URL",
    )
    sorftime_mcp_url: str = Field(
        default="https://mcp.sorftime.com",
        alias="SORFTIME_MCP_URL",
    )
    sif_mcp_url: str = Field(
        default="https://mcp.sif.com/mcp",
        alias="SIF_MCP_URL",
    )
    remote_mcp_timeout_seconds: float = Field(
        default=25.0,
        ge=0.01,
        le=30.0,
        alias="REMOTE_MCP_TIMEOUT_SECONDS",
    )
    listing_optimize_mcp_url: str = Field(
        default="",
        alias="LISTING_OPTIMIZE_MCP_URL",
    )
    listing_optimize_mcp_token: SecretStr = Field(
        default=SecretStr(""),
        alias="LISTING_OPTIMIZE_MCP_TOKEN",
        repr=False,
    )
    listing_optimize_mcp_timeout_seconds: float = Field(
        default=10.0,
        ge=0.01,
        le=30.0,
        alias="LISTING_OPTIMIZE_MCP_TIMEOUT_SECONDS",
    )
    listing_optimize_mcp_max_resource_bytes: int = Field(
        default=64_000,
        ge=1,
        le=262_144,
        alias="LISTING_OPTIMIZE_MCP_MAX_RESOURCE_BYTES",
    )
    listing_optimize_mcp_max_pages: int = Field(
        default=16,
        ge=1,
        le=32,
        alias="LISTING_OPTIMIZE_MCP_MAX_PAGES",
    )
    listing_optimize_mcp_max_resources_per_page: int = Field(
        default=128,
        ge=1,
        le=256,
        alias="LISTING_OPTIMIZE_MCP_MAX_RESOURCES_PER_PAGE",
    )
    listing_optimize_mcp_max_total_resources: int = Field(
        default=256,
        ge=1,
        le=512,
        alias="LISTING_OPTIMIZE_MCP_MAX_TOTAL_RESOURCES",
    )

    # ── Optional writing MCPs (stdio; style/grammar only) ─────────
    writing_tools_mcp_enabled: bool = Field(
        default=False,
        alias="WRITING_TOOLS_MCP_ENABLED",
    )
    writing_tools_mcp_command: str = Field(
        default="uvx --from git+https://github.com/wdm0006/writing-tools-mcp writing-tools-mcp",
        alias="WRITING_TOOLS_MCP_COMMAND",
    )
    writing_editor_mcp_enabled: bool = Field(
        default=False,
        alias="WRITING_EDITOR_MCP_ENABLED",
    )
    writing_editor_mcp_command: str = Field(
        default="npx --yes tsx .vendor/thatsboring/writing-editor-mcp/src/server.ts",
        alias="WRITING_EDITOR_MCP_COMMAND",
    )
    writing_editor_mcp_polish: bool = Field(
        default=False,
        alias="WRITING_EDITOR_MCP_POLISH",
    )
    writing_mcp_timeout_seconds: float = Field(
        default=20.0,
        ge=0.5,
        le=60.0,
        alias="WRITING_MCP_TIMEOUT_SECONDS",
    )

    # ── Limits ───────────────────────────────────────────────────
    max_llm_calls: int = Field(
        default=12,
        ge=1,
        le=12,
        alias="MAX_LLM_CALLS",
    )
    max_mcp_calls: int = Field(
        default=20,
        ge=1,
        le=20,
        alias="MAX_MCP_CALLS",
    )
    run_deadline_seconds: int = Field(
        default=120,
        ge=1,
        le=120,
        alias="RUN_DEADLINE_SECONDS",
    )
    max_review_rounds: int = Field(
        default=2,
        ge=0,
        alias="MAX_REVIEW_ROUNDS",
    )
    checkpoint_retention_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        alias="CHECKPOINT_RETENTION_HOURS",
    )
    checkpoint_path: Path = Field(
        default=_DEFAULT_CHECKPOINT_PATH,
        alias="CHECKPOINT_PATH",
    )

    @field_validator("listing_optimize_mcp_url")
    @classmethod
    def require_secure_rule_endpoint(cls, value: str) -> str:
        """Accept only credential-free HTTPS Streamable HTTP endpoints."""
        endpoint = value.strip()
        if not endpoint:
            return ""
        try:
            parts = urlsplit(endpoint)
            port = parts.port
        except ValueError as error:
            raise PydanticCustomError(
                _UNSAFE_LISTING_OPTIMIZE_ENDPOINT,
                _SECURE_ENDPOINT_REQUIRED,
            ) from error
        query_keys = {
            "".join(character for character in key.casefold() if character.isalnum())
            for key, _value in parse_qsl(parts.query, keep_blank_values=True)
        }
        credential_query = any(
            key in {"apikey", "key", "secretkey"} or key.endswith(("token", "secret", "password"))
            for key in query_keys
        )
        secure = (
            parts.scheme.casefold() == "https"
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and port in {None, 443}
            and not parts.fragment
            and not credential_query
        )
        if not secure:
            raise PydanticCustomError(
                _UNSAFE_LISTING_OPTIMIZE_ENDPOINT,
                _SECURE_ENDPOINT_REQUIRED,
            )
        return endpoint

    @property
    def effective_api_key(self) -> str | None:
        """Return the API key, or None when MOCK=true and key is empty."""
        api_key = self.openai_api_key.get_secret_value()
        if self.mock and not api_key:
            return None
        return api_key or None


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        field = str(error.errors(include_input=False, include_url=False)[0]["loc"][0]).lower()
        raise SystemExit(field) from None


settings = _load_settings()


def apply_runtime_settings(new: Settings) -> Settings:
    """Replace the global settings singleton.

    CLI / Streamlit call this before pipeline runs so consumers see the same
    overrides. Later waves may also patch llm/agent module-level references.
    """
    globals()["settings"] = new
    return new
