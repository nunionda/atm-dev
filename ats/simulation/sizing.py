"""
Position sizing: VIX-based sizing multiplier and related pure functions.
Extracted from engine.py for modularity (C2 decomposition).
"""
from __future__ import annotations

from simulation.constants import VIX_SIZING_SCALE


def get_vix_sizing_mult(vix_ema20: float, strategy: str = "momentum") -> float:
    """Phase 4.5: 전략별 VIX 사이징 배율.

    MR은 변동성 높을 때 기회 → VIX 높으면 사이즈 증가.
    Defensive는 VIX 높을 때 활성화 → 할인 없음.
    나머지(momentum/smc/brt)는 기존 로직 유지.
    """
    if strategy == "mean_reversion":
        if vix_ema20 > 25:
            return 1.2
        elif vix_ema20 > 20:
            return 1.0
        return 0.8
    if strategy == "defensive":
        return 1.0  # defensive는 VIX 할인 없음
    if strategy == "volatility":
        # volatility premium: VIX 높을수록 기회 크므로 사이즈 증가
        if vix_ema20 > 30:
            return 1.3
        elif vix_ema20 > 25:
            return 1.1
        return 0.9
    # 기존 로직 (momentum/smc/brt)
    for (lo, hi), mult in VIX_SIZING_SCALE.items():
        if lo <= vix_ema20 < hi:
            return mult
    return 0.3  # VIX 100+ fallback
