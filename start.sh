#!/usr/bin/env bash

# ── Agent Manager — One-Command Start ─────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_PGID=$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')
WITH_TUNNEL=false
BACKEND_PID=""
FRONTEND_PID=""
TUNNEL_PID=""

if [[ "${1:-}" == "--tunnel" ]]; then
    WITH_TUNNEL=true
elif [[ $# -gt 0 ]]; then
    echo "Usage: bash start.sh [--tunnel]"
    exit 2
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🤖 Agent Manager"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Kill old processes on both ports ──────────────────────
for PORT in 8000 5173 8501 8502; do
    OLD_PIDS=$(lsof -tiTCP:$PORT -sTCP:LISTEN 2>/dev/null)
    for OLD_PID in $OLD_PIDS; do
        OLD_PGID=$(ps -o pgid= -p "$OLD_PID" 2>/dev/null | tr -d ' ')
        if [ -n "$OLD_PGID" ] && [ "$OLD_PGID" != "$CURRENT_PGID" ]; then
            echo "🔪 端口 $PORT 被占用 (PID: $OLD_PID, PGID: $OLD_PGID)，自动释放..."
            kill -TERM -- "-$OLD_PGID" 2>/dev/null || true
            sleep 0.2
            kill -KILL -- "-$OLD_PGID" 2>/dev/null || true
        else
            echo "🔪 端口 $PORT 被占用 (PID: $OLD_PID)，自动释放..."
            kill -TERM "$OLD_PID" 2>/dev/null || true
            sleep 0.2
            kill -KILL "$OLD_PID" 2>/dev/null || true
        fi
    done
done

# ── Isolated backend dependencies ─────────────────────────
BACKEND_DIR="$SCRIPT_DIR/backend"
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
echo ""
BACKEND_READY=false
if [[ -x "$BACKEND_PYTHON" ]] && "$BACKEND_PYTHON" -m pip --version >/dev/null 2>&1; then
    BACKEND_READY=true
fi
if [[ "$BACKEND_READY" != true ]]; then
    if [[ -d "$BACKEND_DIR/.venv" ]]; then
        echo "📦 Recreating incomplete backend environment..."
        rm -rf "$BACKEND_DIR/.venv"
    fi
    echo "📦 Creating isolated backend environment..."
    python3 -m venv "$BACKEND_DIR/.venv"
else
    echo "📦 Using isolated backend environment..."
fi
echo "📦 Checking backend dependencies..."
"$BACKEND_PYTHON" -m pip install -q -r "$BACKEND_DIR/requirements.txt"

# ── Frontend dependencies ─────────────────────────────────
if [[ ! -d "$SCRIPT_DIR/frontend/node_modules" ]]; then
    echo "📦 Installing frontend dependencies..."
    (
        cd "$SCRIPT_DIR/frontend"
        npm ci
    )
fi

# ── Backend (FastAPI :8000) ───────────────────────────────
echo "🚀 Starting backend (API :8000)..."
"$BACKEND_PYTHON" -m uvicorn main:app --app-dir "$SCRIPT_DIR/backend" --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 1

# ── Frontend (Vite :5173, HMR enabled) ────────────────────
echo ""
echo "🎨 Starting frontend (Vite :5173)..."
node "$SCRIPT_DIR/frontend/node_modules/vite/bin/vite.js" --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

# ── Optional Cloudflare Quick Tunnel ───────────────────────
if [[ "$WITH_TUNNEL" == true ]]; then
    echo ""
    echo "☁️  Starting Cloudflare Quick Tunnel..."
    bash "$SCRIPT_DIR/cloudflare/start-quick-tunnel.sh" &
    TUNNEL_PID=$!
fi

# ── Ready ─────────────────────────────────────────────────
sleep 2
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Agent Manager is running!"
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
if [[ "$WITH_TUNNEL" == true ]]; then
    echo "  Cloudflare: URL will appear above shortly"
fi
echo ""
echo "  Press Ctrl+C to stop all services."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Trap Ctrl+C to clean up both processes
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    [[ -n "$TUNNEL_PID" ]] && kill "$TUNNEL_PID" 2>/dev/null || true
    [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    echo "   All services stopped."
}
trap cleanup EXIT INT TERM

# Wait for all launched services. Ctrl+C triggers cleanup.
wait
