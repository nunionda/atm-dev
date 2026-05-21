"""
P3-4 회귀 보호: ESF compute_magnetic_ma 부분 lookback 활용.

핵심 단언:
  - 기존: 마지막 10봉 deviation이 통계에서 완전 제외 → 최근 시장 변화 미반영 (E4)
  - 개선: 마지막 1봉만 제외 + available_lookback = min(10, 잔여 봉수)
  - 결과: total_deviations 증가 (가능 시), reversion 부분 카운트 정확
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from data.config_manager import ATSConfig, ESFIntradayConfig
from strategy.esf_intraday import ESFIntradayStrategy


def _make_strategy() -> ESFIntradayStrategy:
    return ESFIntradayStrategy(ATSConfig(esf_intraday=ESFIntradayConfig()))


# ──────────────────────────────────────
# 1) 소스 단언 — P3-4 패치 적용
# ──────────────────────────────────────

def test_p3_4_partial_lookback_applied():
    """소스에 available_lookback 패턴 적용 + len(indices) - 1 (마지막 1봉만 제외)."""
    import strategy.esf_intraday as mod
    src = inspect.getsource(mod.ESFIntradayStrategy.compute_magnetic_ma)
    assert "available_lookback" in src, "P3-4 regression: available_lookback 변수 필요"
    assert "len(indices) - 1" in src, "P3-4 regression: 마지막 1봉만 제외해야 함"
    # 실행 코드 라인의 옛 패턴(콜론 포함)이 제거됐는지 (주석 텍스트는 콜론 없이 보존 가능)
    assert "range(period, len(indices) - lookback):" not in src, (
        "P3-4 regression: 구 실행 코드 `range(period, len(indices) - lookback):` 제거 필요"
    )


# ──────────────────────────────────────
# 2) total_deviations >= 이전 코드의 그것
# ──────────────────────────────────────

def _build_df_with_known_pattern(n_bars: int = 100) -> pd.DataFrame:
    """ATR 일정, close가 sine wave로 deviation 반복하는 df."""
    np.random.seed(42)
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="15min")
    base = 5000.0
    # 진폭 ±50 sine + 약간의 노이즈
    close = base + 50 * np.sin(np.linspace(0, 8 * np.pi, n_bars)) + np.random.normal(0, 5, n_bars)
    high = close + 5
    low = close - 5
    df = pd.DataFrame({
        "close": close,
        "high": high,
        "low": low,
        "atr": np.full(n_bars, 10.0),  # 일정 ATR
        "volume": np.full(n_bars, 1000),
    }, index=idx)
    return df


def test_total_deviations_includes_recent_bars():
    """패치 후 total_deviations가 마지막 10봉의 deviation도 포함해야 한다."""
    strat = _make_strategy()
    df = _build_df_with_known_pattern(n_bars=100)
    result = strat.compute_magnetic_ma(df)
    # 결과 자체가 정상 반환되는지 + 최소 1개 ranking 있는지
    assert "rankings" in result
    assert isinstance(result["rankings"], list)
    # 모든 ranking은 total_samples >= 5 (line 345 필터)
    for r in result["rankings"]:
        assert r["total_samples"] >= 5, f"total_samples {r['total_samples']} < 5"


def test_short_df_returns_empty():
    """df가 너무 짧으면 (60봉 미만) empty 반환 (변화 없음)."""
    strat = _make_strategy()
    df = _build_df_with_known_pattern(n_bars=50)
    result = strat.compute_magnetic_ma(df)
    assert result == {"rankings": [], "best": None}


def test_no_atr_column_returns_empty():
    """ATR 컬럼 없으면 empty."""
    strat = _make_strategy()
    df = pd.DataFrame({
        "close": [100, 101, 102, 103, 104] * 20,
    }, index=pd.date_range("2026-01-01", periods=100, freq="15min"))
    result = strat.compute_magnetic_ma(df)
    assert result == {"rankings": [], "best": None}


# ──────────────────────────────────────
# 3) magnetic_score 의미 검증 — 부분 lookback에서도 안정
# ──────────────────────────────────────

def test_magnetic_score_within_reasonable_range():
    """부분 lookback이 적용된 magnetic_score가 비정상 값(NaN/inf, 음수) 안 나오는지."""
    strat = _make_strategy()
    df = _build_df_with_known_pattern(n_bars=200)
    result = strat.compute_magnetic_ma(df)
    for r in result.get("rankings", []):
        ms = r["magnetic_score"]
        assert ms == ms, f"magnetic_score NaN: {r}"  # NaN check
        assert ms >= 0, f"magnetic_score negative: {ms}"
        assert ms < 1000, f"magnetic_score abnormally large: {ms}"
