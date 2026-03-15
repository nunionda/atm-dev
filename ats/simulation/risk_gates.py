"""
Risk gate checks: RG1-RG5, bearish divergence, S/R detection.
Extracted from engine.py for modularity (C2 decomposition).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

import pandas as pd

from simulation.constants import REGIME_OVERRIDES, REGIME_PARAMS

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def risk_gate_check(engine: SimulationEngine) -> tuple:
    """
    Phase 4: 리스크 게이트. 하나라도 실패 시 (False, reason) 반환.

    Phase 3.2 단계적 DD 대응:
      DD > 10% → 포지션 사이즈 50% 감축 (dd_sizing_mult=0.5)
      DD > 15% → 신규 진입 차단
      DD > 20% → 전 포지션 청산, 시스템 정지
    """
    total_equity = engine._get_total_equity()
    daily_pnl_pct = (
        (total_equity - engine._daily_start_equity) / engine._daily_start_equity * 100
        if engine._daily_start_equity > 0 else 0
    )

    # RG1: 일일 손실 -10% → 매매 중단
    if daily_pnl_pct <= -10.0:
        return False, "RG1: 일일 손실 -10% 도달"

    # DD 단계적 대응 (Phase 3.2)
    engine._peak_equity = max(engine._peak_equity, total_equity)
    mdd = (
        (total_equity - engine._peak_equity) / engine._peak_equity * 100
        if engine._peak_equity > 0 else 0
    )

    # RG2c: DD > 20% → 전 포지션 청산 + 시스템 정지
    if mdd <= -20.0:
        engine._dd_level = 3
        engine._force_liquidate_all("DD>20% 시스템 정지")
        return False, "RG2c: DD -20% — 전 포지션 청산, 시스템 정지"

    # RG2b: DD > 15% → 신규 진입 차단 (기존 포지션은 유지)
    if mdd <= -15.0:
        engine._dd_level = 2
        return False, "RG2b: DD -15% — 신규 진입 차단"

    # RG2a: DD > 10% → 사이징 50% 감축 (진입은 허용)
    if mdd <= -10.0:
        engine._dd_level = 1
        engine._dd_sizing_mult = 0.5
    else:
        engine._dd_level = 0
        engine._dd_sizing_mult = 1.0

    # RG3: 최대 포지션 수 (regime별)
    active_count = len([p for p in engine.positions.values() if p.status == "ACTIVE"])
    regime_params = REGIME_PARAMS.get(engine._market_regime, REGIME_PARAMS["NEUTRAL"])
    if active_count >= regime_params["max_positions"]:
        return False, f"RG3: 최대 보유 {regime_params['max_positions']}종목 도달"

    # RG4: 현금 비율 (활성 포지션 수에 따라 동적 적용)
    cash_ratio = engine.cash / total_equity if total_equity > 0 else 1.0
    effective_rg4 = engine.min_cash_ratio
    if engine._allocator:
        ac = sum(1 for p in engine.positions.values() if p.status == "ACTIVE")
        if ac <= 2:
            effective_rg4 = max(0.50, engine.min_cash_ratio - 0.20)
    # RG4b: 레짐별 현금 비율 오버라이드 (BEAR: 50%, CRISIS: 70%)
    regime_cash = REGIME_OVERRIDES.get(engine._market_regime, {}).get("min_cash_override")
    if regime_cash is not None:
        effective_rg4 = max(effective_rg4, regime_cash)

    if cash_ratio < effective_rg4:
        return False, f"RG4: 현금 비율 {effective_rg4*100:.0f}% 미만"

    # RG5: VIX > 30 공포 구간 → 신규 진입 차단
    if engine._vix_ema20 > 30:
        return False, f"RG5: VIX 공포구간 ({engine._vix_ema20:.1f} > 30)"

    return True, None


def detect_bearish_divergence(df: pd.DataFrame, lookback: int = 10) -> bool:
    """
    베어리시 다이버전스 감지: 가격은 고점 갱신인데 RSI는 고점 하락.
    True → 진입 차단 (모멘텀 약화 신호).
    """
    if len(df) < lookback + 2 or "rsi" not in df.columns:
        return False

    recent = df.iloc[-lookback:]
    price = recent["close"].astype(float)
    rsi = recent["rsi"]

    if rsi.isna().any():
        return False

    price_peaks = []
    rsi_at_peaks = []
    for i in range(1, len(recent) - 1):
        if float(price.iloc[i]) > float(price.iloc[i - 1]) and float(price.iloc[i]) > float(price.iloc[i + 1]):
            price_peaks.append(float(price.iloc[i]))
            rsi_at_peaks.append(float(rsi.iloc[i]))

    if len(price_peaks) >= 2:
        if price_peaks[-1] > price_peaks[-2] and rsi_at_peaks[-1] < rsi_at_peaks[-2]:
            return True

    return False


def detect_support_resistance(df: pd.DataFrame, lookback: int = 40) -> dict:
    """최근 N봉의 스윙 포인트를 클러스터링하여 S/R 레벨 반환."""
    if len(df) < lookback:
        return {"support": [], "resistance": []}

    recent = df.tail(lookback)
    levels: List[tuple] = []

    # 3-candle 프랙탈 기반 스윙 포인트
    highs = recent["high"].astype(float).values
    lows = recent["low"].astype(float).values
    for i in range(1, len(recent) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            levels.append(("R", float(highs[i])))
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            levels.append(("S", float(lows[i])))

    if not levels:
        return {"support": [], "resistance": []}

    # 1.5% 이내 레벨 클러스터링
    clustered = cluster_levels(levels, tolerance=0.015)
    return {
        "support": [l for t, l in clustered if t == "S"],
        "resistance": [l for t, l in clustered if t == "R"],
    }


def cluster_levels(levels: list, tolerance: float = 0.015) -> list:
    """가격 레벨을 tolerance % 이내로 클러스터링."""
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda x: x[1])
    clusters: List[list] = [[sorted_levels[0]]]

    for item in sorted_levels[1:]:
        last_cluster = clusters[-1]
        avg_price = sum(l[1] for l in last_cluster) / len(last_cluster)
        if abs(item[1] - avg_price) / avg_price <= tolerance:
            last_cluster.append(item)
        else:
            clusters.append([item])

    result = []
    for cluster in clusters:
        avg_price = sum(l[1] for l in cluster) / len(cluster)
        s_count = sum(1 for t, _ in cluster if t == "S")
        r_count = len(cluster) - s_count
        dominant_type = "S" if s_count >= r_count else "R"
        result.append((dominant_type, round(avg_price, 2)))

    return result
