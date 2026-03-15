#!/bin/bash
# ATS 개발 서버 실행 스크립트
# Backend (FastAPI :8000) + Frontend (Vite :5173) 동시 실행
# 기존 서버 자동 정리 후 재시작

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 기존 프로세스 정리 ──
echo "[dev.sh] Cleaning up existing servers..."

if lsof -ti:8000 >/dev/null 2>&1; then
    echo "[dev.sh] Killing existing backend (port 8000)..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

if lsof -ti:5173 >/dev/null 2>&1; then
    echo "[dev.sh] Killing existing frontend (port 5173)..."
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    sleep 1
fi

echo "[dev.sh] Ports cleared."

# ── 종료 시 정리 ──
cleanup() {
    echo ""
    echo "[dev.sh] Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "[dev.sh] Done."
}
trap cleanup EXIT INT TERM

# ── Backend 시작 ──
echo "[dev.sh] Starting backend (port 8000)..."
python3 main.py api &
BACKEND_PID=$!

# ── Frontend 시작 ──
echo "[dev.sh] Starting frontend (port 5173)..."
cd web && npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo "══════════════════════════════════════════"
echo "  ATS Dev Server Running"
echo "  API:  http://localhost:8000"
echo "  Web:  http://localhost:5173"
echo "  PID:  backend=$BACKEND_PID  frontend=$FRONTEND_PID"
echo "  Press Ctrl+C to stop"
echo "══════════════════════════════════════════"
echo ""

wait
