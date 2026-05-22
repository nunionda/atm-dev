"""F2 — BB squeeze L4 통합 단위 테스트.

목표: bb_squeeze_ratio < 0.75 AND volume_ratio >= 1.5 동시 발생 시 Layer 4 +3pt,
그 외에는 변화 없음. max_score 25 cap 유지.
"""
from __future__ import annotations

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pandas as pd

from common.enums import FuturesDirection
from data.config_manager import ATSConfig
from strategy.esf_intraday import ESFIntradayStrategy


def _build_df(volume_ratio: float, bb_squeeze: float, obv_fast: float = 100, obv_slow: float = 90):
    """단일 row df 생성. _score_volume_aggression 입력 형태."""
    return pd.DataFrame([{
        "volume_ratio": volume_ratio,
        "bb_squeeze_ratio": bb_squeeze,
        "obv_ema_fast": obv_fast,
        "obv_ema_slow": obv_slow,
    }])


def _no_aggression():
    """Aggression 미감지 (점수 기여 없음)."""
    return {
        "detected": False,
        "direction": "NEUTRAL",
        "body_ratio": 0.3,
        "range_expansion": 1.0,
        "consecutive_dir": 0,
    }


def _make_strategy() -> ESFIntradayStrategy:
    return ESFIntradayStrategy(ATSConfig())


# ─────────────────────────── BB squeeze active cases ───────────────────────────


def test_bb_squeeze_with_vol_surge_adds_3pt():
    """BB squeeze (0.6) + vol surge (1.5) → BB_SQUEEZE_BREAKOUT +3."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.6, bb_squeeze=0.6)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    # vol surge 8 + obv 7 + bb squeeze 3 = 18 (aggression 0)
    assert score == 18.0
    assert "BB_SQUEEZE_BREAKOUT" in signals
    assert "VOL_SURGE" in signals
    assert "OBV_BULL" in signals


def test_bb_squeeze_edge_below_threshold_active():
    """BB squeeze 0.74 (< 0.75) + vol 1.5 → +3."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.5, bb_squeeze=0.74)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" in signals
    assert score >= 11.0  # at least vol surge + bb bonus


# ─────────────────────────── BB squeeze NOT active cases ───────────────────────────


def test_bb_loose_no_bonus():
    """BB ratio 1.0 (not squeezed) + vol 1.6 → BB bonus 미발동."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.6, bb_squeeze=1.0)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" not in signals
    # vol surge 8 + obv 7 = 15
    assert score == 15.0


def test_bb_squeeze_but_low_vol_no_bonus():
    """BB squeeze 0.5 (압축) but vol 1.0 (서지 없음) → BB bonus 미발동."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.0, bb_squeeze=0.5)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" not in signals


def test_bb_squeeze_boundary_075_inactive():
    """BB ratio 정확히 0.75 (경계) → < 0.75 조건 불충족 → 미발동."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.6, bb_squeeze=0.75)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" not in signals


def test_vol_boundary_15_active():
    """volume_ratio 정확히 1.5 (경계) + BB squeeze → 발동 (>=)."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.5, bb_squeeze=0.6)
    _, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" in signals


# ─────────────────────────── max_score cap ───────────────────────────


def test_max_score_25_cap_respected():
    """모든 신호 + aggression detected 시 max 25pt cap 유지."""
    s = _make_strategy()
    df = _build_df(volume_ratio=2.0, bb_squeeze=0.5)
    aggr = {
        "detected": True,
        "direction": "BULL",
        "body_ratio": 0.8,
        "range_expansion": 1.5,
        "consecutive_dir": 4,
    }
    score, signals = s._score_volume_aggression(df, aggr, FuturesDirection.LONG)
    # vol 8 + obv 7 + bb 3 + aggr 10 = 28 → cap 25
    assert score == 25.0
    assert "BB_SQUEEZE_BREAKOUT" in signals
    assert "AGGRESSION_ALIGNED" in signals


def test_short_direction_bb_squeeze_works():
    """SHORT 방향에도 BB squeeze + vol surge 보너스 동일 작동."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.6, bb_squeeze=0.6, obv_fast=80, obv_slow=100)
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.SHORT)
    assert "BB_SQUEEZE_BREAKOUT" in signals
    assert "OBV_BEAR" in signals  # SHORT 방향 OBV 일치


def test_no_signals_returns_zero():
    """vol low + BB loose + OBV reverse → 0pt 또는 아주 낮음."""
    s = _make_strategy()
    df = _build_df(volume_ratio=1.0, bb_squeeze=1.0, obv_fast=80, obv_slow=100)  # OBV bearish for long
    score, signals = s._score_volume_aggression(df, _no_aggression(), FuturesDirection.LONG)
    assert "BB_SQUEEZE_BREAKOUT" not in signals
    assert score == 0.0  # vol 0 + obv 0 + bb 0 + aggr 0
