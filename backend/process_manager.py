"""Process manager for packaged local agents."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
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

    def reconcile_status(self, agent_id: str) -> ProcessInfo | None:
        """Refresh one agent from its actual listening port."""
        info = self._processes.get(agent_id)
        if info is not None:
            self._reconcile_listener_status(info)
        return info

    def get_all_statuses(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for agent in list_agents():
            aid = agent["id"]
            info = self._processes.get(aid)
            if info is not None:
                self._reconcile_listener_status(info)
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
        """Prepare the agent environment and start its API process."""
        agent = get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        info = self._processes[agent_id]
        self._reconcile_listener_status(info)
        if info.status == AgentStatus.RUNNING:
            return info

        info.status = AgentStatus.STARTING
        info.error_message = ""

        try:
            cwd = Path(agent["path"])
            port = agent["default_port"]

            await self._ensure_environment(cwd)
            await self._ensure_frontend(agent, cwd)

            group_options: dict[str, Any]
            if os.name == "nt":
                group_options = {
                    "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
                }
            else:
                group_options = {"preexec_fn": os.setsid}

            info.process = await asyncio.create_subprocess_exec(
                *agent["api_command"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd),
                **group_options,
            )

            info.pid = info.process.pid or 0
            info.started_at = time.time()
            # Drain stdout immediately. Waiting until after readiness can hide the
            # import error that caused startup to fail (and can fill the pipe).
            asyncio.create_task(self._read_logs(agent_id))
            await self._wait_until_listening(info)
            info.status = AgentStatus.RUNNING

        except Exception as exc:
            info.status = AgentStatus.ERROR
            info.error_message = str(exc)
            if info.process is not None and info.process.returncode is None:
                await self._terminate_tracked_process(info.process)
            info.process = None
            info.pid = 0
            info.started_at = 0

        return info

    async def _wait_until_listening(self, info: ProcessInfo) -> None:
        """Do not report RUNNING before the Agent API accepts connections."""
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if info.process is not None and info.process.returncode is not None:
                raise RuntimeError(f"agent process exited with code {info.process.returncode}")
            try:
                _reader, writer = await asyncio.open_connection("127.0.0.1", info.port)
            except OSError:
                await asyncio.sleep(0.15)
                continue
            writer.close()
            await writer.wait_closed()
            return
        raise RuntimeError(f"agent API did not become ready on port {info.port}")

    @staticmethod
    def _venv_python(cwd: Path) -> Path:
        if os.name == "nt":
            return cwd / ".venv" / "Scripts" / "python.exe"
        return cwd / ".venv" / "bin" / "python"

    async def _ensure_environment(self, cwd: Path) -> None:
        """Repair a missing or partial agent venv from its locked project."""
        python = self._venv_python(cwd)
        if await self._environment_is_ready(python, cwd):
            return

        try:
            process = await asyncio.create_subprocess_exec(
                "uv",
                "sync",
                "--frozen",
                "--no-dev",
                "--reinstall-package",
                "fastapi",
                "--reinstall-package",
                "uvicorn",
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "agent environment is incomplete and 'uv' is not installed"
            ) from exc
        output, _ = await process.communicate()
        if process.returncode != 0:
            message = output.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"agent environment sync failed: {message}")
        if not await self._environment_is_ready(python, cwd):
            raise RuntimeError("agent environment is still incomplete after sync")

    @staticmethod
    async def _environment_is_ready(python: Path, cwd: Path) -> bool:
        if not python.is_file():
            return False
        check = await asyncio.create_subprocess_exec(
            str(python),
            "-c",
            "import fastapi, uvicorn",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(cwd),
        )
        return await check.wait() == 0

    def _reconcile_listener_status(self, info: ProcessInfo) -> None:
        """Recover lifecycle state after the manager process restarts."""
        listener_pids = self._listener_pids(info.port)
        if listener_pids:
            if info.status is not AgentStatus.STARTING:
                info.status = AgentStatus.RUNNING
            if info.pid == 0:
                info.pid = listener_pids[0]
            return
        if info.status is AgentStatus.RUNNING:
            info.status = AgentStatus.STOPPED
            info.process = None
            info.pid = 0
            info.started_at = 0

    async def _ensure_frontend(self, agent: dict[str, Any], cwd: Path) -> None:
        """Install and build one agent frontend if no packaged index exists."""
        if not agent.get("web_dir") or not agent.get("web_dist"):
            return
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
        process = info.process
        info.status = AgentStatus.STOPPED
        info.process = None
        info.pid = 0
        info.started_at = 0
        info.error_message = ""
        try:
            if process is not None:
                await self._terminate_tracked_process(process)
            await self._terminate_port_listeners(info.port)
        except Exception as exc:
            info.error_message = str(exc)

        return info

    async def _terminate_tracked_process(self, process: asyncio.subprocess.Process) -> None:
        """Terminate the complete process group created for one managed agent."""
        if os.name == "nt":
            await self._taskkill(process.pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            return

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                return
            await process.wait()

    async def _terminate_port_listeners(self, port: int) -> None:
        """Stop stale or detached processes that still listen on an agent port."""
        if os.name == "nt":
            for process_id in self._listener_pids(port):
                await self._taskkill(process_id)
            return
        self._signal_listener_groups(port, signal.SIGTERM)
        await asyncio.sleep(0.2)
        self._signal_listener_groups(port, signal.SIGKILL)

    def _signal_listener_groups(self, port: int, sig: signal.Signals) -> None:
        """Signal complete process groups for every detached port listener."""
        own_group = os.getpgrp()
        signaled_groups: set[int] = set()
        for pid in self._listener_pids(port):
            try:
                process_group = os.getpgid(pid)
            except ProcessLookupError:
                continue
            if process_group == own_group or process_group in signaled_groups:
                continue
            try:
                os.killpg(process_group, sig)
                signaled_groups.add(process_group)
            except ProcessLookupError:
                continue

    @staticmethod
    async def _taskkill(process_id: int) -> None:
        """Terminate a Windows process tree without opening a console window."""
        process = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process_id),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await process.wait()

    @staticmethod
    def _listener_pids(port: int) -> tuple[int, ...]:
        """Return PIDs currently listening on a TCP port using the host lsof."""
        if os.name == "nt":
            result = subprocess.run(  # noqa: S603
                ["netstat", "-ano", "-p", "TCP"],
                check=False,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            process_ids: set[int] = set()
            for line in result.stdout.splitlines():
                columns = line.split()
                if (
                    len(columns) == 5
                    and columns[0].upper() == "TCP"
                    and columns[1].rsplit(":", 1)[-1] == str(port)
                    and columns[3].upper() == "LISTENING"
                    and columns[4].isdigit()
                ):
                    process_ids.add(int(columns[4]))
            return tuple(sorted(process_ids))

        result = subprocess.run(  # noqa: S603
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
        )
        return tuple(
            int(line)
            for line in result.stdout.splitlines()
            if line.strip().isdigit()
        )

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
