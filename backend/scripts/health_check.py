#!/usr/bin/env python3
"""
ATS 헬스체크 스크립트
배포 전/후 외부 의존성 연결 상태를 점검한다.

Usage:
    python scripts/health_check.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.config_manager import ConfigManager
from infra.logger import setup_logger, get_logger

setup_logger(level="INFO")
logger = get_logger("health_check")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
SKIP = "⏭️"
results = []


def check(name, func):
    try:
        result = func()
        if len(result) == 3 and result[2] == "skip":
            results.append((name, None, result[1]))
            print(f"  {SKIP} {name}: {result[1]}")
            return
        ok, msg = result[0], result[1]
        status = PASS if ok else FAIL
        results.append((name, ok, msg))
        print(f"  {status} {name}: {msg}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  {FAIL} {name}: {e}")


def _load_config():
    cm = ConfigManager()
    return cm.load()


def _has_kis_credentials(config):
    return (config.kis_app_key and config.kis_app_key != "your_app_key_here"
            and config.kis_app_secret and config.kis_app_secret != "your_app_secret_here"
            and config.kis_account_no and config.kis_account_no != "12345678-01")


def _has_telegram_credentials(config):
    return (config.telegram_bot_token and config.telegram_bot_token != "your_bot_token_here"
            and config.telegram_chat_id and config.telegram_chat_id != "your_chat_id_here")


def check_config():
    """설정 파일 존재 여부."""
    config = _load_config()
    missing = []
    if not _has_kis_credentials(config):
        missing.append("KIS(APP_KEY/SECRET/ACCOUNT)")
    if not _has_telegram_credentials(config):
        missing.append("TELEGRAM(BOT_TOKEN/CHAT_ID)")

    mode_str = f"mode={'모의' if config.kis_is_paper else '실전'}"
    if missing:
        return True, f"config.yaml 로드 완료 | {mode_str} | 미설정: {', '.join(missing)}"
    return True, f"config.yaml + .env 로드 완료 | {mode_str}"


def check_database():
    """DB 연결 및 테이블 확인."""
    from infra.db.connection import Database
    cm = ConfigManager()
    config = cm.load()

    db = Database(db_path=config.db_path)
    db.init_tables()

    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    expected = ["universe", "positions", "orders", "trade_logs",
                "daily_reports", "config_history", "system_logs"]
    missing = [t for t in expected if t not in tables]
    db.close()

    if missing:
        return False, f"누락 테이블: {missing}"
    return True, f"SQLite OK | {len(tables)}개 테이블 | path={config.db_path}"


def _get_kis_broker(config):
    from infra.broker.kis_broker import KISBroker
    return KISBroker(
        app_key=config.kis_app_key,
        app_secret=config.kis_app_secret,
        account_no=config.kis_account_no,
        is_paper=config.kis_is_paper,
    )


def check_kis_auth():
    """한투 API 인증 토큰 발급."""
    config = _load_config()
    if not _has_kis_credentials(config):
        return None, "KIS 크레덴셜 미설정 — SKIP", "skip"

    broker = _get_kis_broker(config)
    start = time.time()
    token = broker.authenticate()
    elapsed = time.time() - start

    if token and len(token) > 10:
        return True, f"토큰 발급 OK | {elapsed:.1f}초 | expires={broker._token_expires}"
    return False, "토큰 발급 실패"


def check_kis_price():
    """한투 API 시세 조회 (삼성전자)."""
    config = _load_config()
    if not _has_kis_credentials(config):
        return None, "KIS 크레덴셜 미설정 — SKIP", "skip"

    broker = _get_kis_broker(config)
    broker.authenticate()

    start = time.time()
    price = broker.get_price("005930")
    elapsed = time.time() - start

    if price and price.current_price > 0:
        return True, f"삼성전자 현재가={price.current_price:,.0f}원 | {elapsed:.1f}초"
    return False, "시세 조회 실패"


def check_kis_balance():
    """한투 API 잔고 조회."""
    config = _load_config()
    if not _has_kis_credentials(config):
        return None, "KIS 크레덴셜 미설정 — SKIP", "skip"

    broker = _get_kis_broker(config)
    broker.authenticate()

    balance = broker.get_balance()

    return True, (
        f"예수금={balance.cash:,.0f}원 | "
        f"평가금={balance.total_eval:,.0f}원 | "
        f"보유종목={len(balance.positions)}개"
    )


def check_telegram():
    """Telegram 알림 발송 테스트."""
    import requests
    config = _load_config()

    if not _has_telegram_credentials(config):
        return None, "Telegram 크레덴셜 미설정 — SKIP", "skip"

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": config.telegram_chat_id,
        "text": "🔔 ATS 헬스체크 테스트 메시지",
    }, timeout=10)

    if resp.status_code == 200:
        return True, "메시지 발송 OK"
    return False, f"HTTP {resp.status_code}: {resp.text[:100]}"


def check_universe():
    """유니버스 종목 수 확인."""
    from infra.db.connection import Database
    from infra.db.repository import Repository
    cm = ConfigManager()
    config = cm.load()

    db = Database(db_path=config.db_path)
    db.init_tables()
    repo = Repository(db)
    active = repo.get_active_universe()
    db.close()

    if len(active) == 0:
        return False, "유니버스 0건 — 'python scripts/load_universe.py' 실행 필요"
    return True, f"유니버스 {len(active)}종목 로드 완료"


def main():
    print("=" * 60)
    print("ATS Health Check")
    print("=" * 60)

    print("\n[1] 설정 파일")
    check("config.yaml + .env", check_config)

    print("\n[2] 데이터베이스")
    check("SQLite DB", check_database)
    check("유니버스 종목", check_universe)

    print("\n[3] 한국투자증권 API")
    check("인증 토큰 발급", check_kis_auth)
    check("시세 조회 (005930)", check_kis_price)
    check("계좌 잔고 조회", check_kis_balance)

    print("\n[4] Telegram 알림")
    check("메시지 발송", check_telegram)

    # 결과 요약
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok is True)
    skipped = sum(1 for _, ok, _ in results if ok is None)
    failed = total - passed - skipped

    print("\n" + "=" * 60)
    print(f"결과: {PASS} {passed} passed / {SKIP} {skipped} skipped / {FAIL} {failed} failed / 총 {total}건")
    print("=" * 60)

    if failed > 0:
        print(f"\n{WARN} {failed}건 실패 — 위 항목을 확인하세요.")
        return 1
    elif skipped > 0:
        print(f"\n{PASS} 로컬 점검 통과 — 외부 연동은 .env 설정 후 재점검 필요")
        return 0
    else:
        print(f"\n{PASS} 모든 점검 통과 — 시스템 기동 가능")
        return 0


if __name__ == "__main__":
    sys.exit(main())
