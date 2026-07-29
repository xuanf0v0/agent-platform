"""Agent metadata registry — single source of truth for managed agents."""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

_AGENT_REGISTRY: Final[dict[str, dict]] = {
    "listing-creation": {
        "id": "listing-creation",
        "name": "Listing Creation Agent",
        "name_zh": "Listing 创作 Agent",
        "description": "从 0 到 1 创建 Amazon Listing（Title + Bullets + Search Terms）",
        "description_en": "Create Amazon listings from scratch — Title, Bullets, Search Terms",
        "path": "/Users/ypc/listing-creation-agent",
        "entry": "amazon_create/ui/app.py",
        "default_port": 8501,
        "icon": "✨",
        "venv": ".venv/bin/streamlit",
    },
    "listing-optimization": {
        "id": "listing-optimization",
        "name": "Listing Optimization Agent",
        "name_zh": "Listing 优化 Agent",
        "description": "优化现有 Amazon Listing，自动研究 + 重写 + 后检",
        "description_en": "Optimize existing Amazon listings with research, rewrite, and postflight",
        "path": "/Users/ypc/listing-optimization-agent",
        "entry": "amazon_copy/ui/app.py",
        "default_port": 8502,
        "icon": "🔧",
        "venv": ".venv/bin/streamlit",
    },
}


def get_agent(agent_id: str) -> dict | None:
    """Return agent metadata or None."""
    return _AGENT_REGISTRY.get(agent_id)


def list_agents() -> list[dict]:
    """Return all registered agents."""
    return list(_AGENT_REGISTRY.values())


def agent_ids() -> list[str]:
    """Return all agent ids."""
    return list(_AGENT_REGISTRY.keys())