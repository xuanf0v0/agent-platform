#!/usr/bin/env bash

# ── Agent Manager — One-Command Start ─────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_PGID=$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')

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

# ── Install backend deps if needed ────────────────────────
echo ""
echo "📦 Checking dependencies..."
cd "$SCRIPT_DIR/backend"
python3 -m pip install -q -r requirements.txt 2>/dev/null || true

# ── Backend (FastAPI :8000) ───────────────────────────────
echo "🚀 Starting backend (API :8000)..."
python3 -m uvicorn main:app --app-dir "$SCRIPT_DIR/backend" --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 1

# ── Frontend (Vite :5173, HMR enabled) ────────────────────
echo ""
echo "🎨 Starting frontend (Vite :5173)..."
cd "$SCRIPT_DIR/frontend"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

# ── Ready ─────────────────────────────────────────────────
sleep 2
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Agent Manager is running!"
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop all services."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Trap Ctrl+C to clean up both processes
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "   All services stopped."
}
trap cleanup EXIT INT TERM

# Wait for either process to exit
wait
