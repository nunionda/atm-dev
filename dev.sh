#!/bin/bash
# ═══════════════════════════════════════════════════
# ATS 개발 서버 실행 스크립트
# 사용법:
#   ./dev.sh          백엔드 + 프론트엔드 동시 시작
#   ./dev.sh api      백엔드만 시작
#   ./dev.sh web      프론트엔드만 시작
#   ./dev.sh stop     모든 서버 종료
#   ./dev.sh status   서버 상태 확인
# ═══════════════════════════════════════════════════

set -e

# 프로젝트 루트로 이동 (main.py가 있는 디렉토리)
cd "$(dirname "$0")"

BACKEND_PORT=8000
FRONTEND_PORT=5173
PID_DIR=".pids"
mkdir -p "$PID_DIR"

# ── 색상 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 유틸리티 함수 ──

is_port_in_use() {
    lsof -ti:"$1" > /dev/null 2>&1
}

kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}  포트 $port 점유 프로세스 종료 중...${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

check_pid_alive() {
    local pidfile="$PID_DIR/$1.pid"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            return 0  # alive
        fi
        rm -f "$pidfile"
    fi
    return 1  # not alive
}

# ── 백엔드 시작 ──
start_backend() {
    echo -e "${CYAN}[Backend]${NC} 시작 중..."

    # 이중 실행 방지
    if check_pid_alive "backend"; then
        local pid
        pid=$(cat "$PID_DIR/backend.pid")
        echo -e "${YELLOW}[Backend]${NC} 이미 실행 중 (PID: $pid)"
        return 0
    fi

    # 포트 점유 해제
    if is_port_in_use $BACKEND_PORT; then
        echo -e "${YELLOW}[Backend]${NC} 포트 $BACKEND_PORT 이미 사용 중 — 기존 프로세스 종료"
        kill_port $BACKEND_PORT
    fi

    # .env 파일 확인
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}[Backend]${NC} .env 파일 없음 — 모의투자 모드로 실행"
    fi

    # 가상환경 활성화 (있으면)
    if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi

    # 서버 시작
    python3 main.py api > /tmp/ats_api.log 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_DIR/backend.pid"

    # 서버 준비 대기 (최대 10초)
    for i in $(seq 1 10); do
        if curl -s "http://localhost:$BACKEND_PORT/docs" > /dev/null 2>&1; then
            echo -e "${GREEN}[Backend]${NC} ✓ 실행 완료 (PID: $pid, http://localhost:$BACKEND_PORT)"
            return 0
        fi
        sleep 1
    done

    # 10초 후에도 안 되면 로그 확인
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[Backend]${NC} ✓ 시작됨 (PID: $pid) — 데이터 로드 진행 중..."
        echo -e "  로그: tail -f /tmp/ats_api.log"
    else
        echo -e "${RED}[Backend]${NC} ✗ 시작 실패"
        tail -5 /tmp/ats_api.log 2>/dev/null
        return 1
    fi
}

# ── 프론트엔드 시작 ──
start_frontend() {
    echo -e "${CYAN}[Frontend]${NC} 시작 중..."

    # 이중 실행 방지
    if check_pid_alive "frontend"; then
        local pid
        pid=$(cat "$PID_DIR/frontend.pid")
        echo -e "${YELLOW}[Frontend]${NC} 이미 실행 중 (PID: $pid)"
        return 0
    fi

    # 포트 점유 해제
    if is_port_in_use $FRONTEND_PORT; then
        echo -e "${YELLOW}[Frontend]${NC} 포트 $FRONTEND_PORT 이미 사용 중 — 기존 프로세스 종료"
        kill_port $FRONTEND_PORT
    fi

    # node_modules 확인
    if [ ! -d "web/node_modules" ]; then
        echo -e "${CYAN}[Frontend]${NC} npm install 실행 중..."
        (cd web && npm install)
    fi

    # Vite 개발 서버 시작
    (cd web && npm run dev) > /tmp/ats_vite.log 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_DIR/frontend.pid"

    # 서버 준비 대기
    for i in $(seq 1 8); do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo -e "${GREEN}[Frontend]${NC} ✓ 실행 완료 (PID: $pid, http://localhost:$FRONTEND_PORT)"
            return 0
        fi
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[Frontend]${NC} ✓ 시작됨 (PID: $pid)"
    else
        echo -e "${RED}[Frontend]${NC} ✗ 시작 실패"
        tail -5 /tmp/ats_vite.log 2>/dev/null
        return 1
    fi
}

# ── 서버 종료 ──
stop_all() {
    echo -e "${CYAN}서버 종료 중...${NC}"

    # PID 파일 기반 종료
    for name in backend frontend; do
        if [ -f "$PID_DIR/$name.pid" ]; then
            local pid
            pid=$(cat "$PID_DIR/$name.pid")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                echo -e "  $name (PID: $pid) 종료"
            fi
            rm -f "$PID_DIR/$name.pid"
        fi
    done

    # 포트 기반 안전 정리 (PID 파일 누락 대비)
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT

    echo -e "${GREEN}✓ 모든 서버 종료 완료${NC}"
}

# ── 상태 확인 ──
show_status() {
    echo -e "${CYAN}═══ ATS 서버 상태 ═══${NC}"
    echo ""

    # Backend
    if check_pid_alive "backend"; then
        local pid
        pid=$(cat "$PID_DIR/backend.pid")
        echo -e "  ${GREEN}●${NC} Backend   PID: $pid  http://localhost:$BACKEND_PORT"
    elif is_port_in_use $BACKEND_PORT; then
        echo -e "  ${YELLOW}●${NC} Backend   포트 $BACKEND_PORT 사용 중 (PID 파일 없음)"
    else
        echo -e "  ${RED}●${NC} Backend   중지됨"
    fi

    # Frontend
    if check_pid_alive "frontend"; then
        local pid
        pid=$(cat "$PID_DIR/frontend.pid")
        echo -e "  ${GREEN}●${NC} Frontend  PID: $pid  http://localhost:$FRONTEND_PORT"
    elif is_port_in_use $FRONTEND_PORT; then
        echo -e "  ${YELLOW}●${NC} Frontend  포트 $FRONTEND_PORT 사용 중 (PID 파일 없음)"
    else
        echo -e "  ${RED}●${NC} Frontend  중지됨"
    fi

    echo ""
}

# ── 메인 ──
case "${1:-all}" in
    all)
        echo -e "${CYAN}═══ ATS 개발 서버 시작 ═══${NC}"
        echo ""
        start_backend
        start_frontend
        echo ""
        echo -e "${GREEN}═══ 준비 완료 ═══${NC}"
        echo -e "  Backend:  http://localhost:$BACKEND_PORT"
        echo -e "  Frontend: http://localhost:$FRONTEND_PORT"
        echo -e "  백엔드 로그: tail -f /tmp/ats_api.log"
        echo -e "  프론트 로그: tail -f /tmp/ats_vite.log"
        ;;
    api|backend)
        start_backend
        ;;
    web|frontend)
        start_frontend
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    restart)
        stop_all
        sleep 1
        echo ""
        start_backend
        start_frontend
        echo ""
        echo -e "${GREEN}═══ 재시작 완료 ═══${NC}"
        ;;
    *)
        echo "사용법: ./dev.sh [all|api|web|stop|status|restart]"
        exit 1
        ;;
esac
