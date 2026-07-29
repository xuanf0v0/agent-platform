"""Process lifecycle regression tests."""

from __future__ import annotations

import asyncio
import signal

import pytest

from agent_registry import get_agent
from process_manager import AgentStatus, ProcessManager


def test_creation_agent_uses_streamlit_without_react_build() -> None:
    agent = get_agent("listing-creation")
    assert agent is not None
    assert agent["api_command"][:3] == [
        ".venv/bin/streamlit",
        "run",
        "amazon_create/ui/app.py",
    ]
    assert "web_dir" not in agent
    assert "web_dist" not in agent


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
