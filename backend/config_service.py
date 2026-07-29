"""Configuration service — read/write agent .env files with secret masking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_registry import get_agent

# Fields that contain secrets — their values are masked in API responses
_SECRET_FIELD_PATTERNS: list[str] = [
    r".*_KEY$",
    r".*_TOKEN$",
    r".*_SECRET$",
]

# Config fields to expose per agent, with display metadata
_COMMON_CONFIG_FIELDS: list[dict[str, Any]] = [
    {"key": "MOCK", "label": "Mock Mode", "type": "boolean", "default": "true"},
    {"key": "OPENAI_API_KEY", "label": "API Key", "type": "secret", "default": ""},
    {"key": "OPENAI_API_BASE", "label": "API Base URL", "type": "string", "default": "https://api.deepseek.com"},
    {"key": "WRITER_MODEL", "label": "Writer Model", "type": "string", "default": "deepseek-v4-flash"},
    {"key": "REVIEW_MODEL", "label": "Review Model", "type": "string", "default": "deepseek-v4-flash"},
]

_OPTIMIZATION_EXTRA_FIELDS: list[dict[str, Any]] = [
    {"key": "VOTE_MODEL", "label": "Vote Model", "type": "string", "default": "deepseek-v4-flash"},
    {"key": "TITLE_MODE", "label": "Title Mode", "type": "select", "options": ["sop_seo", "strict_amazon"], "default": "sop_seo"},
    {"key": "MAX_LLM_CALLS", "label": "Max LLM Calls", "type": "number", "default": "12"},
    {"key": "MAX_MCP_CALLS", "label": "Max MCP Calls", "type": "number", "default": "20"},
]


def _is_secret_field(key: str) -> bool:
    return any(re.match(pattern, key) for pattern in _SECRET_FIELD_PATTERNS)


def _mask_value(value: str) -> str:
    """Mask a secret value: show first 4 and last 4 characters."""
    if not value or len(value) <= 8:
        return "****" if value else ""
    return value[:4] + "*" * 8 + value[-4:]


def _read_env_file(agent_id: str) -> dict[str, str]:
    """Parse the .env file into a dict."""
    agent = get_agent(agent_id)
    if agent is None:
        return {}

    env_path = Path(agent["path"]) / ".env"
    if not env_path.exists():
        return {}

    result: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                result[key] = value
    return result


def _write_env_file(agent_id: str, updates: dict[str, str]) -> None:
    """Update specific keys in the .env file, preserving comments and order."""
    agent = get_agent(agent_id)
    if agent is None:
        raise ValueError(f"Unknown agent: {agent_id}")

    env_path = Path(agent["path"]) / ".env"
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")

    # Read existing lines
    with open(env_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Update matching keys
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append any new keys that weren't in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def get_config(agent_id: str) -> list[dict[str, Any]]:
    """Get agent configuration fields with masked secrets."""
    agent = get_agent(agent_id)
    if agent is None:
        return []

    env_values = _read_env_file(agent_id)

    # Determine which fields to show
    fields = list(_COMMON_CONFIG_FIELDS)
    if agent_id == "listing-optimization":
        fields = list(_COMMON_CONFIG_FIELDS) + _OPTIMIZATION_EXTRA_FIELDS

    result: list[dict[str, Any]] = []
    for field in fields:
        key = field["key"]
        raw_value = env_values.get(key, field.get("default", ""))
        is_secret = _is_secret_field(key) or field.get("type") == "secret"

        result.append(
            {
                **field,
                "value": _mask_value(raw_value) if is_secret else raw_value,
                "is_secret": is_secret,
                "is_masked": is_secret and bool(raw_value),
            }
        )

    return result


def update_config(agent_id: str, updates: dict[str, str]) -> list[dict[str, Any]]:
    """Update agent configuration. Skip masked (unchanged) secret values."""
    env_values = _read_env_file(agent_id)

    # For secret fields whose value is still masked, keep the original
    cleaned: dict[str, str] = {}
    for key, value in updates.items():
        if _is_secret_field(key) and ("*" in value or value == "****"):
            # Value wasn't changed — keep original
            if key in env_values:
                cleaned[key] = env_values[key]
            continue
        cleaned[key] = value

    _write_env_file(agent_id, cleaned)
    return get_config(agent_id)