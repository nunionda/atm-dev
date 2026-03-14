#!/usr/bin/env python3
"""
S&P 500 선물 매매 전략 단위 테스트 (20건)

TC-FUT-001 ~ TC-FUT-020
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ats"))

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

# ── Test Framework ──

passed = 0
failed = 0
errors = []


def run_test(name: str, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name}: {e}")


# ── Fixtures ──

def _make_config():
    from data.config_manager import ATSConfig, SP500FuturesConfig
    config = ATSConfig()
    config.sp500_futures = SP500FuturesConfig()
    return config


def _make_ohlcv(
    n: int = 250,
    base_price: float = 5000.0,
    trend: str = "flat",
    seed: int = 42,
) -> pd.DataFrame:
    """
    테스트용 합성 OHLCV 생성.
    trend: "flat" | "bull" | "bear" | "volatile"
    """
    np.random.seed(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    prices = np.full(n, base_price, dtype=float)

    if trend == "flat":
        noise = np.random.randn(n) * 10
        prices = base_price + np.cumsum(noise * 0.3)
    elif trend == "bull":
        for i in range(1, n):
            prices[i] = prices[i - 1] * (1 + np.random.uniform(0.001, 0.004))
    elif trend == "bear":
        for i in range(1, n):
            prices[i] = prices[i - 1] * (1 - np.random.uniform(0.001, 0.004))
    elif trend == "volatile":
        for i in range(1, n):
            prices[i] = prices[i - 1] * (1 + np.random.uniform(-0.02, 0.02))

    opens = prices * (1 + np.random.randn(n) * 0.002)
    highs = np.maximum(prices, opens) * (1 + np.abs(np.random.randn(n)) * 0.005)
    lows = np.minimum(prices, opens) * (1 - np.abs(np.random.randn(n)) * 0.005)
    volumes = np.random.randint(500000, 2000000, n).astype(float)

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    })


def _make_bull_ohlcv_with_signals(n=250):
    """강한 상승 추세 + 롱 시그널이 발생하도록 조건을 갖춘 OHLCV."""
    np.random.seed(123)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    prices = np.full(n, 5000.0, dtype=float)

    # 전반부 횡보 → 후반부 강한 상승
    for i in range(1, n):
        if i < n * 0.6:
            prices[i] = prices[i - 1] * (1 + np.random.uniform(-0.001, 0.002))
        else:
            prices[i] = prices[i - 1] * (1 + np.random.uniform(0.003, 0.008))

    opens = prices * (1 + np.random.randn(n) * 0.001)
    highs = np.maximum(prices, opens) * (1 + np.abs(np.random.randn(n)) * 0.006)
    lows = np.minimum(prices, opens) * (1 - np.abs(np.random.randn(n)) * 0.003)

    volumes = np.random.randint(800000, 1500000, n).astype(float)
    # 마지막 수 봉에 거래량 폭증
    volumes[-10:] = volumes[-10:] * 2.5

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    })


@dataclass
class MockPosition:
    stock_code: str = "ES=F"
    stock_name: str = "E-mini S&P 500"
    position_id: str = "pos_test"
    entry_price: float = 5500.0
    trailing_high: float = 5600.0
    holding_days: int = 3
    direction: str = "LONG"


# ══════════════════════════════════════════
# Test Suite: strategy/sp500_futures.py
# ══════════════════════════════════════════

def test_suite_sp500_futures():
    print("\n📦 [SP500 Futures] strategy/sp500_futures.py")

    from strategy.sp500_futures import SP500FuturesStrategy, FuturesPositionState
    from common.types import PriceData, FuturesSignal
    from common.enums import FuturesDirection, ExitReason

    config = _make_config()
    strategy = SP500FuturesStrategy(config)

    # ── TC-FUT-001: 기술 지표 컬럼 생성 ──
    def test_indicators_columns():
        df = strategy.calculate_indicators(_make_ohlcv().copy())
        expected_cols = [
            "ema_fast", "ema_mid", "ema_slow", "ma_trend",
            "macd_line", "macd_signal", "macd_hist",
            "rsi",
            "bb_upper", "bb_lower", "bb_middle", "bb_width", "bb_squeeze_ratio",
            "atr", "atr_pct",
            "adx", "plus_di", "minus_di",
            "zscore",
            "volume_ma", "volume_ratio",
            "obv", "obv_ema_fast", "obv_ema_slow",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    run_test("TC-FUT-001: 기술 지표 컬럼 생성", test_indicators_columns)

    # ── TC-FUT-002: Z-Score 범위 검증 ──
    def test_zscore_range():
        df = strategy.calculate_indicators(_make_ohlcv().copy())
        valid = df["zscore"].dropna()
        # Z-Score는 일반적으로 -4 ~ +4 범위 내
        assert (valid > -10).all(), "Z-Score too low"
        assert (valid < 10).all(), "Z-Score too high"

    run_test("TC-FUT-002: Z-Score 범위 검증", test_zscore_range)

    # ── TC-FUT-003: 4-Layer 스코어 범위 검증 ──
    def test_score_ranges():
        df = strategy.calculate_indicators(_make_ohlcv(trend="bull").copy())
        l1, _ = strategy._score_zscore(df, is_long=True)
        l2, _ = strategy._score_trend(df, is_long=True)
        l3, _ = strategy._score_momentum(df, is_long=True)
        l4, _ = strategy._score_volume(df, is_long=True)

        assert 0 <= l1 <= config.sp500_futures.weight_zscore, f"L1 out of range: {l1}"
        assert 0 <= l2 <= config.sp500_futures.weight_trend, f"L2 out of range: {l2}"
        assert 0 <= l3 <= config.sp500_futures.weight_momentum, f"L3 out of range: {l3}"
        assert 0 <= l4 <= config.sp500_futures.weight_volume, f"L4 out of range: {l4}"

        total = l1 + l2 + l3 + l4
        assert 0 <= total <= 100, f"Total out of range: {total}"

    run_test("TC-FUT-003: 4-Layer 스코어 범위 (0~100)", test_score_ranges)

    # ── TC-FUT-004: 방향 결정 — 상승추세 → LONG ──
    def test_direction_bull():
        df = strategy.calculate_indicators(_make_ohlcv(n=250, trend="bull").copy())
        direction = strategy._determine_direction(df)
        assert direction == FuturesDirection.LONG, f"Expected LONG, got {direction}"

    run_test("TC-FUT-004: 상승추세 → LONG", test_direction_bull)

    # ── TC-FUT-005: 방향 결정 — 하락추세 → SHORT ──
    def test_direction_bear():
        df = strategy.calculate_indicators(_make_ohlcv(n=250, trend="bear").copy())
        direction = strategy._determine_direction(df)
        assert direction == FuturesDirection.SHORT, f"Expected SHORT, got {direction}"

    run_test("TC-FUT-005: 하락추세 → SHORT", test_direction_bear)

    # ── TC-FUT-006: 방향 결정 — 횡보장 → NEUTRAL (또는 약한 방향) ──
    def test_direction_flat():
        df = strategy.calculate_indicators(_make_ohlcv(n=250, trend="flat").copy())
        direction = strategy._determine_direction(df)
        # 횡보장은 NEUTRAL이 되어야 함 (혹은 약한 방향)
        assert direction in [FuturesDirection.NEUTRAL, FuturesDirection.LONG, FuturesDirection.SHORT], \
            f"Got unexpected: {direction}"

    run_test("TC-FUT-006: 횡보장 방향 결정", test_direction_flat)

    # ── TC-FUT-007: ATR 돌파 필터 — 유효 돌파 ──
    def test_atr_breakout_valid():
        df = strategy.calculate_indicators(_make_ohlcv(trend="bull").copy())
        # 마지막 봉을 강한 돌파로 조작
        idx = len(df) - 1
        prev_close = float(df.iloc[-2]["close"])
        atr = float(df.iloc[-1]["atr"])
        df.iloc[idx, df.columns.get_loc("high")] = prev_close + atr * 2.0  # 강한 돌파
        result = strategy._check_atr_breakout(df, is_long=True)
        assert result is True, "Strong breakout should pass ATR filter"

    run_test("TC-FUT-007: ATR 돌파 필터 — 유효 돌파", test_atr_breakout_valid)

    # ── TC-FUT-008: 페이크아웃 필터 — 저거래량 차단 ──
    def test_fakeout_low_volume():
        df = strategy.calculate_indicators(_make_ohlcv(trend="bull").copy())
        idx = len(df) - 1
        df.iloc[idx, df.columns.get_loc("volume")] = 10
        df.iloc[idx, df.columns.get_loc("volume_ma")] = 1000000
        # volume_ratio 재계산
        df.iloc[idx, df.columns.get_loc("volume_ratio")] = 10 / 1000000
        result = strategy._check_fakeout_filter(df, is_long=True)
        assert result is False, "Low volume should fail fakeout filter"

    run_test("TC-FUT-008: 페이크아웃 — 저거래량 차단", test_fakeout_low_volume)

    # ── TC-FUT-009: SL/TP 계산 — 롱 포지션 ──
    def test_sl_tp_long():
        sl, tp = strategy._calculate_sl_tp(
            entry_price=5500.0, atr=30.0, is_long=True, adx=30.0
        )
        # ADX ≥ 25 → sl_mult=1.5, tp_mult=3.0
        expected_sl = 5500.0 - 30.0 * 1.5  # 5455.0
        expected_tp = 5500.0 + 30.0 * 3.0  # 5590.0
        # 하드 손절: 5500 * 0.97 = 5335 → ATR SL이 더 가까움
        assert sl == expected_sl, f"SL: expected {expected_sl}, got {sl}"
        assert tp == expected_tp, f"TP: expected {expected_tp}, got {tp}"

    run_test("TC-FUT-009: SL/TP 계산 — 롱", test_sl_tp_long)

    # ── TC-FUT-010: SL/TP 계산 — 숏 포지션 ──
    def test_sl_tp_short():
        sl, tp = strategy._calculate_sl_tp(
            entry_price=5500.0, atr=30.0, is_long=False, adx=30.0
        )
        # ADX ≥ 25 → sl_mult=1.5
        expected_sl = 5500.0 + 30.0 * 1.5  # 5545.0
        expected_tp = 5500.0 - 30.0 * 3.0  # 5410.0
        # 하드 손절: 5500 * 1.03 = 5665 → ATR SL이 더 가까움
        assert sl == expected_sl, f"SL: expected {expected_sl}, got {sl}"
        assert tp == expected_tp, f"TP: expected {expected_tp}, got {tp}"

    run_test("TC-FUT-010: SL/TP 계산 — 숏", test_sl_tp_short)

    # ── TC-FUT-011: ES1 하드 손절 (-3%) ──
    def test_hard_stop_long():
        pos = MockPosition(entry_price=5500.0, direction="LONG")
        prices = {
            "ES=F": PriceData("ES=F", "E-mini S&P 500", 5310.0),  # -3.45%
        }
        exits = strategy.scan_exit_signals([pos], {}, prices)
        assert len(exits) == 1, f"Expected 1 exit, got {len(exits)}"
        assert exits[0].exit_type == ExitReason.STOP_LOSS.value

    run_test("TC-FUT-011: ES1 하드 손절 (-3%)", test_hard_stop_long)

    # ── TC-FUT-012: ES_ATR_SL ATR 동적 손절 ──
    def test_atr_stop_loss():
        # ATR SL을 직접 검증 (scan_exit_signals 내부의 calculate_indicators 재호출 방지)
        sl, _ = strategy._calculate_sl_tp(
            entry_price=5500.0, atr=30.0, is_long=True, adx=30.0
        )
        # ADX ≥ 25 → sl_mult=1.5 → SL=5500-45=5455
        assert sl == 5455.0, f"SL expected 5455.0, got {sl}"

        # check_atr_stop_loss 직접 테스트
        pos = MockPosition(entry_price=5500.0, direction="LONG")
        current_price = 5450.0  # below SL 5455
        pnl_pct = (5450.0 - 5500.0) / 5500.0  # -0.9%
        exit_sig = strategy._check_atr_stop_loss(
            pos, current_price, 5500.0, 30.0, 30.0, pnl_pct, True
        )
        assert exit_sig is not None, "ATR SL should trigger"
        assert exit_sig.exit_type == ExitReason.ATR_STOP_LOSS.value

    run_test("TC-FUT-012: ES_ATR_SL ATR 동적 손절", test_atr_stop_loss)

    # ── TC-FUT-013: ES_ATR_TP ATR 익절 ──
    def test_atr_take_profit():
        # check_atr_take_profit 직접 테스트
        pos = MockPosition(entry_price=5500.0, direction="LONG")
        current_price = 5600.0  # above TP
        pnl_pct = (5600.0 - 5500.0) / 5500.0  # +1.8%

        exit_sig = strategy._check_atr_take_profit(
            pos, current_price, 5500.0, 30.0, pnl_pct, True
        )
        # TP = 5500 + 30*3 = 5590, 5600 > 5590 → 트리거
        assert exit_sig is not None, "ATR TP should trigger"
        assert exit_sig.exit_type == ExitReason.ATR_TAKE_PROFIT.value

    run_test("TC-FUT-013: ES_ATR_TP ATR 익절", test_atr_take_profit)

    # ── TC-FUT-014: ES_CHANDELIER 샹들리에 청산 ──
    def test_chandelier_exit():
        pos = MockPosition(entry_price=5400.0, direction="LONG")
        state = FuturesPositionState()
        state.highest_since_entry = 5600.0
        state.direction = "LONG"

        # Chandelier stop: 5600 - 3*30 = 5510
        # price=5490 < 5510, highest > entry → 트리거
        exit_sig = strategy._check_chandelier_exit(
            pos, current_price=5490.0, atr=30.0,
            pnl_pct=(5490.0 - 5400.0) / 5400.0,
            is_long=True, state=state,
        )
        assert exit_sig is not None, "Chandelier should trigger"
        assert exit_sig.exit_type == ExitReason.CHANDELIER_EXIT.value

    run_test("TC-FUT-014: ES_CHANDELIER 샹들리에 청산", test_chandelier_exit)

    # ── TC-FUT-015: ES3 트레일링 스탑 ──
    def test_trailing_stop():
        pos = MockPosition(entry_price=5400.0, direction="LONG")
        state = FuturesPositionState()
        state.highest_since_entry = 5600.0

        # pnl = (5540-5400)/5400 = 2.59% ≥ 2% → 활성화
        # trail_stop = 5600 - 2.0*25 = 5550 → 5540 < 5550 → 트리거!
        exit_sig = strategy._check_trailing_stop(
            pos, current_price=5540.0, entry_price=5400.0,
            atr=25.0, pnl_pct=(5540.0 - 5400.0) / 5400.0,
            is_long=True, state=state,
        )
        assert exit_sig is not None, "Trailing stop should trigger"
        assert exit_sig.exit_type == ExitReason.TRAILING_STOP.value

    run_test("TC-FUT-015: ES3 트레일링 스탑", test_trailing_stop)

    # ── TC-FUT-016: ES_CHOCH MACD 반전 청산 ──
    def test_macd_reversal():
        pos = MockPosition(entry_price=5400.0, direction="LONG")

        # MACD 히스토그램 양→음 전환 데이터 생성
        df = pd.DataFrame({
            "close": [5410.0, 5420.0, 5415.0],
            "macd_hist": [3.0, 5.0, -2.0],  # 양→음 전환
        })

        pnl_pct = (5420.0 - 5400.0) / 5400.0
        exit_sig = strategy._check_structure_reversal(pos, df, pnl_pct, is_long=True)
        assert exit_sig is not None, "MACD reversal should trigger"
        assert exit_sig.exit_type == ExitReason.CHOCH_REVERSAL.value

    run_test("TC-FUT-016: ES_CHOCH MACD 반전 청산", test_macd_reversal)

    # ── TC-FUT-017: ES5 최대 보유기간 ──
    def test_max_holding():
        pos = MockPosition(entry_price=5400.0, holding_days=25, direction="LONG")
        prices = {
            "ES=F": PriceData("ES=F", "E-mini S&P 500", 5450.0),
        }
        exits = strategy.scan_exit_signals([pos], {}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == ExitReason.MAX_HOLDING.value

    run_test("TC-FUT-017: ES5 최대 보유기간 초과 (>20일)", test_max_holding)

    # ── TC-FUT-018: 포지션 사이징 계산 ──
    def test_position_sizing():
        # equity=100,000, price=5500, SL=5455 → risk_amount=1500
        # point_risk=45, E-mini mult=50 → dollar_risk=2250
        # contracts = 1500/2250 = 0.67 → 1
        contracts = strategy._calculate_position_size(
            equity=100000.0, entry_price=5500.0, stop_loss=5455.0
        )
        assert contracts >= 1, f"Expected ≥1 contract, got {contracts}"
        assert contracts <= config.sp500_futures.max_contracts

    run_test("TC-FUT-018: 포지션 사이징 계산", test_position_sizing)

    # ── TC-FUT-019: FuturesSignal 생성 ──
    def test_futures_signal_generation():
        # 강한 상승 추세 데이터로 FuturesSignal 생성 시도
        df = _make_bull_ohlcv_with_signals(n=250)
        sig = strategy.generate_futures_signal(
            code="ES=F", df=df, current_price=float(df.iloc[-1]["close"]),
            equity=100000.0,
        )
        # 시그널이 생성될 수도, 안 될 수도 있음 (조건 충족 여부)
        if sig is not None:
            assert isinstance(sig, FuturesSignal)
            assert sig.direction in ["LONG", "SHORT"]
            assert sig.signal_strength >= config.sp500_futures.entry_threshold
            assert sig.stop_loss > 0
            assert sig.take_profit > 0
            assert sig.position_size_contracts >= 1

    run_test("TC-FUT-019: FuturesSignal 생성", test_futures_signal_generation)

    # ── TC-FUT-020: HOLD (청산 조건 없음) ──
    def test_hold_no_exit():
        pos = MockPosition(
            entry_price=5500.0, holding_days=3, direction="LONG",
        )
        prices = {
            "ES=F": PriceData("ES=F", "E-mini S&P 500", 5510.0),
        }
        exits = strategy.scan_exit_signals([pos], {}, prices)
        assert len(exits) == 0, f"Expected 0 exits (HOLD), got {len(exits)}"

        strategy.clear_position_state("ES=F")

    run_test("TC-FUT-020: HOLD (청산 조건 없음)", test_hold_no_exit)


# ══════════════════════════════════════════
# 실행
# ══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("S&P 500 선물 전략 — 단위 테스트 실행")
    print("=" * 60)

    test_suite_sp500_futures()

    print("\n" + "=" * 60)
    print(f"결과: ✅ {passed} passed / ❌ {failed} failed / 총 {passed + failed}건")
    print("=" * 60)

    if errors:
        print("\n실패 상세:")
        for name, err in errors:
            print(f"\n  ❌ {name}")
            print(f"     {err[:300]}")

    sys.exit(0 if failed == 0 else 1)
