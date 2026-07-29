"""Process manager for packaged React and Python API agents."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from agent_registry import get_agent, list_agents


class AgentStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ProcessInfo:
    agent_id: str
    port: int
    process: asyncio.subprocess.Process | None = None
    status: AgentStatus = AgentStatus.STOPPED
    started_at: float = 0.0
    pid: int = 0
    error_message: str = ""


class ProcessManager:
    """Manage build and API subprocess lifecycle for registered agents."""

    def __init__(self) -> None:
        self._processes: dict[str, ProcessInfo] = {}
        self._log_buffers: dict[str, list[str]] = {}
        self._log_subscribers: dict[str, list[asyncio.Queue]] = {}
        # Initialize process info for all registered agents
        for agent in list_agents():
            aid = agent["id"]
            self._processes[aid] = ProcessInfo(
                agent_id=aid,
                port=agent["default_port"],
            )
            self._log_buffers[aid] = []
            self._log_subscribers[aid] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self, agent_id: str) -> ProcessInfo | None:
        return self._processes.get(agent_id)

    def get_all_statuses(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for agent in list_agents():
            aid = agent["id"]
            info = self._processes.get(aid)
            status = info.status if info else AgentStatus.STOPPED
            result.append(
                {
                    "id": aid,
                    "name": agent["name"],
                    "name_zh": agent["name_zh"],
                    "description": agent["description"],
                    "description_en": agent["description_en"],
                    "icon": agent["icon"],
                    "port": agent["default_port"],
                    "status": status.value,
                    "pid": info.pid if info else 0,
                    "started_at": info.started_at if info else 0,
                    "error_message": info.error_message if info else "",
                    "url": f"http://localhost:{agent['default_port']}" if status == AgentStatus.RUNNING else None,
                }
            )
        return result

    async def start(self, agent_id: str) -> ProcessInfo:
        """Build the React app when needed and start its Python API."""
        agent = get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        info = self._processes[agent_id]
        if info.status == AgentStatus.RUNNING:
            return info

        info.status = AgentStatus.STARTING
        info.error_message = ""

        try:
            cwd = Path(agent["path"])
            port = agent["default_port"]

            await self._ensure_frontend(agent, cwd)

            info.process = await asyncio.create_subprocess_exec(
                *agent["api_command"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd),
                preexec_fn=os.setsid,
            )

            info.pid = info.process.pid or 0
            info.started_at = time.time()
            info.status = AgentStatus.RUNNING

            # Start log reader task
            asyncio.create_task(self._read_logs(agent_id))

        except Exception as exc:
            info.status = AgentStatus.ERROR
            info.error_message = str(exc)

        return info

    async def _ensure_frontend(self, agent: dict[str, Any], cwd: Path) -> None:
        """Install and build one agent frontend if no packaged index exists."""
        if (cwd / agent["web_dist"]).is_file():
            return
        web_dir = cwd / agent["web_dir"]
        for command in (("npm", "install"), ("npm", "run", "build")):
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(web_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            if process.returncode != 0:
                message = output.decode("utf-8", errors="replace")[-2000:]
                raise RuntimeError(f"frontend build failed: {message}")

    async def stop(self, agent_id: str) -> ProcessInfo:
        """Stop a running agent subprocess."""
        agent = get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        info = self._processes[agent_id]
        if info.status != AgentStatus.RUNNING or info.process is None:
            if info.status == AgentStatus.STARTING:
                info.status = AgentStatus.STOPPED
            return info

        try:
            # Send SIGTERM to the process group
            os.killpg(os.getpgid(info.process.pid), signal.SIGTERM)

            try:
                await asyncio.wait_for(info.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                # Force kill if still alive
                os.killpg(os.getpgid(info.process.pid), signal.SIGKILL)
                await info.process.wait()
        except ProcessLookupError:
            pass  # Already dead
        except Exception as exc:
            info.error_message = str(exc)

        info.process = None
        info.pid = 0
        info.status = AgentStatus.STOPPED
        info.started_at = 0

        return info

    def get_logs(self, agent_id: str, tail: int = 200) -> list[str]:
        """Return recent log lines from the buffer."""
        buffer = self._log_buffers.get(agent_id, [])
        return buffer[-tail:] if tail > 0 else buffer

    def subscribe_logs(self, agent_id: str) -> asyncio.Queue:
        """Subscribe to real-time log updates. Returns a queue that receives log lines."""
        queue: asyncio.Queue = asyncio.Queue()
        self._log_subscribers.setdefault(agent_id, []).append(queue)
        return queue

    def unsubscribe_logs(self, agent_id: str, queue: asyncio.Queue) -> None:
        """Remove a log subscriber."""
        subs = self._log_subscribers.get(agent_id, [])
        if queue in subs:
            subs.remove(queue)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _read_logs(self, agent_id: str) -> None:
        """Read stdout lines from the subprocess and broadcast to subscribers."""
        info = self._processes.get(agent_id)
        if info is None or info.process is None or info.process.stdout is None:
            return

        buffer = self._log_buffers.setdefault(agent_id, [])

        try:
            while True:
                line_bytes = await info.process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")

                # Keep buffer bounded
                buffer.append(line)
                if len(buffer) > 2000:
                    del buffer[:1000]

                # Broadcast to subscribers
                subs = self._log_subscribers.get(agent_id, [])
                for q in subs:
                    try:
                        q.put_nowait(line)
                    except asyncio.QueueFull:
                        pass
        except (asyncio.CancelledError, Exception):
            pass

        # Process exited — update status
        if info.status == AgentStatus.RUNNING:
            info.status = AgentStatus.STOPPED
            info.process = None
            info.pid = 0


# Singleton
process_manager = ProcessManager()
