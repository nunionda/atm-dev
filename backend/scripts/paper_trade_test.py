#!/usr/bin/env python3
"""
모의투자 연동 테스트
한투 모의투자 서버와 실제 연결하여 전 API를 검증한다.

Usage:
    python scripts/paper_trade_test.py

사전 조건:
    1. .env에 모의투자 APP_KEY/SECRET 설정 (KIS_IS_PAPER=true)
    2. 한투 모의투자 계좌 개설 완료
    3. 모의투자 가상자금 충전 완료
"""

import os
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.config_manager import ConfigManager
from infra.broker.kis_broker import KISBroker
from infra.logger import setup_logger, get_logger

setup_logger(level="DEBUG")
logger = get_logger("paper_test")

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"
results = []


def test(name, func, skip_condition=False):
    if skip_condition:
        results.append((name, None, "SKIP"))
        print(f"  {SKIP} {name}: 스킵")
        return None
    try:
        ok, msg, data = func()
        status = PASS if ok else FAIL
        results.append((name, ok, msg))
        print(f"  {status} {name}: {msg}")
        return data
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  {FAIL} {name}: {e}")
        return None


def main():
    print("=" * 60)
    print("ATS 모의투자 연동 테스트")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    cm = ConfigManager()
    config = cm.load()

    if not config.kis_is_paper:
        print(f"\n{FAIL} KIS_IS_PAPER=false → 실전 모드입니다!")
        print("   모의투자 테스트를 위해 .env에서 KIS_IS_PAPER=true로 변경하세요.")
        return 1

    broker = KISBroker(
        app_key=config.kis_app_key,
        app_secret=config.kis_app_secret,
        account_no=config.kis_account_no,
        is_paper=True,
    )

    print(f"\n모드: 모의투자 (paper)")
    print(f"서버: {broker.base_url}")
    print(f"계좌: {broker.cano[:4]}****-{broker.acnt_prdt_cd}")

    # ── Test 1: 인증 ──
    print("\n[1/7] 인증 토큰 발급")
    def test_auth():
        start = time.time()
        token = broker.authenticate()
        elapsed = time.time() - start
        valid = broker.is_token_valid()
        return (
            bool(token) and valid,
            f"토큰 길이={len(token)} | 유효={valid} | {elapsed:.2f}초",
            token,
        )
    test("OAuth 토큰 발급", test_auth)

    # ── Test 2: 현재가 조회 ──
    print("\n[2/7] 현재가 조회")
    test_codes = ["005930", "000660", "035420"]
    prices = {}
    for code in test_codes:
        def test_price(c=code):
            time.sleep(0.3)
            p = broker.get_price(c)
            prices[c] = p
            return (
                p.current_price > 0,
                f"{p.stock_name} = {p.current_price:,.0f}원 | 전일비 {p.change_pct:+.2f}%",
                p,
            )
        test(f"현재가 [{code}]", test_price)

    # ── Test 3: 일봉 조회 ──
    print("\n[3/7] 일봉 OHLCV 조회")
    def test_ohlcv():
        time.sleep(0.3)
        df = broker.get_ohlcv("005930", period=30)
        if df.empty:
            return False, "빈 DataFrame 반환", None
        cols = list(df.columns)
        last = df.iloc[-1]
        return (
            len(df) >= 10,
            f"{len(df)}행 | 컬럼={cols} | 최근일={last['date']}",
            df,
        )
    test("일봉 OHLCV [005930]", test_ohlcv)

    # ── Test 4: 잔고 조회 ──
    print("\n[4/7] 계좌 잔고 조회")
    balance = None
    def test_balance():
        nonlocal balance
        time.sleep(0.3)
        balance = broker.get_balance()
        return (
            True,
            f"예수금={balance.cash:,.0f}원 | 평가={balance.total_eval:,.0f}원 | "
            f"보유={len(balance.positions)}종목",
            balance,
        )
    test("잔고 조회", test_balance)

    # ── Test 5: 매수 주문 (소액 1주) ──
    print("\n[5/7] 매수 주문 (삼성전자 1주 지정가)")

    # 장중인지 확인
    now = datetime.now()
    is_market_open = (
        now.weekday() < 5  # 평일
        and now.hour >= 9 and (now.hour < 15 or (now.hour == 15 and now.minute <= 30))
    )

    buy_order_id = None
    def test_buy():
        nonlocal buy_order_id
        from common.types import OrderRequest
        price = prices.get("005930")
        if not price:
            return False, "현재가 없음", None

        # 현재가보다 5% 낮은 가격으로 지정가 주문 (체결 방지)
        limit_price = int(price.current_price * 0.95)
        order = OrderRequest(
            order_id="test_buy_001",
            position_id="test_pos_001",
            stock_code="005930",
            stock_name="삼성전자",
            side="BUY",
            order_type="LIMIT",
            price=limit_price,
            quantity=1,
        )
        result = broker.place_order(order)
        buy_order_id = result.broker_order_id
        return (
            result.success,
            f"broker_id={result.broker_order_id} | "
            f"price={limit_price:,}원 × 1주 (의도적 미체결)",
            result,
        )
    test("매수 주문 전송", test_buy, skip_condition=not is_market_open)

    # ── Test 6: 체결 조회 ──
    print("\n[6/7] 체결 상태 조회")
    def test_order_status():
        if not buy_order_id:
            return False, "매수 주문 ID 없음", None
        time.sleep(1)
        status = broker.get_order_status(buy_order_id)
        return (
            True,
            f"status={status.status} | filled={status.filled_quantity}주",
            status,
        )
    test("체결 조회", test_order_status, skip_condition=buy_order_id is None)

    # ── Test 7: 주문 취소 ──
    print("\n[7/7] 주문 취소")
    def test_cancel():
        if not buy_order_id:
            return False, "취소할 주문 없음", None
        time.sleep(0.5)
        ok = broker.cancel_order(buy_order_id)
        return ok, f"취소 {'성공' if ok else '실패'} | broker_id={buy_order_id}", None
    test("주문 취소", test_cancel, skip_condition=buy_order_id is None)

    # ── 결과 요약 ──
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok is True)
    failed = sum(1 for _, ok, _ in results if ok is False)
    skipped = sum(1 for _, ok, _ in results if ok is None)

    print("\n" + "=" * 60)
    print(f"결과: {PASS} {passed} / {FAIL} {failed} / {SKIP} {skipped} / 총 {total}")
    print("=" * 60)

    if not is_market_open:
        print(f"\n{SKIP} 장외 시간이라 주문 테스트가 스킵되었습니다.")
        print("   장중(평일 09:00~15:30)에 재실행하면 매수/취소까지 검증합니다.")

    if failed > 0:
        print(f"\n{FAIL} {failed}건 실패 — 확인이 필요합니다.")
        return 1

    print(f"\n{PASS} 모의투자 연동 검증 완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
