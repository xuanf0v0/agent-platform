# Agent Platform

The platform backend is powered by the reusable
[`agent-harness`](https://github.com/xuanf0v0/my-harness). Agent definitions live
under `harness-agents/`; the Amazon business packages remain isolated under
`agents/`.

Harness now owns environment setup, process lifecycle, health checks, logs,
configuration and service proxying. The management API remains on port 8000,
while the business services use ports 8501, 8502 and 8503.

Useful backend operations:

```bash
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/api/agents
curl -X POST http://127.0.0.1:8000/api/agents/listing-creation/setup
curl -X POST http://127.0.0.1:8000/api/agents/listing-creation/start
```

## Windows / PowerShell

PowerShell does not need the backend virtual environment to be activated. From
the repository root:

```powershell
# Foreground
.\start.ps1

# Background
.\start.ps1 -Background

# Background with a Cloudflare Quick Tunnel
.\start.ps1 -Tunnel -Background

# Check local and tunnel status
.\start.ps1 -Status

# Stop the platform and managed agent listeners
.\start.ps1 -Stop
```

If the network requires an HTTP proxy, pass it explicitly:

```powershell
.\start.ps1 -Tunnel -Background -Proxy http://127.0.0.1:7890
```

Tunnel startup waits up to 12 seconds for a URL or a concrete error. Adjust or
disable that foreground wait without changing the background process:

```powershell
.\start.ps1 -Tunnel -Background -TunnelWaitSeconds 30
.\start.ps1 -Tunnel -Background -TunnelWaitSeconds 0
```

Runtime state and logs are written under `.tmp/runtime/`.

## macOS / Linux

```bash
bash start.sh
bash start.sh --tunnel
```
