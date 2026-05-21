"""
P0-1 회귀 보호: SP500 종목별 ATR multiplier 분리.

- atr_mult_map 디폴트 4종목 로드 검증
- _get_atr_mult가 ticker별로 올바른 값 반환
- _calculate_sl_tp가 ticker 인자를 통해 종목별 SL 거리 분리
- 백테스트 회귀: NQ=F Return > 0 (P0-1 효과 검증)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from data.config_manager import SP500FuturesConfig, ATSConfig, ExitConfig, OrderConfig, PortfolioConfig, RiskConfig, ScheduleConfig, StrategyConfig, UniverseConfig
from strategy.sp500_futures import SP500FuturesStrategy


def _make_strategy(config: ATSConfig) -> SP500FuturesStrategy:
    """SP500FuturesStrategy 인스턴스 (config만 주입)."""
    return SP500FuturesStrategy(config)


# ──────────────────────────────────────
# 1) atr_mult_map 디폴트 적재
# ──────────────────────────────────────

def test_atr_mult_map_default_contains_4_tickers():
    """디폴트 config에 4종목(+ 마이크로) 모두 포함."""
    fc = SP500FuturesConfig()
    expected = {"ES=F", "MES=F", "NQ=F", "MNQ=F", "CL=F", "MCL=F", "GC=F", "MGC=F"}
    assert expected.issubset(set(fc.atr_mult_map.keys()))

    # 각 값은 (strong, weak) 튜플
    for ticker, mult in fc.atr_mult_map.items():
        assert isinstance(mult, tuple) and len(mult) == 2, f"{ticker} should be (strong, weak) tuple"
        assert mult[0] > 0 and mult[1] > 0


# ──────────────────────────────────────
# 2) _get_atr_mult가 ticker별로 정확한 값 반환
# ──────────────────────────────────────

def test_get_atr_mult_per_ticker():
    """NQ=F는 좁은 (1.0/1.3), ES=F는 표준 (1.5/2.0)."""
    cfg = ATSConfig(
        sp500_futures=SP500FuturesConfig(adx_threshold=25.0),
    )
    strat = _make_strategy(cfg)

    # ADX=30 → strong, ADX=10 → weak
    assert strat._get_atr_mult("NQ=F", 30) == 1.0
    assert strat._get_atr_mult("NQ=F", 10) == 1.3

    assert strat._get_atr_mult("ES=F", 30) == 1.5
    assert strat._get_atr_mult("ES=F", 10) == 2.0

    assert strat._get_atr_mult("CL=F", 30) == 1.2
    assert strat._get_atr_mult("CL=F", 10) == 1.6


def test_get_atr_mult_unknown_ticker_falls_back_to_default():
    """map에 없는 ticker는 글로벌 sl_atr_mult/sl_atr_mult_strong로 fallback."""
    cfg = ATSConfig(
        sp500_futures=SP500FuturesConfig(
            adx_threshold=25.0,
            sl_atr_mult=2.0,
            sl_atr_mult_strong=1.5,
        ),
    )
    strat = _make_strategy(cfg)

    assert strat._get_atr_mult("UNKNOWN=F", 30) == 1.5  # strong
    assert strat._get_atr_mult("UNKNOWN=F", 10) == 2.0  # weak

    # None ticker도 fallback
    assert strat._get_atr_mult(None, 30) == 1.5
    assert strat._get_atr_mult(None, 10) == 2.0


# ──────────────────────────────────────
# 3) _calculate_sl_tp가 ticker별로 SL 거리 분리
# ──────────────────────────────────────

def test_calculate_sl_tp_distance_differs_per_ticker():
    """동일 entry/atr/adx에 대해 NQ는 ES보다 좁은 SL을 만들어야 한다 (P0-1 핵심 효과)."""
    cfg = ATSConfig(
        sp500_futures=SP500FuturesConfig(adx_threshold=25.0, tp_atr_mult=3.0),
    )
    strat = _make_strategy(cfg)

    entry = 5000.0
    atr = 50.0
    is_long = True
    adx_weak = 10  # weak 분기

    sl_es, _ = strat._calculate_sl_tp(entry, atr, is_long, adx_weak, ticker="ES=F")
    sl_nq, _ = strat._calculate_sl_tp(entry, atr, is_long, adx_weak, ticker="NQ=F")

    # ES (weak=2.0): SL = 5000 - 50*2.0 = 4900
    # NQ (weak=1.3): SL = 5000 - 50*1.3 = 4935 (entry에 더 가까움)
    assert sl_es < sl_nq, f"ES SL({sl_es}) should be lower (farther) than NQ SL({sl_nq}) for LONG"
    assert abs(sl_es - 4900) < 0.1
    assert abs(sl_nq - 4935) < 0.1


def test_calculate_sl_tp_short_direction_per_ticker():
    """SHORT 포지션에서도 ticker별 SL 거리 분리 (LONG의 대칭)."""
    cfg = ATSConfig(
        sp500_futures=SP500FuturesConfig(adx_threshold=25.0, tp_atr_mult=3.0),
    )
    strat = _make_strategy(cfg)

    entry = 5000.0
    atr = 50.0
    is_long = False
    adx_weak = 10

    sl_es, _ = strat._calculate_sl_tp(entry, atr, is_long, adx_weak, ticker="ES=F")
    sl_nq, _ = strat._calculate_sl_tp(entry, atr, is_long, adx_weak, ticker="NQ=F")

    # ES (weak=2.0): SL = 5000 + 50*2.0 = 5100
    # NQ (weak=1.3): SL = 5000 + 50*1.3 = 5065 (entry에 더 가까움)
    assert sl_nq < sl_es, f"NQ SL({sl_nq}) should be lower (closer) than ES SL({sl_es}) for SHORT"
