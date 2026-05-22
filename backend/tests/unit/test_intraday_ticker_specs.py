"""Phase 3 unit tests — intraday_ticker_specs module + IntradayBacktester per-ticker spec."""
from __future__ import annotations

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest

from data.config_manager import ATSConfig
from strategy.intraday_ticker_specs import (
    INTRADAY_SPECS,
    get_intraday_spec,
    is_supported_intraday,
    list_supported_tickers,
)


# ─────────────────────────── spec map tests ───────────────────────────


def test_all_8_tickers_present():
    """ES/MES/NQ/MNQ/CL/MCL/GC/MGC 모두 spec 존재."""
    expected = {"ES=F", "MES=F", "NQ=F", "MNQ=F", "CL=F", "MCL=F", "GC=F", "MGC=F"}
    assert set(INTRADAY_SPECS.keys()) == expected


def test_equity_index_spec_values():
    """ES/MES/NQ/MNQ: tick 0.25, RTH 09:30-16:00."""
    for tk in ("ES=F", "MES=F", "NQ=F", "MNQ=F"):
        spec = get_intraday_spec(tk)
        assert spec is not None
        assert spec["tick_size"] == 0.25
        assert spec["rth_start"] == "09:30"
        assert spec["rth_end"] == "16:00"


def test_es_multiplier_50():
    """ES=F multiplier = 50.0 (CME E-mini)."""
    assert get_intraday_spec("ES=F")["multiplier"] == 50.0


def test_mes_multiplier_5():
    """MES=F multiplier = 5.0 (Micro)."""
    assert get_intraday_spec("MES=F")["multiplier"] == 5.0


def test_cl_spec():
    """CL=F: mult 1000, tick 0.01, pit hours 09:00-14:30."""
    spec = get_intraday_spec("CL=F")
    assert spec["multiplier"] == 1000.0
    assert spec["tick_size"] == 0.01
    assert spec["rth_start"] == "09:00"
    assert spec["rth_end"] == "14:30"


def test_gc_spec():
    """GC=F: mult 100, tick 0.10, floor 08:20-13:30."""
    spec = get_intraday_spec("GC=F")
    assert spec["multiplier"] == 100.0
    assert spec["tick_size"] == 0.10
    assert spec["rth_start"] == "08:20"
    assert spec["rth_end"] == "13:30"


def test_micro_commodities():
    """MCL/MGC: multiplier 1/10 of full contract."""
    assert get_intraday_spec("MCL=F")["multiplier"] == 100.0   # full CL=1000
    assert get_intraday_spec("MGC=F")["multiplier"] == 10.0    # full GC=100


def test_unsupported_ticker_returns_none():
    """spec 미정의 ticker는 None."""
    assert get_intraday_spec("UNKNOWN=F") is None
    assert get_intraday_spec("") is None


def test_is_supported():
    assert is_supported_intraday("ES=F") is True
    assert is_supported_intraday("CL=F") is True
    assert is_supported_intraday("XYZ=F") is False


def test_list_supported_returns_8():
    assert len(list_supported_tickers()) == 8


# ─────────────────────────── IntradayBacktester integration ───────────────────────────


def test_backtester_uses_spec_for_es():
    """IntradayBacktester ES=F: spec 값 그대로 적용."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="ES=F", is_micro=False)
    assert bt.multiplier == 50.0
    assert bt.tick_size == 0.25
    assert bt.rth_start == "09:30"
    assert bt.rth_end == "16:00"


def test_backtester_uses_spec_for_cl():
    """IntradayBacktester CL=F: commodity spec 적용."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="CL=F", is_micro=False)
    assert bt.multiplier == 1000.0
    assert bt.tick_size == 0.01
    assert bt.rth_start == "09:00"
    assert bt.rth_end == "14:30"


def test_backtester_uses_spec_for_gc():
    """IntradayBacktester GC=F: gold spec 적용."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="GC=F", is_micro=False)
    assert bt.multiplier == 100.0
    assert bt.tick_size == 0.10
    assert bt.rth_start == "08:20"
    assert bt.rth_end == "13:30"


def test_backtester_fallback_for_unknown_ticker():
    """spec 미정의 ticker는 ic.* fallback (backward-compat)."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="UNKNOWN=F", is_micro=True)
    # fallback: tick_size=0.25 (ES default), rth_start/end from ic
    assert bt.tick_size == 0.25
    assert bt.rth_start == cfg.esf_intraday.rth_start
    assert bt.rth_end == cfg.esf_intraday.rth_end


def test_backtester_es_slippage_unchanged():
    """ES=F regression: slippage = 1 tick × 0.25 × 50 = $12.50/contract."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="ES=F", is_micro=False)
    assert bt.slippage_per_contract == pytest.approx(12.50, abs=0.01)


def test_backtester_cl_slippage_correct():
    """CL=F: slippage = 1 tick × 0.01 × 1000 = $10/contract."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="CL=F", is_micro=False)
    assert bt.slippage_per_contract == pytest.approx(10.00, abs=0.01)


def test_backtester_gc_slippage_correct():
    """GC=F: slippage = 1 tick × 0.10 × 100 = $10/contract."""
    from backtest.intraday_backtester import IntradayBacktester
    cfg = ATSConfig()
    bt = IntradayBacktester(cfg, ticker="GC=F", is_micro=False)
    assert bt.slippage_per_contract == pytest.approx(10.00, abs=0.01)
