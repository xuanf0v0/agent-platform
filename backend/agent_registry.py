"""Agent metadata registry — single source of truth for managed agents."""

from __future__ import annotations

from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------

_ROOT: Final = Path(__file__).resolve().parents[1]

_AGENT_REGISTRY: Final[dict[str, dict]] = {
    "listing-creation": {
        "id": "listing-creation",
        "name": "Listing Creation Agent",
        "name_zh": "Listing 创作 Agent",
        "description": "完整创建 Amazon Listing，含研究、合规、A+、类目与图片规划",
        "description_en": "Create researched, compliant Amazon listings with A+, category, and image plans",
        "path": str(_ROOT / "agents" / "listing-creation"),
        "default_port": 8501,
        "icon": "✨",
        "api_command": ["uv", "run", "amz-create-api", "--port", "8501"],
        "web_dir": "web",
        "web_dist": "amazon_create/web_dist/index.html",
    },
    "listing-optimization": {
        "id": "listing-optimization",
        "name": "Listing Optimization Agent",
        "name_zh": "Listing 优化 Agent",
        "description": "优化现有 Amazon Listing，自动研究 + 重写 + 后检",
        "description_en": "Optimize existing Amazon listings with research, rewrite, and postflight",
        "path": str(_ROOT / "agents" / "listing-optimization"),
        "default_port": 8502,
        "icon": "🔧",
        "api_command": [
            ".venv/bin/streamlit",
            "run",
            "amazon_copy/ui/app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "8502",
            "--server.headless",
            "true",
        ],
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
