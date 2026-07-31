#!/usr/bin/env bash

# Start a Cloudflare Quick Tunnel on macOS or Linux. When a system HTTP proxy
# is configured, bootstrap through curl because cloudflared does not always
# inherit the desktop proxy configuration during Quick Tunnel creation.

set -euo pipefail

ORIGIN="${1:-http://127.0.0.1:5173}"

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "cloudflared is required. macOS: brew install cloudflared" >&2
    exit 1
fi

PROXY_URL="${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}"

if [[ -z "$PROXY_URL" && "$(uname -s)" == "Darwin" ]] && command -v scutil >/dev/null 2>&1; then
    PROXY_HOST=$(scutil --proxy | awk '/HTTPProxy :/ {print $3; exit}')
    PROXY_PORT=$(scutil --proxy | awk '/HTTPPort :/ {print $3; exit}')
    if [[ -n "$PROXY_HOST" && -n "$PROXY_PORT" ]]; then
        PROXY_URL="http://$PROXY_HOST:$PROXY_PORT"
    fi
fi

if [[ -z "$PROXY_URL" ]]; then
    exec cloudflared tunnel --no-autoupdate --protocol http2 --url "$ORIGIN"
fi

if [[ ! "$PROXY_URL" =~ ^https?:// ]]; then
    PROXY_URL="http://$PROXY_URL"
fi
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"

QUICK_TUNNEL_JSON=$(curl --fail --silent --show-error --proxy "$PROXY_URL" --request POST --max-time 30 https://api.trycloudflare.com/tunnel)
HOSTNAME=$(python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if not payload.get("success"):
    raise SystemExit("Cloudflare rejected the Quick Tunnel request")
result = payload["result"]
print(result["hostname"])
' <<< "$QUICK_TUNNEL_JSON")
TUNNEL_ID=$(python3 -c '
import json
import sys
print(json.load(sys.stdin)["result"]["id"])
' <<< "$QUICK_TUNNEL_JSON")
CREDENTIALS=$(python3 -c '
import json
import sys

result = json.load(sys.stdin)["result"]
print(json.dumps({"AccountTag": result["account_tag"], "TunnelSecret": result["secret"], "TunnelID": result["id"]}))
' <<< "$QUICK_TUNNEL_JSON")
CREDENTIALS_FILE=$(mktemp "${TMPDIR:-/tmp}/cloudflared-quick.XXXXXX")
chmod 600 "$CREDENTIALS_FILE"
trap 'rm -f "$CREDENTIALS_FILE"' EXIT INT TERM
printf '%s' "$CREDENTIALS" > "$CREDENTIALS_FILE"

echo "Quick Tunnel: https://$HOSTNAME"
cloudflared tunnel --no-autoupdate --protocol http2 --url "$ORIGIN" --credentials-file "$CREDENTIALS_FILE" run "$TUNNEL_ID"
