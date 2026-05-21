"""
Self-contained helpers used by SimulationEngine — pure functions, no `self` deps.

Phase 4.C-3 분할: ats/simulation/engine.py → ats/simulation/_helpers.py
모듈 레벨 / staticmethod 후보들을 모음.
"""

from typing import List, Tuple

import numpy as np
import pandas as pd


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """순수 pandas로 ADX, +DI, -DI 계산 (ta 라이브러리 의존 없음).

    Returns
    -------
    (adx, plus_di, minus_di) : 3 pd.Series tuple
    """
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    # +DM과 -DM 중 큰 쪽만 유효
    mask_plus = plus_dm <= minus_dm
    mask_minus = minus_dm <= plus_dm
    plus_dm = plus_dm.copy()
    minus_dm = minus_dm.copy()
    plus_dm[mask_plus] = 0
    minus_dm[mask_minus] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(window=period).mean()

    return adx, plus_di, minus_di


def cluster_levels(levels: list, tolerance: float = 0.015) -> List[Tuple[str, float]]:
    """가격 레벨을 tolerance % 이내로 클러스터링.

    각 클러스터에서 가장 빈번한 타입과 평균 가격을 반환.

    Parameters
    ----------
    levels : list of (type_str, price_float)
        type_str ∈ {"S", "R"} — 지지/저항
    tolerance : float
        클러스터 병합 임계비율 (default 1.5%)

    Returns
    -------
    list of (dominant_type, avg_price) 클러스터 대표값
    """
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
