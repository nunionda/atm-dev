#!/usr/bin/env python3
"""
ATS 독립 테스트 실행기
SQLAlchemy 없이 순수 로직 모듈을 테스트한다.

테스트 대상:
  - common/ (Enum, DataClass)
  - core/state_manager.py (FSM)
  - strategy/momentum_swing.py (시그널 계산)
  - risk/risk_manager.py (리스크 게이트)
"""

import sys
import os
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════
# 테스트 프레임워크 (pytest 대용)
# ═══════════════════════════════════════════

passed = 0
failed = 0
errors = []


def run_test(name, func):
    global passed, failed
    try:
        func()
        passed += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name} — {e}")
    except Exception as e:
        failed += 1
        errors.append((name, traceback.format_exc()))
        print(f"  💥 {name} — {e}")


# ═══════════════════════════════════════════
# Test Suite 1: common/enums.py
# ═══════════════════════════════════════════

def test_suite_enums():
    print("\n📦 [1/5] common/enums.py")

    from common.enums import (
        SystemState, PositionStatus, OrderSide,
        OrderType, ExitReason, TradeEventType,
    )

    def test_system_state_count():
        assert len(SystemState) == 6, f"Expected 6 states, got {len(SystemState)}"

    def test_position_status_values():
        assert PositionStatus.PENDING.value == "PENDING"
        assert PositionStatus.ACTIVE.value == "ACTIVE"
        assert PositionStatus.CLOSED.value == "CLOSED"

    def test_exit_reason_mapping():
        assert ExitReason.STOP_LOSS.value == "ES1"
        assert ExitReason.TAKE_PROFIT.value == "ES2"
        assert ExitReason.TRAILING_STOP.value == "ES3"
        assert ExitReason.DEAD_CROSS.value == "ES4"
        assert ExitReason.MAX_HOLDING.value == "ES5"

    def test_order_types():
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

    run_test("TC-COM-001: SystemState 6개 상태", test_system_state_count)
    run_test("TC-COM-002: PositionStatus 값", test_position_status_values)
    run_test("TC-COM-003: ExitReason ES1~ES5 매핑", test_exit_reason_mapping)
    run_test("TC-COM-004: OrderType/OrderSide 값", test_order_types)


# ═══════════════════════════════════════════
# Test Suite 2: common/types.py
# ═══════════════════════════════════════════

def test_suite_types():
    print("\n📦 [2/5] common/types.py")

    from common.types import Signal, Portfolio, RiskCheckResult, ExitSignal

    def test_signal_strength_auto():
        s = Signal(
            stock_code="005930", stock_name="삼성전자",
            primary_signals=["PS1", "PS2"],
            confirmation_filters=["CF1"],
            current_price=72000.0,
        )
        assert s.strength == 3, f"Expected 3, got {s.strength}"

    def test_signal_empty_strength():
        s = Signal(stock_code="005930", stock_name="테스트")
        assert s.strength == 0

    def test_signal_timestamp_auto():
        s = Signal(stock_code="005930", stock_name="테스트")
        assert len(s.timestamp) > 0

    def test_portfolio_defaults():
        p = Portfolio()
        assert p.total_capital == 0.0
        assert p.active_count == 0
        assert p.today_sold_codes == []

    def test_risk_check_passed():
        r = RiskCheckResult(passed=True)
        assert r.passed is True
        assert r.failed_gate is None

    def test_risk_check_failed():
        r = RiskCheckResult(passed=False, failed_gate="RG1", reason="한도 초과")
        assert r.failed_gate == "RG1"

    run_test("TC-TYP-001: Signal 강도 자동 계산", test_signal_strength_auto)
    run_test("TC-TYP-002: Signal 빈 강도 0", test_signal_empty_strength)
    run_test("TC-TYP-003: Signal 타임스탬프 자동", test_signal_timestamp_auto)
    run_test("TC-TYP-004: Portfolio 기본값", test_portfolio_defaults)
    run_test("TC-TYP-005: RiskCheckResult 통과", test_risk_check_passed)
    run_test("TC-TYP-006: RiskCheckResult 실패", test_risk_check_failed)


# ═══════════════════════════════════════════
# Test Suite 3: core/state_manager.py
# ═══════════════════════════════════════════

def test_suite_state_manager():
    print("\n📦 [3/5] core/state_manager.py")

    from common.enums import SystemState
    from common.exceptions import StateTransitionError
    from core.state_manager import SystemStateManager

    def test_initial_state():
        sm = SystemStateManager()
        assert sm.state == SystemState.INIT

    def test_valid_full_lifecycle():
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        assert sm.is_ready
        sm.transition_to(SystemState.RUNNING)
        assert sm.is_running
        sm.transition_to(SystemState.STOPPING)
        sm.transition_to(SystemState.STOPPED)
        assert sm.is_stopped

    def test_invalid_transition():
        sm = SystemStateManager()
        try:
            sm.transition_to(SystemState.RUNNING)  # INIT→RUNNING (invalid)
            assert False, "Should have raised StateTransitionError"
        except StateTransitionError:
            pass  # Expected

    def test_force_error():
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        sm.force_error("Critical")
        assert sm.state == SystemState.ERROR

    def test_error_recovery():
        sm = SystemStateManager()
        sm.force_error("test")
        sm.transition_to(SystemState.READY)
        assert sm.is_ready

    def test_stopped_to_init():
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        sm.transition_to(SystemState.STOPPING)
        sm.transition_to(SystemState.STOPPED)
        sm.transition_to(SystemState.INIT)
        assert sm.state == SystemState.INIT

    def test_running_to_ready_invalid():
        sm = SystemStateManager()
        sm.transition_to(SystemState.READY)
        sm.transition_to(SystemState.RUNNING)
        try:
            sm.transition_to(SystemState.READY)
            assert False, "Should have raised"
        except StateTransitionError:
            pass

    run_test("TC-STA-001: 초기 상태 INIT", test_initial_state)
    run_test("TC-STA-002: 전체 수명주기", test_valid_full_lifecycle)
    run_test("TC-STA-003: 잘못된 전이 에러", test_invalid_transition)
    run_test("TC-STA-004: ERROR 강제 전이", test_force_error)
    run_test("TC-STA-005: ERROR 복구", test_error_recovery)
    run_test("TC-STA-006: STOPPED→INIT 재기동", test_stopped_to_init)
    run_test("TC-STA-007: RUNNING→READY 불가", test_running_to_ready_invalid)


# ═══════════════════════════════════════════
# Test Suite 4: strategy/momentum_swing.py
# ═══════════════════════════════════════════

def test_suite_strategy():
    print("\n📦 [4/5] strategy/momentum_swing.py")

    from data.config_manager import ATSConfig, StrategyConfig, ExitConfig
    from strategy.momentum_swing import MomentumSwingStrategy
    from common.types import PriceData

    config = ATSConfig(
        strategy=StrategyConfig(),
        exit=ExitConfig(),
    )
    strategy = MomentumSwingStrategy(config)

    def make_ohlcv(n=60, base=70000, trend=5000, spike_last=2000):
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=n, freq="B")
        t = np.linspace(0, trend, n)
        noise = np.random.normal(0, 500, n)
        closes = base + t + noise
        if spike_last > 0:
            closes[-5:] += spike_last
        return pd.DataFrame({
            "date": [d.strftime("%Y%m%d") for d in dates],
            "open": closes - 200, "high": closes + 300,
            "low": closes - 300, "close": closes,
            "volume": np.random.randint(10_000_000, 30_000_000, n),
        })

    def test_indicators_columns():
        df = strategy.calculate_indicators(make_ohlcv())
        expected = ["ma_short", "ma_long", "macd_line", "macd_signal",
                     "macd_hist", "rsi", "bb_upper", "bb_lower", "volume_ma"]
        for col in expected:
            assert col in df.columns, f"Missing: {col}"

    def test_rsi_range():
        df = strategy.calculate_indicators(make_ohlcv())
        valid = df["rsi"].dropna()
        assert (valid >= 0).all(), "RSI < 0"
        assert (valid <= 100).all(), "RSI > 100"

    def test_bb_upper_gt_lower():
        df = strategy.calculate_indicators(make_ohlcv())
        valid = df.dropna(subset=["bb_upper", "bb_lower"])
        assert (valid["bb_upper"] > valid["bb_lower"]).all()

    def test_empty_df():
        df = strategy.calculate_indicators(pd.DataFrame())
        assert df.empty

    def test_short_df():
        short = pd.DataFrame({"close": [70000] * 5, "volume": [1000000] * 5})
        df = strategy.calculate_indicators(short)
        assert len(df) == 5

    def test_entry_returns_list():
        ohlcv = make_ohlcv()
        prices = {
            "005930": PriceData("005930", "삼성전자", 77000, 76000, 77500,
                                75500, 76000, 25000000, 1.3, datetime.now().isoformat()),
        }
        signals = strategy.scan_entry_signals(["005930"], {"005930": ohlcv}, prices)
        assert isinstance(signals, list)

    def test_no_signal_insufficient_data():
        short = pd.DataFrame({
            "date": ["20260101"] * 5, "open": [70000] * 5, "high": [71000] * 5,
            "low": [69000] * 5, "close": [70500] * 5, "volume": [1000000] * 5,
        })
        signals = strategy.scan_entry_signals(["005930"], {"005930": short}, {})
        assert len(signals) == 0

    # ── 청산 시그널 테스트 ──

    @dataclass
    class MockPosition:
        position_id: str = "pos_test"
        stock_code: str = "005930"
        stock_name: str = "삼성전자"
        entry_price: float = 70000.0
        quantity: int = 20
        trailing_high: float = 72000.0
        holding_days: int = 3

    def test_stop_loss_es1():
        pos = MockPosition()
        prices = {
            "005930": PriceData("005930", "삼성전자", 67000, 68000, 68500,
                                66500, 69000, 20000000, -2.9, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES1"
        assert exits[0].order_type == "MARKET"

    def test_take_profit_es2():
        pos = MockPosition()
        prices = {
            "005930": PriceData("005930", "삼성전자", 75000, 74000, 75500,
                                73500, 74000, 18000000, 1.35, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES2"

    def test_max_holding_es5():
        pos = MockPosition(holding_days=11)
        prices = {
            "005930": PriceData("005930", "삼성전자", 71000, 70500, 71500,
                                70000, 70800, 12000000, 0.28, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES5"
        assert exits[0].order_type == "LIMIT"

    def test_hold_no_exit():
        pos = MockPosition(holding_days=3)
        prices = {
            "005930": PriceData("005930", "삼성전자", 70500, 70000, 71000,
                                69800, 70200, 10000000, 0.43, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 0

    run_test("TC-STR-001: 지표 컬럼 추가", test_indicators_columns)
    run_test("TC-STR-002: RSI 0~100 범위", test_rsi_range)
    run_test("TC-STR-003: BB 상단 > 하단", test_bb_upper_gt_lower)
    run_test("TC-STR-004: 빈 DataFrame 처리", test_empty_df)
    run_test("TC-STR-005: 짧은 DataFrame 처리", test_short_df)
    run_test("TC-STR-006: 진입 시그널 리스트 반환", test_entry_returns_list)
    run_test("TC-STR-007: 데이터 부족 시 시그널 없음", test_no_signal_insufficient_data)
    run_test("TC-STR-008: ES1 손절 시그널 (-3%↓)", test_stop_loss_es1)
    run_test("TC-STR-009: ES2 익절 시그널 (+7%↑)", test_take_profit_es2)
    run_test("TC-STR-010: ES5 보유기간 초과 (>10일)", test_max_holding_es5)
    run_test("TC-STR-011: HOLD (청산조건 없음)", test_hold_no_exit)


# ═══════════════════════════════════════════
# Test Suite 5: risk/risk_manager.py
# ═══════════════════════════════════════════

def test_suite_risk_manager():
    print("\n📦 [5/5] risk/risk_manager.py")

    from data.config_manager import ATSConfig, PortfolioConfig, RiskConfig
    from risk.risk_manager import RiskManager
    from common.types import Signal, Portfolio

    config = ATSConfig(
        portfolio=PortfolioConfig(max_positions=10, max_weight_per_stock=0.15, min_cash_ratio=0.20),
        risk=RiskConfig(daily_loss_limit=-0.03, mdd_limit=-0.10, max_order_amount=3_000_000),
    )
    rm = RiskManager(config)

    sig = lambda price=72000, bb=76000: Signal(
        stock_code="005930", stock_name="삼성전자",
        primary_signals=["PS1"], confirmation_filters=["CF1"],
        current_price=price, bb_upper=bb,
    )

    pf = lambda active=2, cash=8_000_000, capital=10_000_000, daily_buy=1_500_000: Portfolio(
        total_capital=capital, cash_balance=cash,
        active_count=active, daily_buy_amount=daily_buy,
    )

    def test_all_pass():
        r = rm.check_risk_gates(sig(), pf())
        assert r.passed is True

    def test_rg1_fail():
        r = rm.check_risk_gates(sig(), pf(active=10))
        assert r.passed is False
        assert r.failed_gate == "RG1"

    def test_rg1_boundary():
        r = rm.check_risk_gates(sig(), pf(active=9))
        assert r.passed is True

    def test_rg4_fail():
        r = rm.check_risk_gates(sig(price=77000, bb=76000), pf())
        assert r.passed is False
        assert r.failed_gate == "RG4"

    def test_rg4_exact_boundary():
        r = rm.check_risk_gates(sig(price=76000, bb=76000), pf())
        assert r.passed is False
        assert r.failed_gate == "RG4"

    def test_rg4_just_below():
        r = rm.check_risk_gates(sig(price=75999, bb=76000), pf())
        assert r.passed is True

    def test_daily_loss_no():
        assert rm.check_daily_loss_limit(Portfolio(total_capital=10_000_000, daily_pnl=50000)) is False

    def test_daily_loss_at_limit():
        assert rm.check_daily_loss_limit(Portfolio(total_capital=10_000_000, daily_pnl=-300_000)) is True

    def test_daily_loss_exceeded():
        assert rm.check_daily_loss_limit(Portfolio(total_capital=10_000_000, daily_pnl=-500_000)) is True

    def test_mdd_within():
        assert rm.check_mdd_limit(Portfolio(mdd=-0.05)) is False

    def test_mdd_at_limit():
        assert rm.check_mdd_limit(Portfolio(mdd=-0.10)) is True

    def test_buy_qty_normal():
        qty = rm.calculate_buy_quantity(72000.0, pf())
        assert qty == 20, f"Expected 20, got {qty}"  # 10M*15%=1.5M / 72K = 20

    def test_buy_qty_no_cash():
        qty = rm.calculate_buy_quantity(72000.0, pf(cash=1_500_000))
        assert qty == 0

    def test_buy_qty_zero_price():
        qty = rm.calculate_buy_quantity(0, pf())
        assert qty == 0

    def test_buy_qty_max_capped():
        qty = rm.calculate_buy_quantity(72000.0, pf(capital=100_000_000, cash=80_000_000))
        expected = int(3_000_000 / 72000)  # 41
        assert qty == expected, f"Expected {expected}, got {qty}"

    run_test("TC-RSK-001: 모든 게이트 통과", test_all_pass)
    run_test("TC-RSK-002: RG1 종목수 한도 초과", test_rg1_fail)
    run_test("TC-RSK-003: RG1 한도 미만 통과", test_rg1_boundary)
    run_test("TC-RSK-004: RG4 BB 상단 초과", test_rg4_fail)
    run_test("TC-RSK-005: RG4 BB 상단 정확히 도달", test_rg4_exact_boundary)
    run_test("TC-RSK-006: RG4 BB 상단 미만 통과", test_rg4_just_below)
    run_test("TC-RSK-007: 일일손실 한도 미달", test_daily_loss_no)
    run_test("TC-RSK-008: 일일손실 -3% 도달", test_daily_loss_at_limit)
    run_test("TC-RSK-009: 일일손실 -3% 초과", test_daily_loss_exceeded)
    run_test("TC-RSK-010: MDD 한도 내", test_mdd_within)
    run_test("TC-RSK-011: MDD -10% 도달", test_mdd_at_limit)
    run_test("TC-RSK-012: 매수수량 정상계산 (20주)", test_buy_qty_normal)
    run_test("TC-RSK-013: 현금부족 시 0주", test_buy_qty_no_cash)
    run_test("TC-RSK-014: 현재가 0 시 0주", test_buy_qty_zero_price)
    run_test("TC-RSK-015: 최대주문금액 제한", test_buy_qty_max_capped)


# ═══════════════════════════════════════════
# 실행
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("ATS Phase 4 — 단위 테스트 실행")
    print("=" * 60)

    test_suite_enums()
    test_suite_types()
    test_suite_state_manager()
    test_suite_strategy()
    test_suite_risk_manager()

    print("\n" + "=" * 60)
    print(f"결과: ✅ {passed} passed / ❌ {failed} failed / 총 {passed + failed}건")
    print("=" * 60)

    if errors:
        print("\n실패 상세:")
        for name, err in errors:
            print(f"\n  ❌ {name}")
            print(f"     {err[:200]}")

    sys.exit(0 if failed == 0 else 1)
