#!/bin/bash
# ═══════════════════════════════════════════════════
# ATS 백엔드 서버 (FastAPI)
# 사용법:
#   ./start-backend.sh          서버 시작
#   ./start-backend.sh stop     서버 종료
#   ./start-backend.sh restart  재시작
#   ./start-backend.sh log      로그 보기
# ═══════════════════════════════════════════════════

cd "$(dirname "$0")"

PORT=8000
PID_FILE=".pids/backend.pid"
LOG_FILE="/tmp/ats_api.log"
mkdir -p .pids

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        kill -0 "$pid" 2>/dev/null && return 0
        rm -f "$PID_FILE"
    fi
    return 1
}

stop_server() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null
        rm -f "$PID_FILE"
        echo -e "${GREEN}[Backend]${NC} 종료됨 (PID: $pid)"
    fi
    # 포트 점유 정리
    local pids
    pids=$(lsof -ti:"$PORT" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

start_server() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo -e "${YELLOW}[Backend]${NC} 이미 실행 중 (PID: $pid, http://localhost:$PORT)"
        return 0
    fi

    # 포트 점유 해제
    local pids
    pids=$(lsof -ti:"$PORT" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}[Backend]${NC} 포트 $PORT 점유 해제 중..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    # 가상환경 활성화
    if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi

    echo -e "${CYAN}[Backend]${NC} FastAPI 서버 시작 중..."
    python3 main.py api > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    # 준비 대기 (최대 15초)
    for i in $(seq 1 15); do
        if curl -s "http://localhost:$PORT/docs" > /dev/null 2>&1; then
            echo -e "${GREEN}[Backend]${NC} ✓ 실행 완료"
            echo -e "  URL:  http://localhost:$PORT"
            echo -e "  Docs: http://localhost:$PORT/docs"
            echo -e "  PID:  $pid"
            echo -e "  Log:  tail -f $LOG_FILE"
            return 0
        fi
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[Backend]${NC} ✓ 시작됨 (PID: $pid) — 데이터 로드 중..."
        echo -e "  Log: tail -f $LOG_FILE"
    else
        echo -e "${RED}[Backend]${NC} ✗ 시작 실패"
        tail -10 "$LOG_FILE" 2>/dev/null
        return 1
    fi
}

case "${1:-start}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 1
        start_server
        ;;
    log|logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "로그 파일 없음: $LOG_FILE"
        fi
        ;;
    status)
        if is_running; then
            local pid
            pid=$(cat "$PID_FILE")
            echo -e "${GREEN}●${NC} Backend 실행 중 (PID: $pid, http://localhost:$PORT)"
        else
            echo -e "${RED}●${NC} Backend 중지됨"
        fi
        ;;
    *)
        echo "사용법: ./start-backend.sh [start|stop|restart|log|status]"
        exit 1
        ;;
esac
