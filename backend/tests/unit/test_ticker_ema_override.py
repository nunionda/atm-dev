"""F3 — Per-ticker EMA period override 단위 테스트.

목표:
- ES/NQ ticker: ic.ema_fast/mid/slow (8/21/55) 사용
- CL/GC ticker: spec override 5/13/34 사용
- 미정의 ticker / None: ic.ema_* fallback
- IntradayBacktester 인스턴스 attr (self.ema_*) 동일 적용
"""
from __future__ import annotations

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pandas as pd

from data.config_manager import ATSConfig
from strategy.intraday_ticker_specs import get_intraday_spec


# ─────────────────────────── spec map values ───────────────────────────


def test_equity_index_no_ema_override():
    """ES/MES/NQ/MNQ spec에 ema_fast/mid/slow 키 없음 (ic fallback)."""
    for tk in ("ES=F", "MES=F", "NQ=F", "MNQ=F"):
        spec = get_intraday_spec(tk)
        assert spec is not None
        # NotRequired field 미포함
        assert "ema_fast" not in spec
        assert "ema_mid" not in spec
        assert "ema_slow" not in spec


def test_commodity_has_fibonacci_ema():
    """CL/MCL/GC/MGC spec에 5/13/34 EMA override."""
    for tk in ("CL=F", "MCL=F", "GC=F", "MGC=F"):
        spec = get_intraday_spec(tk)
        assert spec is not None
        assert spec.get("ema_fast") == 5, f"{tk}: ema_fast expected 5"
        assert spec.get("ema_mid") == 13, f"{tk}: ema_mid expected 13"
        assert spec.get("ema_slow") == 34, f"{tk}: ema_slow expected 34"


# ─────────────────────────── IntradayBacktester attrs ───────────────────────────


def test_backtester_es_uses_config_ema():
    """ES=F: self.ema_* = ic.ema_* (8/21/55 default)."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="ES=F")
    assert bt.ema_fast == cfg.esf_intraday.ema_fast
    assert bt.ema_mid == cfg.esf_intraday.ema_mid
    assert bt.ema_slow == cfg.esf_intraday.ema_slow
    # 기본값 검증
    assert bt.ema_fast == 8
    assert bt.ema_mid == 21
    assert bt.ema_slow == 55


def test_backtester_cl_uses_fibonacci():
    """CL=F: self.ema_* = 5/13/34 (spec override)."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="CL=F")
    assert bt.ema_fast == 5
    assert bt.ema_mid == 13
    assert bt.ema_slow == 34


def test_backtester_gc_uses_fibonacci():
    """GC=F: self.ema_* = 5/13/34."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="GC=F")
    assert bt.ema_fast == 5
    assert bt.ema_mid == 13
    assert bt.ema_slow == 34


def test_backtester_micro_commodity_consistent():
    """MCL/MGC도 동일 spec 적용."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    for tk in ("MCL=F", "MGC=F"):
        bt = IntradayBacktester(cfg, ticker=tk)
        assert bt.ema_fast == 5, f"{tk}"
        assert bt.ema_mid == 13
        assert bt.ema_slow == 34


def test_backtester_unknown_falls_back():
    """spec 미정의 ticker: ic.ema_* fallback."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="UNKNOWN=F")
    assert bt.ema_fast == cfg.esf_intraday.ema_fast


# ─────────────────────────── ESFIntradayStrategy.calculate_indicators ───────────────────────────


def _make_df(n: int = 100) -> pd.DataFrame:
    """가벼운 OHLCV df 생성 (계산에 충분한 길이)."""
    import numpy as np
    # 결정적 무작위 시계열 (재현 가능)
    rng = np.random.default_rng(seed=42)
    closes = 4500 + rng.normal(0, 5, n).cumsum()
    return pd.DataFrame({
        "open": closes - 0.5,
        "high": closes + 1.0,
        "low": closes - 1.0,
        "close": closes,
        "volume": rng.integers(1000, 5000, n),
    })


def test_calc_indicators_ticker_arg_changes_ema_for_cl():
    """calculate_indicators(df, ticker='CL=F'): EMA가 5-period span으로 계산됨."""
    from strategy.esf_intraday import ESFIntradayStrategy
    cfg = ATSConfig()
    strat = ESFIntradayStrategy(cfg)
    df = _make_df(100)

    # 기본 (ticker None): 8/21/55
    df_default = strat.calculate_indicators(df.copy())
    # ticker=CL=F: 5/13/34
    df_cl = strat.calculate_indicators(df.copy(), ticker="CL=F")

    # 짧은 span(5)이 긴 span(8)보다 빠르게 반응 — 마지막 ema_fast 차이
    last_default = float(df_default["ema_fast"].iloc[-1])
    last_cl = float(df_cl["ema_fast"].iloc[-1])
    # 다르긴 해야 한다 (span 변경했으니)
    assert last_default != last_cl


def test_calc_indicators_no_ticker_uses_config_default():
    """ticker 미지정 → ic.ema_* 사용 (ES와 동일)."""
    from strategy.esf_intraday import ESFIntradayStrategy
    cfg = ATSConfig()
    strat = ESFIntradayStrategy(cfg)
    df = _make_df(100)

    df_none = strat.calculate_indicators(df.copy(), ticker=None)
    df_es = strat.calculate_indicators(df.copy(), ticker="ES=F")
    # ES spec에 ema_* override 없으므로 None과 동일 결과
    assert float(df_none["ema_fast"].iloc[-1]) == float(df_es["ema_fast"].iloc[-1])
