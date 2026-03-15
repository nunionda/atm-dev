#!/usr/bin/env bash
# ===== ATS 초기 설정 스크립트 =====
# Usage: bash scripts/setup.sh
set -e

echo "============================================================"
echo "ATS 초기 설정"
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo
echo "[1/5] Python 버전 확인..."
PYTHON_VERSION=$(python3 --version 2>&1)
echo "  $PYTHON_VERSION"
MAJOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$MAJOR" -lt 11 ]; then
    echo "  ❌ Python 3.11 이상이 필요합니다."
    exit 1
fi
echo "  ✅ OK"

echo
echo "[2/5] 가상환경 생성..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  ✅ venv 생성 완료"
else
    echo "  ⏭️  venv 이미 존재"
fi

echo
echo "[3/5] 의존성 설치..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✅ $(pip list --format=freeze | wc -l)개 패키지 설치 완료"

echo
echo "[4/5] 환경 파일 설정..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ⚠️  .env 파일이 생성되었습니다."
    echo "     실제 API Key와 계좌번호를 입력하세요:"
    echo "     vi .env"
else
    echo "  ⏭️  .env 이미 존재"
fi

echo
echo "[5/5] 데이터베이스 초기화..."
mkdir -p data_store/logs
python3 main.py init-db
echo

echo "[+] 유니버스 로드 (샘플 30종목)..."
python3 scripts/load_universe.py
echo

echo "============================================================"
echo "초기 설정 완료!"
echo "============================================================"
echo
echo "다음 단계:"
echo "  1. .env 파일을 편집하여 실제 API Key를 입력하세요"
echo "     vi .env"
echo
echo "  2. 헬스체크를 실행하세요"
echo "     python scripts/health_check.py"
echo
echo "  3. 모의투자 연동 테스트를 실행하세요"
echo "     python scripts/paper_trade_test.py"
echo
echo "  4. 매매 시스템을 시작하세요"
echo "     python main.py start"
echo
