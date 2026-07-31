"""Process lifecycle regression tests."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import pytest

from agent_registry import get_agent
from process_manager import AgentStatus, ProcessManager


def test_creation_agent_uses_fastapi_without_legacy_ui() -> None:
    agent = get_agent("listing-creation")
    assert agent is not None
    executable = (
        str(
            Path(__file__).resolve().parents[1]
            / "agents"
            / "listing-creation"
            / ".venv"
            / "Scripts"
            / "uvicorn.exe"
        )
        if os.name == "nt"
        else ".venv/bin/uvicorn"
    )
    assert agent["api_command"][:3] == [
        executable,
        "amazon_create.api:app",
        "--host",
    ]
    assert "legacy_ui_command" not in agent
    assert "web_dir" not in agent
    assert "web_dist" not in agent


def test_incomplete_agent_environment_is_synced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = ProcessManager()
    python = tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    python.parent.mkdir(parents=True)
    python.touch()
    calls: list[tuple[object, ...]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, None]:
            return b"synced", None

    async def fake_subprocess(*command: object, **_kwargs: object) -> FakeProcess:
        calls.append(command)
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    readiness = iter((False, True))

    async def fake_ready(_python: Path, _cwd: Path) -> bool:
        return next(readiness)

    monkeypatch.setattr(manager, "_environment_is_ready", fake_ready)

    asyncio.run(manager._ensure_environment(tmp_path))

    assert calls == [
        (
            "uv",
            "sync",
            "--frozen",
            "--no-dev",
            "--reinstall-package",
            "fastapi",
            "--reinstall-package",
            "uvicorn",
        )
    ]


def test_stop_cleans_port_without_tracked_parent() -> None:
    manager = ProcessManager()
    info = manager.get_status("listing-creation")
    assert info is not None
    info.status = AgentStatus.RUNNING
    calls: list[int] = []

    async def fake_cleanup(port: int) -> None:
        calls.append(port)

    manager._terminate_port_listeners = fake_cleanup  # type: ignore[method-assign]
    result = asyncio.run(manager.stop("listing-creation"))

    assert calls == [8501]
    assert result.status is AgentStatus.STOPPED
    assert result.pid == 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group behavior")
def test_port_cleanup_signals_detached_listener_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ProcessManager()
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(manager, "_listener_pids", lambda _port: (3039,))
    monkeypatch.setattr("process_manager.os.getpgrp", lambda: 100)
    monkeypatch.setattr("process_manager.os.getpgid", lambda _pid: 3036)
    monkeypatch.setattr(
        "process_manager.os.killpg",
        lambda process_group, sig: signals.append((process_group, sig)),
    )

    manager._signal_listener_groups(8502, signal.SIGTERM)

    assert signals == [(3036, signal.SIGTERM)]


def test_status_recovers_running_agent_from_listener_after_manager_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ProcessManager()
    monkeypatch.setattr(
        manager,
        "_listener_pids",
        lambda port: (4153,) if port == 8502 else (),
    )

    statuses = {status["id"]: status for status in manager.get_all_statuses()}

    assert statuses["listing-optimization"]["status"] == "running"
    assert statuses["listing-optimization"]["pid"] == 4153
    assert statuses["listing-optimization"]["url"] == "http://localhost:8502"
