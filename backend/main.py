"""Agent Platform backend assembled from the reusable agent-harness package."""

from __future__ import annotations

from pathlib import Path

from agent_harness.api import create_app

_ROOT = Path(__file__).resolve().parents[1]

app = create_app(
    _ROOT / "harness-agents",
    state_path=_ROOT / ".tmp" / "harness" / "state.db",
    lock_address="127.0.0.1:8000",
)


@app.get("/api/health")
async def compatibility_health() -> dict[str, str]:
    """Keep the original platform launcher health endpoint compatible."""
    return {"status": "ok"}
