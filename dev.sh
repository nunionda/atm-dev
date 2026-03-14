#!/bin/bash
# ATS 개발 서버 실행 스크립트
# Backend (FastAPI :8000) + Frontend (Vite :5173) 동시 실행

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

cleanup() {
    echo ""
    echo "[dev.sh] Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "[dev.sh] Done."
}
trap cleanup EXIT INT TERM

# Backend
echo "[dev.sh] Starting backend (port 8000)..."
python3 main.py api &
BACKEND_PID=$!

# Frontend
echo "[dev.sh] Starting frontend (port 5173)..."
cd web && npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo "[dev.sh] Backend PID=$BACKEND_PID | Frontend PID=$FRONTEND_PID"
echo "[dev.sh] API: http://localhost:8000 | Web: http://localhost:5173"

wait
