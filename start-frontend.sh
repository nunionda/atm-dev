#!/bin/bash
# ═══════════════════════════════════════════════════
# ATS 프론트엔드 서버 (Vite + React)
# 사용법:
#   ./start-frontend.sh          서버 시작
#   ./start-frontend.sh stop     서버 종료
#   ./start-frontend.sh restart  재시작
#   ./start-frontend.sh log      로그 보기
#   ./start-frontend.sh build    프로덕션 빌드
#   ./start-frontend.sh check    TypeScript 타입 체크
# ═══════════════════════════════════════════════════

cd "$(dirname "$0")"

PORT=5173
PID_FILE=".pids/frontend.pid"
LOG_FILE="/tmp/ats_vite.log"
WEB_DIR="web"
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
        echo -e "${GREEN}[Frontend]${NC} 종료됨 (PID: $pid)"
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
        echo -e "${YELLOW}[Frontend]${NC} 이미 실행 중 (PID: $pid, http://localhost:$PORT)"
        return 0
    fi

    # 포트 점유 해제
    local pids
    pids=$(lsof -ti:"$PORT" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}[Frontend]${NC} 포트 $PORT 점유 해제 중..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    # node_modules 확인
    if [ ! -d "$WEB_DIR/node_modules" ]; then
        echo -e "${CYAN}[Frontend]${NC} npm install 실행 중..."
        (cd "$WEB_DIR" && npm install)
    fi

    echo -e "${CYAN}[Frontend]${NC} Vite 개발 서버 시작 중..."
    (cd "$WEB_DIR" && npm run dev) > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    # 준비 대기 (최대 10초)
    for i in $(seq 1 10); do
        if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
            echo -e "${GREEN}[Frontend]${NC} ✓ 실행 완료"
            echo -e "  URL: http://localhost:$PORT"
            echo -e "  PID: $pid"
            echo -e "  Log: tail -f $LOG_FILE"
            return 0
        fi
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[Frontend]${NC} ✓ 시작됨 (PID: $pid)"
        echo -e "  Log: tail -f $LOG_FILE"
    else
        echo -e "${RED}[Frontend]${NC} ✗ 시작 실패"
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
            echo -e "${GREEN}●${NC} Frontend 실행 중 (PID: $pid, http://localhost:$PORT)"
        else
            echo -e "${RED}●${NC} Frontend 중지됨"
        fi
        ;;
    build)
        echo -e "${CYAN}[Frontend]${NC} 프로덕션 빌드 중..."
        (cd "$WEB_DIR" && npm run build)
        echo -e "${GREEN}[Frontend]${NC} ✓ 빌드 완료 → $WEB_DIR/dist/"
        ;;
    check|typecheck)
        echo -e "${CYAN}[Frontend]${NC} TypeScript 타입 체크..."
        (cd "$WEB_DIR" && npx tsc --noEmit)
        echo -e "${GREEN}[Frontend]${NC} ✓ 타입 체크 통과"
        ;;
    *)
        echo "사용법: ./start-frontend.sh [start|stop|restart|log|status|build|check]"
        exit 1
        ;;
esac
