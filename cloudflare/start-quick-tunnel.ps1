param(
    [string]$Origin = "http://127.0.0.1:5173",
    [string]$Proxy = "",
    [string]$UrlFile = "",
    [string]$ErrorFile = ""
)

$ErrorActionPreference = "Stop"

function Set-TunnelError([string]$Message) {
    if ($ErrorFile) {
        $Message | Set-Content -LiteralPath $ErrorFile -Encoding UTF8
    }
    [Console]::Error.WriteLine($Message)
}

if ($UrlFile) {
    Remove-Item -LiteralPath $UrlFile -Force -ErrorAction SilentlyContinue
}
if ($ErrorFile) {
    Remove-Item -LiteralPath $ErrorFile -Force -ErrorAction SilentlyContinue
}

if (-not $Proxy) {
    $internetSettings = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
    if ($internetSettings.ProxyEnable -eq 1 -and $internetSettings.ProxyServer) {
        $Proxy = [string]$internetSettings.ProxyServer
    }
}

if ($Proxy) {
    if ($Proxy -notmatch "^https?://") { $Proxy = "http://$Proxy" }
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
    Write-Host "Using proxy: $Proxy"
}

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($null -ne $cloudflared) {
    $cloudflaredPath = $cloudflared.Source
} else {
    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $cloudflaredPath = Get-ChildItem -LiteralPath $packageRoot -Filter cloudflared.exe -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $cloudflaredPath) {
    throw "cloudflared was not found. Run: winget install Cloudflare.cloudflared"
}

# cloudflared's account-less tunnel bootstrap does not consistently honor the
# Windows system proxy. Always bootstrap through curl so startup has a bounded
# timeout and can publish the URL through a deterministic status file.
$curlArguments = @("-sS", "-X", "POST", "--connect-timeout", "8", "--max-time", "20")
if ($Proxy) { $curlArguments += @("-x", $Proxy) }
$curlArguments += "https://api.trycloudflare.com/tunnel"
$savedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$responseJson = & curl.exe @curlArguments 2>&1
$curlExitCode = $LASTEXITCODE
$ErrorActionPreference = $savedErrorActionPreference
if ($curlExitCode -ne 0) {
    Set-TunnelError "Unable to create a Cloudflare Quick Tunnel: $responseJson"
    exit 1
}
try {
    $response = $responseJson | ConvertFrom-Json
} catch {
    Set-TunnelError "Cloudflare returned an invalid response: $responseJson"
    exit 1
}
if (-not $response.success) {
    Set-TunnelError "Cloudflare rejected the Quick Tunnel request."
    exit 1
}

$credentialsPath = Join-Path ([IO.Path]::GetTempPath()) ("cloudflared-quick-{0}.json" -f [guid]::NewGuid())
$credentials = [ordered]@{
    AccountTag = $response.result.account_tag
    TunnelSecret = $response.result.secret
    TunnelID = $response.result.id
}
$credentials | ConvertTo-Json -Compress | Set-Content -LiteralPath $credentialsPath -Encoding Ascii

$publicUrl = "https://$($response.result.hostname)"
if ($UrlFile) { $publicUrl | Set-Content -LiteralPath $UrlFile -Encoding Ascii }
Write-Host "Quick Tunnel: $publicUrl"
try {
    & $cloudflaredPath tunnel --no-autoupdate --protocol http2 --url $Origin --credentials-file $credentialsPath run $response.result.id
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Set-TunnelError "cloudflared exited with code $exitCode."
    }
    exit $exitCode
} finally {
    Remove-Item -LiteralPath $credentialsPath -Force -ErrorAction SilentlyContinue
}
