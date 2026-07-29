"""Process lifecycle regression tests."""

from __future__ import annotations

import asyncio

from process_manager import AgentStatus, ProcessManager


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
