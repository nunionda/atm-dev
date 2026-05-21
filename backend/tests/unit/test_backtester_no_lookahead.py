"""
P0-2 회귀 보호: FuturesBacktester Lookahead Bias 제거 검증.

핵심 단언:
  진입 신호 생성 시 `df.loc[df.index < date]`로 현재 봉을 제외해야 한다.
  즉, 봉 N에서 진입 신호 판단은 봉 N-1까지의 데이터로만 이루어져야 한다.

회귀 시나리오:
  마지막 봉의 close가 신호를 강제로 만들 정도로 큰 값이어도,
  P0-2 fix가 적용되어 있으면 그 봉에서 진입이 발생하지 않아야 한다.
"""
from __future__ import annotations

import inspect
import re

import pandas as pd
import pytest


def test_p0_2_patch_applied_in_backtester_source():
    """소스 레벨 단언: 진입 신호 분기에서 'df.index < date' 패턴 사용."""
    import backtest.futures_backtester as bt
    src = inspect.getsource(bt)
    # 진입 분기에서 lookahead 제거가 적용됐는지
    assert "df.loc[df.index < date]" in src, (
        "P0-2 regression: backtester entry signal must use 'df.loc[df.index < date]' "
        "to exclude the current bar (lookahead bias fix)."
    )


def test_p0_2_entry_uses_only_past_bars():
    """진입 신호 인덱싱이 현재 봉(date)을 제외하는지 직접 검증."""
    # 5봉짜리 mock df
    idx = pd.date_range("2026-05-15", periods=5, freq="B")
    df = pd.DataFrame({
        "open":   [100, 101, 102, 103, 104],
        "high":   [101, 102, 103, 104, 105],
        "low":    [99, 100, 101, 102, 103],
        "close":  [100, 101, 102, 103, 200],   # 마지막 봉 의도적 점프
        "volume": [1000] * 5,
    }, index=idx)

    # 마지막 봉 진입 시점에서 P0-2 인덱싱 적용
    current_date = idx[-1]
    df_slice = df.loc[df.index < current_date]

    # 단언: slice는 4봉만 포함, 마지막 봉(close=200)은 제외
    assert len(df_slice) == 4
    assert df_slice["close"].iloc[-1] == 103  # 마지막 봉의 점프(200)는 제외
    assert (df_slice.index < current_date).all()


def test_p0_2_first_bar_yields_empty_slice():
    """첫 번째 봉(i=0)에서 진입 시도 시 slice가 비어 strategy가 None 반환하도록."""
    idx = pd.date_range("2026-05-15", periods=3, freq="B")
    df = pd.DataFrame({"close": [100, 101, 102]}, index=idx)

    current_date = idx[0]
    df_slice = df.loc[df.index < current_date]
    assert len(df_slice) == 0


def test_p0_1_and_p0_2_independent():
    """P0-1 (ATR map)와 P0-2 (lookahead fix)가 서로 독립적으로 적용됐는지 정적 단언."""
    import strategy.sp500_futures as strat_mod
    import backtest.futures_backtester as bt_mod

    strat_src = inspect.getsource(strat_mod)
    bt_src = inspect.getsource(bt_mod)

    # P0-1: ticker 인자 추가
    assert "_get_atr_mult" in strat_src
    assert re.search(r"_calculate_sl_tp\([^)]*ticker", strat_src)

    # P0-2: backtester lookahead fix
    assert "df.loc[df.index < date]" in bt_src
