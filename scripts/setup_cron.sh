#!/usr/bin/env bash
# ===== ATS crontab 자동 기동/중지 설정 =====
# 문서: ATS-SAD-001 §14
# Usage: bash scripts/setup_cron.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT_DIR/venv/bin/python3"
LOG_DIR="$PROJECT_DIR/data_store/logs"

echo "ATS crontab 설정"
echo "  Project: $PROJECT_DIR"
echo "  Python:  $PYTHON"
echo

# cron 작업 내용
CRON_START="50 8 * * 1-5 cd $PROJECT_DIR && $PYTHON main.py start >> $LOG_DIR/cron.log 2>&1"
CRON_COMMENT="# ATS Auto-Trading (Mon-Fri 08:50 start)"

# 기존 ATS 관련 crontab 제거 후 새로 추가
(crontab -l 2>/dev/null | grep -v "ATS" | grep -v "main.py start") | crontab - 2>/dev/null || true

(crontab -l 2>/dev/null; echo "$CRON_COMMENT"; echo "$CRON_START") | crontab -

echo "✅ crontab 설정 완료:"
echo
crontab -l | grep -A1 "ATS"
echo
echo "스케줄: 평일(월~금) 08:50 자동 기동"
echo "중지:   시스템 내부 스케줄러가 15:35 자동 중지"
echo
echo "crontab 해제: crontab -e 에서 ATS 줄 삭제"
