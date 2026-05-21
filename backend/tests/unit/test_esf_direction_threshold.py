"""
P3-1 회귀 보호: ESF _determine_direction 임계값 완화 (3 → 2).

핵심 단언:
  - score = 2 → LONG/SHORT 진입 가능 (이전: NEUTRAL 차단)
  - score = -2 → SHORT (이전: NEUTRAL)
  - score = 1, -1, 0 → 여전히 NEUTRAL
  - EMA veto는 유지 — score 충분해도 역배열이면 NEUTRAL
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from common.enums import FuturesDirection
from data.config_manager import ATSConfig, ESFIntradayConfig
from strategy.esf_intraday import ESFIntradayStrategy


def _make_strategy() -> ESFIntradayStrategy:
    cfg = ATSConfig(esf_intraday=ESFIntradayConfig())
    return ESFIntradayStrategy(cfg)


def _make_bar(ema_fast=100.0, ema_mid=100.0, ema_slow=100.0,
              macd_hist=0.0, zscore=0.0) -> pd.DataFrame:
    """단일 봉 df (last row만 사용)."""
    return pd.DataFrame({
        "ema_fast": [ema_fast, ema_fast],
        "ema_mid":  [ema_mid, ema_mid],
        "ema_slow": [ema_slow, ema_slow],
        "macd_hist":[macd_hist, macd_hist],
        "zscore":   [zscore, zscore],
    })


# ──────────────────────────────────────
# 1) 임계 2로 완화 — score=2면 LONG 진입
# ──────────────────────────────────────

def test_score_2_triggers_long():
    """EMA bullish + MACD>0 = score 2 → LONG (이전 임계 3에서는 NEUTRAL)."""
    strat = _make_strategy()
    df = _make_bar(ema_fast=102, ema_mid=101, ema_slow=100, macd_hist=0.5, zscore=0)
    # score: EMA fast>slow +1, MACD +1, Z 0 = 2
    result = strat._determine_direction(df, market_state="BALANCE",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.LONG


def test_score_negative_2_triggers_short():
    """EMA bearish + MACD<0 = score -2 → SHORT (단 EMA 완전 역배열이라 veto?)
    EMA fast<slow는 -1, EMA bearish veto는 fast<mid<slow 일 때.
    여기 fast=100, mid=101, slow=102: bearish 아님(mid>fast이지만 fast>slow 아님). 사실 fast<slow."""
    strat = _make_strategy()
    # EMA: fast=99, mid=100, slow=101 (완전 역배열 fast<mid<slow → SHORT veto는 ema_bullish 일 때만)
    df = _make_bar(ema_fast=99, ema_mid=100, ema_slow=101, macd_hist=-0.5, zscore=0)
    # ema_f < ema_s → -1, MACD -1, Z 0 = -2
    # ema_bullish (fast>mid>slow)? 99>100>101 거짓 → SHORT 진입 가능
    result = strat._determine_direction(df, market_state="BALANCE",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.SHORT


# ──────────────────────────────────────
# 2) score 1, -1, 0은 여전히 NEUTRAL
# ──────────────────────────────────────

def test_score_1_remains_neutral():
    """score 1은 NEUTRAL 유지."""
    strat = _make_strategy()
    df = _make_bar(ema_fast=102, ema_mid=101, ema_slow=100, macd_hist=0.0, zscore=0)
    # EMA +1, MACD 0, Z 0 = 1
    result = strat._determine_direction(df, market_state="BALANCE",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.NEUTRAL


def test_score_0_remains_neutral():
    """모든 컴포넌트 중립 → NEUTRAL."""
    strat = _make_strategy()
    df = _make_bar(ema_fast=100, ema_mid=100, ema_slow=100, macd_hist=0.0, zscore=0)
    result = strat._determine_direction(df, market_state="BALANCE",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.NEUTRAL


# ──────────────────────────────────────
# 3) EMA veto는 유지 — score 충분해도 차단
# ──────────────────────────────────────

def test_ema_bearish_vetoes_long():
    """EMA 완전 역배열(bearish)이면 score>=2여도 LONG 차단."""
    strat = _make_strategy()
    # EMA fast<mid<slow (bearish), MACD>0, IMBALANCE_BULL → 가능한 score 높지만 LONG veto
    df = _make_bar(ema_fast=99, ema_mid=100, ema_slow=101, macd_hist=0.5, zscore=-2)
    # market_state +2, MACD +1, Z (-1.5 미만이므로 +1) = 4. EMA fast<slow -1. 합 = 3.
    # 그러나 ema_bearish → veto → NEUTRAL
    result = strat._determine_direction(df, market_state="IMBALANCE_BULL",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.NEUTRAL


def test_ema_bullish_vetoes_short():
    """EMA 완전 정배열(bullish)이면 score<=-2여도 SHORT 차단."""
    strat = _make_strategy()
    # EMA bullish (102>101>100), MACD<0, IMBALANCE_BEAR
    df = _make_bar(ema_fast=102, ema_mid=101, ema_slow=100, macd_hist=-0.5, zscore=2)
    # market_state -2, MACD -1, Z (1.5 초과) -1, EMA +1 = -3. veto bullish → NEUTRAL
    result = strat._determine_direction(df, market_state="IMBALANCE_BEAR",
                                          aggression={"detected": False, "direction": "NEUTRAL"})
    assert result == FuturesDirection.NEUTRAL


# ──────────────────────────────────────
# 4) 소스 단언 — 임계 2 패턴 적용
# ──────────────────────────────────────

def test_p3_1_threshold_patch_in_source():
    """esf_intraday 소스에 임계 2 패턴이 적용됐는지."""
    import inspect
    import strategy.esf_intraday as mod
    src = inspect.getsource(mod._determine_direction.__get__) if hasattr(mod, '_determine_direction') else inspect.getsource(mod)
    assert "score >= 2" in src and "score <= -2" in src, (
        "P3-1 regression: _determine_direction must use ±2 threshold (not ±3)."
    )
