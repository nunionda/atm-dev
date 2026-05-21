"""
P1-1 회귀 보호: ESF intraday_backtester의 ES_HARD가 Entry sl_level과 정합.

핵심 단언:
  ES_HARD 분기는 봉 low/high(intraday OHLC) 기반으로 entry_price × (1 ± sl_hard_pct) 한도와 비교한다.
  → 갭 다운으로 봉 low가 hard_cap 아래로 떨어진 경우 정확히 캐치 (이전 close-based는 놓침).
  → 정상 시(entry_sl > hard_cap)에는 ES_ATR_SL이 먼저 발동되어 ES_HARD는 미발동.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────
# 1) 소스 레벨 단언: P1-1 패치 적용 확인
# ──────────────────────────────────────

def test_p1_1_patch_applied_in_backtester_source():
    """intraday_backtester._check_exit가 entry_price 기반 hard_cap_price 계산을 사용."""
    import backtest.intraday_backtester as bt
    src = inspect.getsource(bt._check_exit) if hasattr(bt, "_check_exit") else inspect.getsource(bt)
    assert "hard_cap_price" in src, (
        "P1-1 regression: intraday_backtester ES_HARD must compute hard_cap_price = "
        "entry_price × (1 ± sl_hard_pct), not close-based pnl_pct."
    )
    # close-based ES_HARD가 제거됐는지 (`pnl_pct < -self.ic.sl_hard_pct` 패턴 없음)
    assert "pnl_pct < -self.ic.sl_hard_pct" not in src, (
        "P1-1 regression: legacy close-based ES_HARD pattern should be replaced "
        "with OHLC low/high comparison."
    )


# ──────────────────────────────────────
# 2) 갭 다운 ES_HARD 정확 캐치 (low 기준)
# ──────────────────────────────────────

@dataclass
class MockPosition:
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    trailing_high: float = 0.0
    trailing_low: float = float("inf")
    trailing_active: bool = False


@dataclass
class MockIntradayConfig:
    sl_hard_pct: float = 0.015
    trailing_activation_pct: float = 0.01
    trailing_atr_mult: float = 1.5


def _make_bar(close, high=None, low=None, atr=10.0):
    high = high if high is not None else close
    low = low if low is not None else close
    return pd.Series({"close": close, "high": high, "low": low, "atr": atr})


def test_gap_down_triggers_hard_stop_via_low():
    """LONG 보유 중 다음 봉이 갭 다운 — 봉 low가 hard_cap_price 이하면 ES_HARD 발동.
    이전 close-based 로직은 close가 cap 위면 놓쳤지만, low-based는 정확 캐치."""
    from backtest.intraday_backtester import IntradayBacktester, IntradayPosition
    from common.enums import ExitReason

    # entry 5000, hard_cap = 5000 × (1 - 0.015) = 4925
    pos = IntradayPosition(
        ticker="ES=F",
        entry_time=pd.Timestamp("2026-05-21 09:30"),
        entry_price=5000.0,
        entry_bar_idx=0,
        direction="LONG",
        contracts=1,
        stop_loss=4960.0,   # atr 기반 -0.8% (hard_cap 위)
        take_profit=5050.0,
    )
    # bar: close=4950(hard_cap 위지만), low=4900(갭 다운 hard_cap 아래)
    bar = _make_bar(close=4950, high=4960, low=4900, atr=10)

    bt = IntradayBacktester.__new__(IntradayBacktester)
    bt.ic = MockIntradayConfig()
    reason = bt._check_exit(pos, bar, bar_idx=5, is_eod=False, session_halted=False)
    assert reason == ExitReason.HARD_STOP.value


def test_normal_bar_no_hard_stop_atr_sl_fires_first():
    """정상 시나리오: entry_sl(4960)이 hard_cap(4925)보다 위라 ES_ATR_SL 먼저 발동."""
    from backtest.intraday_backtester import IntradayBacktester, IntradayPosition
    from common.enums import ExitReason

    pos = IntradayPosition(
        ticker="ES=F",
        entry_time=pd.Timestamp("2026-05-21 09:30"),
        entry_price=5000.0,
        entry_bar_idx=0,
        direction="LONG",
        contracts=1,
        stop_loss=4960.0,
        take_profit=5050.0,
    )
    # bar: low=4955 (entry_sl 4960 아래, hard_cap 4925 위) → ES_ATR_SL
    bar = _make_bar(close=4958, high=4965, low=4955, atr=10)

    bt = IntradayBacktester.__new__(IntradayBacktester)
    bt.ic = MockIntradayConfig()
    reason = bt._check_exit(pos, bar, bar_idx=5, is_eod=False, session_halted=False)
    assert reason == ExitReason.ATR_STOP_LOSS.value


def test_short_gap_up_triggers_hard_stop_via_high():
    """SHORT 대칭: 봉 high가 entry × (1 + sl_hard_pct) 이상이면 ES_HARD."""
    from backtest.intraday_backtester import IntradayBacktester, IntradayPosition
    from common.enums import ExitReason

    # entry 5000, hard_cap = 5075
    pos = IntradayPosition(
        ticker="ES=F",
        entry_time=pd.Timestamp("2026-05-21 09:30"),
        entry_price=5000.0,
        entry_bar_idx=0,
        direction="SHORT",
        contracts=1,
        stop_loss=5040.0,
        take_profit=4950.0,
    )
    # bar: close=5050(cap 아래), high=5100(cap 위)
    bar = _make_bar(close=5050, high=5100, low=5040, atr=10)

    bt = IntradayBacktester.__new__(IntradayBacktester)
    bt.ic = MockIntradayConfig()
    reason = bt._check_exit(pos, bar, bar_idx=5, is_eod=False, session_halted=False)
    assert reason == ExitReason.HARD_STOP.value


def test_quiet_bar_no_exit():
    """정상 보유 중인 봉은 어떤 exit도 발동 안 함."""
    from backtest.intraday_backtester import IntradayBacktester, IntradayPosition

    pos = IntradayPosition(
        ticker="ES=F",
        entry_time=pd.Timestamp("2026-05-21 09:30"),
        entry_price=5000.0,
        entry_bar_idx=0,
        direction="LONG",
        contracts=1,
        stop_loss=4960.0,
        take_profit=5050.0,
    )
    bar = _make_bar(close=5005, high=5010, low=4995, atr=10)

    bt = IntradayBacktester.__new__(IntradayBacktester)
    bt.ic = MockIntradayConfig()
    reason = bt._check_exit(pos, bar, bar_idx=5, is_eod=False, session_halted=False)
    assert reason is None
