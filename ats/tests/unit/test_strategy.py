"""
strategy/momentum_swing.py 단위 테스트
TC-STR-001 ~ TC-STR-010: 시그널 생성 로직 검증 (BRD §2)
"""

import pytest
import pandas as pd
import numpy as np
from common.types import PriceData, Signal
from infra.db.models import Position
from strategy.momentum_swing import MomentumSwingStrategy


class TestCalculateIndicators:
    """TC-STR-001: 기술적 지표 계산 검증."""

    def test_indicators_added_to_dataframe(self, config, sample_ohlcv):
        """지표 컬럼이 정상적으로 추가되는지."""
        strategy = MomentumSwingStrategy(config)
        df = strategy.calculate_indicators(sample_ohlcv.copy())

        expected_cols = [
            "ma_short", "ma_long",
            "macd_line", "macd_signal", "macd_hist",
            "rsi",
            "bb_upper", "bb_lower", "bb_middle",
            "volume_ma",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_ma_values_reasonable(self, config, sample_ohlcv):
        """이동평균선 값이 합리적인 범위인지."""
        strategy = MomentumSwingStrategy(config)
        df = strategy.calculate_indicators(sample_ohlcv.copy())

        last = df.iloc[-1]
        assert 60000 < last["ma_short"] < 90000
        assert 60000 < last["ma_long"] < 90000

    def test_rsi_range(self, config, sample_ohlcv):
        """RSI가 0~100 범위인지."""
        strategy = MomentumSwingStrategy(config)
        df = strategy.calculate_indicators(sample_ohlcv.copy())

        valid_rsi = df["rsi"].dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_bb_upper_above_lower(self, config, sample_ohlcv):
        """볼린저밴드 상단 > 하단."""
        strategy = MomentumSwingStrategy(config)
        df = strategy.calculate_indicators(sample_ohlcv.copy())

        valid = df.dropna(subset=["bb_upper", "bb_lower"])
        assert (valid["bb_upper"] > valid["bb_lower"]).all()

    def test_empty_dataframe(self, config):
        """빈 DataFrame 입력 시 빈 DataFrame 반환."""
        strategy = MomentumSwingStrategy(config)
        df = strategy.calculate_indicators(pd.DataFrame())
        assert df.empty

    def test_short_dataframe(self, config):
        """데이터 부족 시 (< ma_long) 원본 반환."""
        strategy = MomentumSwingStrategy(config)
        short_df = pd.DataFrame({
            "close": [70000, 71000, 72000],
            "volume": [1000000, 1100000, 1200000],
        })
        df = strategy.calculate_indicators(short_df)
        assert len(df) == 3


class TestScanEntrySignals:
    """TC-STR-002 ~ TC-STR-005: 매수 시그널 스캔 검증."""

    def test_returns_signals_list(self, config, sample_ohlcv):
        """TC-STR-002: 반환값이 Signal 리스트인지."""
        strategy = MomentumSwingStrategy(config)
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=77000.0, open_price=76000, high_price=77500,
                low_price=75500, prev_close=76000, volume=25000000,
                change_pct=1.3, timestamp="2026-02-25T10:00:00",
            ),
        }
        signals = strategy.scan_entry_signals(
            ["005930"], {"005930": sample_ohlcv}, prices
        )
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, Signal)

    def test_no_signal_on_insufficient_data(self, config):
        """TC-STR-003: 데이터 부족 시 시그널 없음."""
        strategy = MomentumSwingStrategy(config)
        short_df = pd.DataFrame({
            "date": ["20260101"] * 5,
            "open": [70000] * 5,
            "high": [71000] * 5,
            "low": [69000] * 5,
            "close": [70500] * 5,
            "volume": [1000000] * 5,
        })
        signals = strategy.scan_entry_signals(["005930"], {"005930": short_df}, {})
        assert len(signals) == 0

    def test_signals_sorted_by_strength(self, config, sample_ohlcv):
        """TC-STR-004: 시그널 강도 내림차순 정렬."""
        strategy = MomentumSwingStrategy(config)

        # 두 종목 제공
        prices = {}
        ohlcv = {}
        for code in ["005930", "000660"]:
            ohlcv[code] = sample_ohlcv.copy()
            prices[code] = PriceData(
                stock_code=code, stock_name=f"종목_{code}",
                current_price=77000.0, open_price=76000, high_price=77500,
                low_price=75500, prev_close=76000, volume=25000000,
                change_pct=1.3, timestamp="2026-02-25T10:00:00",
            )

        signals = strategy.scan_entry_signals(
            ["005930", "000660"], ohlcv, prices
        )
        if len(signals) > 1:
            for i in range(len(signals) - 1):
                assert signals[i].strength >= signals[i + 1].strength

    def test_missing_stock_in_ohlcv_skipped(self, config):
        """TC-STR-005: OHLCV에 없는 종목은 스킵."""
        strategy = MomentumSwingStrategy(config)
        signals = strategy.scan_entry_signals(
            ["999999"], {}, {}
        )
        assert len(signals) == 0


class TestScanExitSignals:
    """TC-STR-006 ~ TC-STR-010: 청산 시그널 스캔 검증."""

    def _make_position(self, entry_price=70000, holding_days=3):
        """테스트용 포지션 객체."""
        pos = Position(
            position_id="pos_test",
            stock_code="005930",
            stock_name="삼성전자",
            status="ACTIVE",
            entry_price=entry_price,
            quantity=20,
            stop_loss_price=entry_price * 0.97,
            take_profit_price=entry_price * 1.07,
            trailing_high=entry_price * 1.02,
            trailing_stop_price=entry_price * 1.02 * 0.97,
            holding_days=holding_days,
            created_at="2026-02-20T09:30:00",
            updated_at="2026-02-25T09:30:00",
        )
        return pos

    def test_stop_loss_triggered(self, config, sample_ohlcv):
        """TC-STR-006: 손절 시그널 (ES1) — 현재가 ≤ 매수가 × 0.97."""
        strategy = MomentumSwingStrategy(config)
        pos = self._make_position(entry_price=70000)

        # 현재가 67000 → 손절가 67900 이하
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=67000.0, open_price=68000, high_price=68500,
                low_price=66500, prev_close=69000, volume=20000000,
                change_pct=-2.9, timestamp="2026-02-25T10:00:00",
            ),
        }

        exits = strategy.scan_exit_signals([pos], {"005930": sample_ohlcv}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES1"
        assert exits[0].order_type == "MARKET"

    def test_take_profit_triggered(self, config, sample_ohlcv):
        """TC-STR-007: 익절 시그널 (ES2) — 현재가 ≥ 매수가 × 1.07."""
        strategy = MomentumSwingStrategy(config)
        pos = self._make_position(entry_price=70000)

        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=75000.0, open_price=74000, high_price=75500,
                low_price=73500, prev_close=74000, volume=18000000,
                change_pct=1.35, timestamp="2026-02-25T10:00:00",
            ),
        }

        exits = strategy.scan_exit_signals([pos], {"005930": sample_ohlcv}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES2"

    def test_stop_loss_priority_over_take_profit(self, config, sample_ohlcv):
        """TC-STR-008: 손절이 익절보다 우선순위 높음 (동시 해당 불가지만 로직 확인)."""
        strategy = MomentumSwingStrategy(config)
        pos = self._make_position(entry_price=70000)

        # 현재가가 손절 조건에 해당
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=67000.0, open_price=68000, high_price=68500,
                low_price=66500, prev_close=69000, volume=20000000,
                change_pct=-2.9, timestamp="2026-02-25T10:00:00",
            ),
        }

        exits = strategy.scan_exit_signals([pos], {"005930": sample_ohlcv}, prices)
        # ES1이 먼저 매칭되므로 ES2 이하는 체크되지 않음
        assert exits[0].exit_type == "ES1"

    def test_max_holding_days_triggered(self, config, sample_ohlcv):
        """TC-STR-009: 보유기간 초과 (ES5) — 11일 보유."""
        strategy = MomentumSwingStrategy(config)
        pos = self._make_position(entry_price=70000, holding_days=11)

        # 현재가 정상 범위 (ES1~ES4 해당 없음)
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=71000.0, open_price=70500, high_price=71500,
                low_price=70000, prev_close=70800, volume=12000000,
                change_pct=0.28, timestamp="2026-02-25T10:00:00",
            ),
        }

        exits = strategy.scan_exit_signals([pos], {"005930": sample_ohlcv}, prices)
        assert len(exits) == 1
        assert exits[0].exit_type == "ES5"
        assert exits[0].order_type == "LIMIT"

    def test_hold_when_no_exit_condition(self, config, sample_ohlcv):
        """TC-STR-010: 청산 조건 미해당 시 시그널 없음 (HOLD)."""
        strategy = MomentumSwingStrategy(config)
        pos = self._make_position(entry_price=70000, holding_days=3)

        # 현재가 70500 — 모든 청산 조건 미해당
        prices = {
            "005930": PriceData(
                stock_code="005930", stock_name="삼성전자",
                current_price=70500.0, open_price=70000, high_price=71000,
                low_price=69800, prev_close=70200, volume=10000000,
                change_pct=0.43, timestamp="2026-02-25T10:00:00",
            ),
        }

        exits = strategy.scan_exit_signals([pos], {"005930": sample_ohlcv}, prices)
        assert len(exits) == 0
