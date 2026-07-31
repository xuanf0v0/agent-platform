param(
    [switch]$Tunnel,
    [string]$Hostname = "",
    [string]$Proxy = "",
    [switch]$Background,
    [switch]$BackgroundWorker,
    [switch]$Status,
    [switch]$Stop,
    [ValidateRange(0, 120)]
    [int]$TunnelWaitSeconds = 12
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$Processes = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
$PowerShellExecutable = (Get-Process -Id $PID).Path

if (($Status -and $Stop) -or ($BackgroundWorker -and ($Status -or $Stop))) {
    throw "Use only one lifecycle action: -Status, -Stop, or start options."
}

function Stop-PlatformProcessTree([int]$ProcessId) {
    if ($ProcessId -eq $PID) { return }
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
}

function Get-PlatformLaunchers {
    $scriptPathPattern = [regex]::Escape((Join-Path $ProjectRoot "start.ps1"))
    return Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @("powershell.exe", "pwsh.exe") -and
        $_.ProcessId -ne $PID -and
        $_.CommandLine -match $scriptPathPattern -and
        $_.CommandLine -match "(^|\s)-BackgroundWorker(\s|$)"
    }
}

if ($Stop) {
    $stopped = $false
    foreach ($launcher in @(Get-PlatformLaunchers)) {
        Write-Host "Stopping platform launcher (PID $($launcher.ProcessId))..."
        Stop-PlatformProcessTree $launcher.ProcessId
        $stopped = $true
    }
    foreach ($portNumber in 8000, 5173, 8501, 8502, 20241) {
        foreach ($listener in @(Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue)) {
            Write-Host "Stopping listener on port $portNumber (PID $($listener.OwningProcess))..."
            Stop-PlatformProcessTree $listener.OwningProcess
            $stopped = $true
        }
    }
    if ($stopped) { Write-Host "Agent Platform stopped." } else { Write-Host "Agent Platform is already stopped." }
    exit 0
}

if ($Status) {
    $runtimeDir = Join-Path $ProjectRoot ".tmp\runtime"
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        Write-Host "Platform: running (http://localhost:5173)"
    } catch {
        Write-Host "Platform: stopped or unhealthy"
    }
    $tunnelUrlFile = Join-Path $runtimeDir "tunnel.url"
    $tunnelErrorFile = Join-Path $runtimeDir "tunnel.err"
    if (Test-Path $tunnelUrlFile) {
        Write-Host "Public:   $((Get-Content -LiteralPath $tunnelUrlFile -Raw).Trim())"
    } elseif (Test-Path $tunnelErrorFile) {
        Write-Host "Tunnel:   failed"
        Write-Host "Reason:   $((Get-Content -LiteralPath $tunnelErrorFile -Raw).Trim())"
    } else {
        Write-Host "Tunnel:   not started or still connecting"
    }
    exit 0
}

if ($Background -and -not $BackgroundWorker) {
    $runtimeDir = Join-Path $ProjectRoot ".tmp\runtime"
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    $platformLog = Join-Path $runtimeDir "platform.log"
    $platformErrorLog = Join-Path $runtimeDir "platform.err.log"
    $tunnelUrlFile = Join-Path $runtimeDir "tunnel.url"
    $tunnelErrorFile = Join-Path $runtimeDir "tunnel.err"
    Remove-Item -LiteralPath $tunnelUrlFile, $tunnelErrorFile -Force -ErrorAction SilentlyContinue
    $workerArguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $MyInvocation.MyCommand.Path, "-BackgroundWorker"
    )
    if ($Tunnel) { $workerArguments += "-Tunnel" }
    if ($Hostname) { $workerArguments += @("-Hostname", $Hostname) }
    if ($Proxy) { $workerArguments += @("-Proxy", $Proxy) }
    $backgroundProcess = Start-Process $PowerShellExecutable -ArgumentList $workerArguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $platformLog -RedirectStandardError $platformErrorLog -WindowStyle Hidden -PassThru
    Write-Host "Agent Platform started in background (PID $($backgroundProcess.Id))."
    Write-Host "Local:  http://localhost:5173"
    Write-Host "API:    http://localhost:8000"
    if ($Tunnel) {
        Write-Host "Tunnel: waiting briefly for an address..."
        $tunnelDeadline = (Get-Date).AddSeconds($TunnelWaitSeconds)
        while ((Get-Date) -lt $tunnelDeadline) {
            if (Test-Path $tunnelUrlFile) { break }
            if (Test-Path $tunnelErrorFile) { break }
            if ($backgroundProcess.HasExited) { break }
            Start-Sleep -Milliseconds 200
        }
        if (Test-Path $tunnelUrlFile) {
            $tunnelAddress = (Get-Content -LiteralPath $tunnelUrlFile -Raw).Trim()
            Write-Host "Public: $tunnelAddress"
        } elseif (Test-Path $tunnelErrorFile) {
            $tunnelFailure = (Get-Content -LiteralPath $tunnelErrorFile -Raw).Trim()
            Write-Warning "Tunnel failed: $tunnelFailure"
        } else {
            Write-Host "Tunnel: still connecting in the background"
            Write-Host "Status: .\start.ps1 -Status"
        }
    }
    Write-Host "Logs:   $platformLog"
    exit 0
}

function Stop-PreviousPlatformLaunchers {
    foreach ($launcher in @(Get-PlatformLaunchers)) {
        Write-Host "Stopping previous platform launcher (PID $($launcher.ProcessId))..."
        Stop-PlatformProcessTree $launcher.ProcessId
    }
}

function Stop-PlatformListeners {
    $platformPorts = 8000, 5173, 8501, 8502, 20241
    foreach ($portNumber in $platformPorts) {
        $listeners = Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $ownedProcessId = $listener.OwningProcess
            if ($ownedProcessId -eq $PID) { continue }
            Write-Host "Releasing port $portNumber (PID $ownedProcessId)..."
            Stop-PlatformProcessTree $ownedProcessId
        }
    }
}

function Start-PlatformTunnel {
    if (-not $Tunnel) { return }

    Write-Host "Starting Cloudflare Quick Tunnel..."
    $tunnelScript = Join-Path $ProjectRoot "cloudflare\start-quick-tunnel.ps1"
    $runtimeDir = Join-Path $ProjectRoot ".tmp\runtime"
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    $tunnelUrlFile = Join-Path $runtimeDir "tunnel.url"
    $tunnelErrorFile = Join-Path $runtimeDir "tunnel.err"
    $tunnelArguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $tunnelScript,
        "-UrlFile", $tunnelUrlFile, "-ErrorFile", $tunnelErrorFile
    )
    if ($Proxy) { $tunnelArguments += @("-Proxy", $Proxy) }
    $tunnelProcess = Start-Process $PowerShellExecutable -ArgumentList $tunnelArguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $Processes.Add($tunnelProcess)
}

try {
    Stop-PreviousPlatformLaunchers
    Stop-PlatformListeners
    # Tunnel bootstrap runs in parallel with dependency checks and local startup,
    # so the foreground launcher can report its final URL/error without racing.
    Start-PlatformTunnel

    $BackendVenv = Join-Path $BackendDir ".venv"
    $BackendPython = Join-Path $BackendVenv "Scripts\python.exe"
    $BackendReady = Test-Path $BackendPython
    if ($BackendReady) {
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $BackendPython -m pip --version *> $null
        $BackendReady = $LASTEXITCODE -eq 0
        $ErrorActionPreference = $savedErrorActionPreference
    }
    if (-not $BackendReady) {
        if (Test-Path $BackendVenv) {
            Write-Host "Recreating incomplete backend environment..."
            Remove-Item -LiteralPath $BackendVenv -Recurse -Force
        }
        Write-Host "Creating isolated backend environment..."
        & python -m venv $BackendVenv
    }
    Write-Host "Checking backend dependencies..."
    & $BackendPython -m pip install -q -r (Join-Path $BackendDir "requirements.txt")

    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies..."
        Push-Location $FrontendDir
        try { & npm.cmd ci } finally { Pop-Location }
    }

    if ($Hostname) { $env:CLOUDFLARE_HOSTNAME = $Hostname }

    Write-Host "Starting FastAPI on http://localhost:8000 ..."
    $backend = Start-Process $BackendPython -ArgumentList @(
        "-m", "uvicorn", "main:app", "--app-dir", $BackendDir,
        "--host", "0.0.0.0", "--port", "8000"
    ) -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru
    $Processes.Add($backend)

    Write-Host "Starting Vite on http://localhost:5173 ..."
    $viteScript = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"
    $frontend = Start-Process node -ArgumentList @(
        $viteScript, "--host", "0.0.0.0", "--port", "5173"
    ) -WorkingDirectory $FrontendDir -NoNewWindow -PassThru
    $Processes.Add($frontend)

    Start-Sleep -Seconds 2
    Write-Host "Agent Platform is running: http://localhost:5173"

    Write-Host "Press Ctrl+C to stop all services."
    while ($true) { Start-Sleep -Seconds 1 }
}
finally {
    Write-Host "Stopping services..."
    foreach ($process in $Processes) {
        if (-not $process.HasExited) {
            Stop-PlatformProcessTree $process.Id
        }
    }
}
