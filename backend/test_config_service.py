from __future__ import annotations

import os
from pathlib import Path

import config_service


def test_update_config_creates_missing_env_from_example(
    monkeypatch,
    tmp_path: Path,
) -> None:
    agent_path = tmp_path / "listing-creation"
    agent_path.mkdir()
    (agent_path / ".env.example").write_text(
        "# Server-side settings\n"
        "OPENAI_API_KEY=\n"
        "OPENAI_API_BASE=https://api.deepseek.com\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        config_service,
        "get_agent",
        lambda agent_id: {"path": str(agent_path)} if agent_id == "listing-creation" else None,
    )

    fields = config_service.update_config(
        "listing-creation",
        {
            "MOCK": "true",
            "OPENAI_API_KEY": "test-secret",
            "WRITER_MODEL": "writer-live",
        },
    )

    env_path = agent_path / ".env"
    content = env_path.read_text(encoding="utf-8")
    assert "# Server-side settings" in content
    assert "OPENAI_API_KEY=test-secret" in content
    assert "WRITER_MODEL=writer-live" in content
    assert "MOCK=" not in content
    if os.name != "nt":
        assert env_path.stat().st_mode & 0o777 == 0o600
    assert all(field["key"] != "MOCK" for field in fields)
