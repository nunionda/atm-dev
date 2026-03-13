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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ats"))

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
        # entry=70000, price=66000 → -5.7% → ES1 -5% 트리거
        prices = {
            "005930": PriceData("005930", "삼성전자", 66000, 66500, 67000,
                                65500, 69000, 20000000, -5.7, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES1"
        assert exits[0].order_type == "MARKET"

    def test_take_profit_es2():
        pos = MockPosition()
        # entry=70000, price=85000 → +21.4% → ES2 +20% 트리거
        prices = {
            "005930": PriceData("005930", "삼성전자", 85000, 84000, 85500,
                                83500, 84000, 18000000, 21.4, datetime.now().isoformat()),
        }
        exits = strategy.scan_exit_signals([pos], {"005930": pd.DataFrame()}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES2"

    def test_max_holding_es5():
        # max_holding_days=40 (BULL), holding_days=41 → ES5 트리거
        pos = MockPosition(holding_days=41)
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
    run_test("TC-STR-008: ES1 손절 시그널 (-5%↓)", test_stop_loss_es1)
    run_test("TC-STR-009: ES2 익절 시그널 (+20%↑)", test_take_profit_es2)
    run_test("TC-STR-010: ES5 보유기간 초과 (>40일)", test_max_holding_es5)
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
        portfolio=PortfolioConfig(max_positions=10, max_weight_per_stock=0.15, min_cash_ratio=0.30),
        risk=RiskConfig(daily_loss_limit=-0.05, mdd_limit=-0.15, max_order_amount=3_000_000),
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
        # BR-R01: -5% → 10M × -5% = -500K
        assert rm.check_daily_loss_limit(Portfolio(total_capital=10_000_000, daily_pnl=-500_000)) is True

    def test_daily_loss_exceeded():
        # -8% > -5% → 매매 중단
        assert rm.check_daily_loss_limit(Portfolio(total_capital=10_000_000, daily_pnl=-800_000)) is True

    def test_mdd_within():
        assert rm.check_mdd_limit(Portfolio(mdd=-0.10)) is False

    def test_mdd_at_limit():
        # BR-R02: MDD -15% → 시스템 정지
        assert rm.check_mdd_limit(Portfolio(mdd=-0.15)) is True

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
    run_test("TC-RSK-008: 일일손실 -5% 도달 (BR-R01)", test_daily_loss_at_limit)
    run_test("TC-RSK-009: 일일손실 -5% 초과", test_daily_loss_exceeded)
    run_test("TC-RSK-010: MDD 한도 내", test_mdd_within)
    run_test("TC-RSK-011: MDD -15% 도달 (BR-R02)", test_mdd_at_limit)
    run_test("TC-RSK-012: 매수수량 정상계산 (20주)", test_buy_qty_normal)
    run_test("TC-RSK-013: 현금부족 시 0주", test_buy_qty_no_cash)
    run_test("TC-RSK-014: 현재가 0 시 0주", test_buy_qty_zero_price)
    run_test("TC-RSK-015: 최대주문금액 제한", test_buy_qty_max_capped)


# ═══════════════════════════════════════════
# Test Suite 6: strategy/breakout_retest.py
# ═══════════════════════════════════════════

def _make_breakout_config():
    """테스트용 ATSConfig with BreakoutRetestConfig."""
    from data.config_manager import (
        ATSConfig, StrategyConfig, ExitConfig, PortfolioConfig,
        RiskConfig, OrderConfig, SMCStrategyConfig, BreakoutRetestConfig,
    )
    config = ATSConfig()
    config.strategy = StrategyConfig()
    config.exit = ExitConfig(stop_loss_pct=-0.05)
    config.smc_strategy = SMCStrategyConfig()
    config.breakout_retest = BreakoutRetestConfig()
    return config


def _make_ohlcv_df(
    n: int = 150,
    base_price: float = 100.0,
    trend: str = "flat",
    breakout_at: int = -1,
    retest_at: int = -1,
):
    """
    테스트용 합성 OHLCV DataFrame 생성.
    trend: "flat" | "up" | "breakout_retest"
    breakout_at: 돌파 봉 인덱스 (breakout_retest 모드)
    retest_at: 리테스트 봉 인덱스 (breakout_retest 모드)
    """
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    prices = np.full(n, base_price, dtype=float)

    if trend == "flat":
        noise = np.random.randn(n) * 0.5
        prices = base_price + np.cumsum(noise * 0.1)
    elif trend == "up":
        for i in range(1, n):
            prices[i] = prices[i - 1] * (1 + np.random.uniform(0.001, 0.005))
    elif trend == "breakout_retest":
        # 횡보 → 돌파 → 풀백 → 반등
        if breakout_at < 0:
            breakout_at = 120
        if retest_at < 0:
            retest_at = 130

        for i in range(1, n):
            if i < breakout_at:
                # 횡보: 100 ± 2
                prices[i] = base_price + np.random.randn() * 1.0
            elif i == breakout_at:
                # 돌파: 큰 양봉
                prices[i] = prices[i - 1] * 1.05
            elif breakout_at < i < retest_at:
                # 상승 지속
                prices[i] = prices[i - 1] * (1 + np.random.uniform(0.002, 0.01))
            elif i == retest_at:
                # 풀백: 돌파 레벨 근처로 복귀
                prices[i] = prices[breakout_at] * 1.01
            elif i == retest_at + 1:
                # 반등 캔들 (하단꼬리 길게)
                prices[i] = prices[i - 1] * 1.02
            else:
                prices[i] = prices[i - 1] * (1 + np.random.uniform(0.001, 0.005))

    opens = prices * (1 + np.random.randn(n) * 0.003)
    highs = np.maximum(prices, opens) * (1 + np.abs(np.random.randn(n)) * 0.005)
    lows = np.minimum(prices, opens) * (1 - np.abs(np.random.randn(n)) * 0.005)

    # 돌파 봉에 큰 body와 높은 거래량
    volumes = np.random.randint(100000, 500000, size=n).astype(float)
    if trend == "breakout_retest" and 0 <= breakout_at < n:
        # 돌파: 큰 양봉 + 높은 거래량
        opens[breakout_at] = prices[breakout_at] * 0.97
        highs[breakout_at] = prices[breakout_at] * 1.01
        lows[breakout_at] = opens[breakout_at] * 0.99
        volumes[breakout_at] = 1000000

        # 리테스트: 낮은 거래량 + 하단꼬리
        if 0 <= retest_at < n:
            volumes[retest_at] = 100000  # 저거래량 풀백

    df = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    })
    return df


def test_suite_breakout_retest():
    print("\n📦 [6/6] strategy/breakout_retest.py")

    from strategy.breakout_retest import BreakoutRetestStrategy, BreakoutState

    config = _make_breakout_config()

    # TC-BRT-001: 지표 컬럼 생성 확인
    def test_indicators_columns():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        result = strat.calculate_indicators(df.copy())
        required_cols = [
            "ma_short", "ma_long", "macd_line", "macd_signal", "macd_hist",
            "rsi", "bb_upper", "bb_lower", "bb_width", "volume_ma",
            "atr", "atr_pct", "adx", "plus_di", "minus_di",
            "is_swing_high", "is_swing_low", "marker", "ob_top", "ob_bottom",
            "fvg_top", "fvg_bottom", "fvg_type", "obv", "obv_ema5", "obv_ema20",
        ]
        for col in required_cols:
            assert col in result.columns, f"Missing column: {col}"

    run_test("TC-BRT-001: 지표 컬럼 생성", test_indicators_columns)

    # TC-BRT-002: 4-Layer 스코어링 범위 검증
    def test_breakout_score_range():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        s1 = strat._score_structure(df)
        s2 = strat._score_volatility_squeeze(df)
        s3 = strat._score_obv_break(df)
        s4 = strat._score_momentum_breakout(df)
        assert 0 <= s1 <= config.breakout_retest.weight_structure, f"L1 out of range: {s1}"
        assert 0 <= s2 <= config.breakout_retest.weight_volatility, f"L2 out of range: {s2}"
        assert 0 <= s3 <= config.breakout_retest.weight_volume, f"L3 out of range: {s3}"
        assert 0 <= s4 <= config.breakout_retest.weight_momentum, f"L4 out of range: {s4}"
        total = s1 + s2 + s3 + s4
        assert 0 <= total <= 100, f"Total out of range: {total}"

    run_test("TC-BRT-002: 4-Layer 스코어 범위", test_breakout_score_range)

    # TC-BRT-003: 페이크아웃 필터 — 저거래량 차단
    def test_fakeout_low_volume():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        # 마지막 봉 거래량을 매우 낮게 설정
        df.iloc[-1, df.columns.get_loc("volume")] = 10
        df.iloc[-1, df.columns.get_loc("volume_ma")] = 500000
        passed_filter, reason = strat._apply_fakeout_filters(df)
        assert not passed_filter, "Low volume should be blocked"
        assert reason == "ERR01_LOW_VOLUME"

    run_test("TC-BRT-003: 페이크아웃 저거래량 차단", test_fakeout_low_volume)

    # TC-BRT-004: 페이크아웃 필터 — 윅 트랩 차단
    def test_fakeout_wick_trap():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        # 마지막 봉: 긴 윗꼬리 (wick > body)
        idx = len(df) - 1
        df.iloc[idx, df.columns.get_loc("open")] = 120.0
        df.iloc[idx, df.columns.get_loc("close")] = 121.0  # body = 1
        df.iloc[idx, df.columns.get_loc("high")] = 125.0  # wick = 4 > body 1
        df.iloc[idx, df.columns.get_loc("volume")] = 500000
        df.iloc[idx, df.columns.get_loc("volume_ma")] = 300000
        passed_filter, reason = strat._apply_fakeout_filters(df)
        assert not passed_filter, "Wick trap should be blocked"
        assert reason == "ERR02_WICK_TRAP"

    run_test("TC-BRT-004: 페이크아웃 윅 트랩 차단", test_fakeout_wick_trap)

    # TC-BRT-005: 페이크아웃 필터 — 정상 통과
    def test_fakeout_pass():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        # 마지막 봉: 적절한 거래량 + 작은 윅
        idx = len(df) - 1
        df.iloc[idx, df.columns.get_loc("volume")] = 500000
        df.iloc[idx, df.columns.get_loc("volume_ma")] = 300000
        df.iloc[idx, df.columns.get_loc("open")] = 118.0
        df.iloc[idx, df.columns.get_loc("close")] = 122.0  # body = 4
        df.iloc[idx, df.columns.get_loc("high")] = 123.0   # wick = 1 < body 4
        passed_filter, reason = strat._apply_fakeout_filters(df)
        assert passed_filter, f"Should pass but blocked: {reason}"

    run_test("TC-BRT-005: 페이크아웃 필터 정상 통과", test_fakeout_pass)

    # TC-BRT-006: State Machine — IDLE → WAITING_RETEST 전이
    def test_state_transition():
        state = BreakoutState()
        assert state.phase == "IDLE"
        state.phase = "WAITING_RETEST"
        state.breakout_price = 105.0
        state.breakout_score = 75
        assert state.phase == "WAITING_RETEST"
        assert state.breakout_score == 75

    run_test("TC-BRT-006: State IDLE→WAITING_RETEST", test_state_transition)

    # TC-BRT-007: State Machine — 만료 (max bars 초과 → IDLE)
    def test_state_expiry():
        strat = BreakoutRetestStrategy(config)
        state = BreakoutState(phase="WAITING_RETEST", breakout_score=70)
        state.bars_since_breakout = config.breakout_retest.retest_max_bars + 1
        strat._breakout_states["TEST"] = state
        strat._expire_stale_breakouts()
        assert state.phase == "IDLE", f"Should expire but phase={state.phase}"

    run_test("TC-BRT-007: State 만료 → IDLE", test_state_expiry)

    # TC-BRT-008: 리테스트 존 캡처
    def test_retest_zone_capture():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        state = strat._capture_retest_zones(df, 120.0, 3.0)
        assert state.phase == "WAITING_RETEST"
        assert state.breakout_price == 120.0
        assert state.breakout_atr == 3.0
        # 존이 설정되어야 함
        assert state.zone_top > 0 or state.zone_bottom > 0, "Zone should be set"

    run_test("TC-BRT-008: 리테스트 존 캡처", test_retest_zone_capture)

    # TC-BRT-009: 리테스트 존 스코어링 — 존 내 가격
    def test_retest_zone_scoring():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="up")
        df = strat.calculate_indicators(df.copy())
        state = BreakoutState(
            phase="WAITING_RETEST",
            fvg_top=122.0, fvg_bottom=118.0,
            ob_top=121.0, ob_bottom=117.0,
            breakout_level=120.0,
            breakout_atr=3.0,
        )
        # 가격이 존 내에 있도록 설정
        df.iloc[-1, df.columns.get_loc("close")] = 119.0
        score = strat._score_retest_zone(df, state)
        assert score > 0, f"Zone score should be positive: {score}"

    run_test("TC-BRT-009: 리테스트 존 스코어링", test_retest_zone_scoring)

    # TC-BRT-010: 리테스트 — 존 하단 이탈 시 진입 거부
    def test_retest_below_zone():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="flat")
        df = strat.calculate_indicators(df.copy())
        state = BreakoutState(
            phase="WAITING_RETEST",
            breakout_price=120.0,
            breakout_score=75,
            zone_top=120.0,
            zone_bottom=118.0,
            breakout_atr=3.0,
        )
        # 가격을 존 아래로 설정
        df.iloc[-1, df.columns.get_loc("close")] = 110.0
        df.iloc[-1, df.columns.get_loc("low")] = 109.0
        signal = strat._check_retest("TEST", df, state)
        assert signal is None, "Should not enter below zone"
        assert state.phase == "IDLE", "Should reset to IDLE"

    run_test("TC-BRT-010: 존 하단 이탈 → 진입 거부", test_retest_below_zone)

    # TC-BRT-011: Exit ES1 하드 손절 -5%
    def test_exit_es1_stop():
        strat = BreakoutRetestStrategy(config)
        from common.types import PriceData

        class MockPosition:
            stock_code = "005930"
            stock_name = "삼성전자"
            position_id = "pos-001"
            entry_price = 100.0
            trailing_high = 100.0
            holding_days = 1

        pos = MockPosition()
        current_prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=94.0,  # -6% (below -5% threshold)
                open_price=100.0, high_price=100.0, low_price=94.0,
                prev_close=100.0, volume=100000, change_pct=-0.06,
                timestamp="2024-01-01",
            )
        }
        exits = strat.scan_exit_signals([pos], {}, current_prices)
        assert len(exits) == 1, f"Expected 1 exit signal, got {len(exits)}"
        assert exits[0].exit_type == "ES1", f"Expected ES1, got {exits[0].exit_type}"

    run_test("TC-BRT-011: Exit ES1 하드 손절", test_exit_es1_stop)

    # TC-BRT-012: Exit ATR SL (1.5배)
    def test_exit_atr_sl():
        strat = BreakoutRetestStrategy(config)
        from common.types import PriceData

        class MockPosition:
            stock_code = "005930"
            stock_name = "삼성전자"
            position_id = "pos-002"
            entry_price = 100.0
            trailing_high = 100.0
            holding_days = 1

        pos = MockPosition()
        # ATR = 2.0 → SL = 100 - 2*1.5 = 97.0, Floor = 95.0
        # Price = 96.5 → below ATR SL but above floor
        df = _make_ohlcv_df(n=150, trend="flat", base_price=96.5)
        df = strat.calculate_indicators(df.copy())
        # Force ATR
        df.iloc[-1, df.columns.get_loc("atr")] = 2.0

        current_prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=96.5,
                open_price=97.0, high_price=97.5, low_price=96.0,
                prev_close=97.0, volume=100000, change_pct=-0.005,
                timestamp="2024-01-01",
            )
        }
        exits = strat.scan_exit_signals([pos], {"005930": df}, current_prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES_BRT_SL"

    run_test("TC-BRT-012: Exit ATR SL (1.5배)", test_exit_atr_sl)

    # TC-BRT-013: Exit 보유기간 초과
    def test_exit_max_holding():
        strat = BreakoutRetestStrategy(config)
        from common.types import PriceData

        class MockPosition:
            stock_code = "005930"
            stock_name = "삼성전자"
            position_id = "pos-003"
            entry_price = 100.0
            trailing_high = 105.0
            holding_days = 35  # > max_holding_days 30

        pos = MockPosition()
        current_prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=103.0,
                open_price=102.0, high_price=104.0, low_price=101.0,
                prev_close=102.0, volume=100000, change_pct=0.01,
                timestamp="2024-01-01",
            )
        }
        exits = strat.scan_exit_signals([pos], {}, current_prices)
        assert len(exits) == 1, f"Expected 1 exit signal, got {len(exits)}"
        assert exits[0].exit_type == "ES5", f"Expected ES5, got {exits[0].exit_type}"

    run_test("TC-BRT-013: Exit 보유기간 초과", test_exit_max_holding)

    # TC-BRT-014: 횡보장 → 돌파 미감지
    def test_no_breakout_flat():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="flat")
        df = strat.calculate_indicators(df.copy())
        result = strat._detect_breakout("TEST", df)
        assert result is None, "Flat market should not detect breakout"

    run_test("TC-BRT-014: 횡보장 돌파 미감지", test_no_breakout_flat)

    # TC-BRT-015: 6조건 — 조건 카운트 검증
    def test_six_conditions_structure():
        strat = BreakoutRetestStrategy(config)
        df = _make_ohlcv_df(n=150, trend="flat")
        df = strat.calculate_indicators(df.copy())
        met_enough, met_list = strat._check_six_conditions(df)
        # 횡보장이므로 많은 조건이 충족되지 않을 것
        assert isinstance(met_list, list)
        assert isinstance(met_enough, bool)
        # 각 조건 이름이 유효한지 확인
        valid_conditions = {"C1_SQUEEZE", "C2_LIQ_SWEEP", "C3_DISPLACEMENT",
                           "C4_OBV_BREAK", "C5_ADX_RISING", "C6_FVG"}
        for c in met_list:
            assert c in valid_conditions, f"Unknown condition: {c}"

    run_test("TC-BRT-015: 6조건 구조 검증", test_six_conditions_structure)


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
    test_suite_breakout_retest()

    print("\n" + "=" * 60)
    print(f"결과: ✅ {passed} passed / ❌ {failed} failed / 총 {passed + failed}건")
    print("=" * 60)

    if errors:
        print("\n실패 상세:")
        for name, err in errors:
            print(f"\n  ❌ {name}")
            print(f"     {err[:200]}")

    sys.exit(0 if failed == 0 else 1)
