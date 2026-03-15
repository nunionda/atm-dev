"""
Market regime detection: breadth, index trend, stock regime classification.
Extracted from engine.py for modularity (C2 decomposition).

All functions receive the engine instance to access its state.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Dict

import numpy as np
import pandas as pd

from simulation.allocator import _compute_adx
from simulation.constants import (
    INDEX_TREND_STRATEGY_WEIGHTS,
    STOCK_REGIME_THRESHOLDS,
)

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def judge_market_regime(engine: SimulationEngine) -> str:
    """
    Phase 0: 복합 지표 기반 시장 체제 판단 (4단계).

    복합 점수 = breadth(40%) + ADX 평균(25%) + VIX(20%) + BB bandwidth(15%)
    BULL ≥ 65 | NEUTRAL 40-65 | RANGE_BOUND 25-40 (ADX<20) | BEAR < 25
    """
    above_count = 0
    total_valid = 0
    adx_values = []
    bb_bandwidths = []

    for w in engine._watchlist:
        code = w["code"]
        df = engine._ohlcv_cache.get(code)
        if df is None or len(df) < 220:
            continue

        close = df["close"].astype(float)
        ma200 = close.rolling(window=200).mean()

        if pd.isna(ma200.iloc[-1]):
            continue

        total_valid += 1
        if float(close.iloc[-1]) > float(ma200.iloc[-1]):
            above_count += 1

        # ADX 수집 (종목별 추세 강도)
        if len(df) >= 30:
            high = df["high"].astype(float) if "high" in df.columns else None
            low = df["low"].astype(float) if "low" in df.columns else None
            if high is not None and low is not None:
                try:
                    adx, _, _ = _compute_adx(high, low, close, period=14)
                    last_adx = adx.iloc[-1]
                    if pd.notna(last_adx):
                        adx_values.append(float(last_adx))
                except Exception:
                    pass

        # BB Bandwidth 수집 (변동성 폭)
        if len(df) >= 30:
            ma20 = close.rolling(window=20).mean()
            std20 = close.rolling(window=20).std()
            last_ma20 = ma20.iloc[-1]
            last_std = std20.iloc[-1]
            if pd.notna(last_ma20) and pd.notna(last_std) and last_ma20 > 0:
                bandwidth = float(last_std * 2 / last_ma20) * 100  # % 단위
                bb_bandwidths.append(bandwidth)

    if total_valid < 3:
        return engine._market_regime  # 데이터 부족 → 현재 유지

    # ── 복합 점수 계산 (0-100) ──

    # 1. Breadth 점수 (40%): 0-100 → 0-40
    breadth_pct = above_count / total_valid * 100
    breadth_score = breadth_pct * 0.40  # 0~40

    # 2. ADX 평균 점수 (25%): ADX 높을수록 추세 강 → 높은 점수
    if adx_values:
        avg_adx = sum(adx_values) / len(adx_values)
        adx_score = min(max((avg_adx - 15) / 25 * 25, 0), 25)  # 0~25
    else:
        avg_adx = 25.0  # 데이터 없으면 중립
        adx_score = 10.0

    # 3. VIX 점수 (20%): VIX 낮을수록 강세 → 높은 점수
    vix = engine._vix_ema20
    vix_score = min(max((30 - vix) / 16 * 20, 0), 20)  # 0~20

    # 4. BB Bandwidth 점수 (15%)
    if bb_bandwidths:
        avg_bw = sum(bb_bandwidths) / len(bb_bandwidths)
        bw_score = min(max((avg_bw - 2) / 6 * 15, 0), 15)  # 0~15
    else:
        avg_bw = 4.0
        bw_score = 7.5

    composite_score = breadth_score + adx_score + vix_score + bw_score

    # ── 레짐 결정 ──
    if composite_score >= 65:
        raw_regime = "BULL"
    elif composite_score >= 40:
        is_range_bound = (
            adx_values
            and avg_adx < 20
            and bb_bandwidths
            and avg_bw < 3.5
        )
        raw_regime = "RANGE_BOUND" if is_range_bound else "NEUTRAL"
    elif composite_score >= 25:
        raw_regime = "NEUTRAL" if breadth_pct > 45 else "BEAR"
    else:
        raw_regime = "BEAR"

    return smooth_regime(engine, raw_regime)


def smooth_regime(engine: SimulationEngine, raw_regime: str) -> str:
    """체제 전환 스무딩: N일 연속 동일 신호 시에만 전환."""
    if raw_regime == engine._market_regime:
        engine._regime_candidate = raw_regime
        engine._regime_candidate_days = 0
        return engine._market_regime

    if raw_regime == engine._regime_candidate:
        engine._regime_candidate_days += 1
        if engine._regime_candidate_days >= engine._regime_confirmation_days:
            return raw_regime  # 확인 완료 → 체제 전환
    else:
        engine._regime_candidate = raw_regime
        engine._regime_candidate_days = 1

    return engine._market_regime  # 아직 미확인 → 현재 유지


def analyze_index_trend(engine: SimulationEngine) -> Dict:
    """지수 OHLCV에서 추세 시그널 분석.

    복합 지표: MA 정렬 + RSI + ADX + MACD + VIX
    Returns:
        {
            "trend": "STRONG_BULL" | "BULL" | "NEUTRAL" | "RANGE_BOUND" | "BEAR" | "CRISIS",
            "ma_alignment": "ALIGNED_BULL" | "ALIGNED_BEAR" | "MIXED",
            "momentum_score": float (0-100),
            "volatility_state": "LOW" | "NORMAL" | "HIGH" | "EXTREME",
            "signals": List[str],
        }
    """
    n = len(engine._index_ohlcv)
    if n < 50:
        return {"trend": "NEUTRAL", "ma_alignment": "MIXED",
                "momentum_score": 50.0, "volatility_state": "NORMAL",
                "signals": ["지수 데이터 부족 (< 50일)"]}

    closes = pd.Series([d["close"] for d in engine._index_ohlcv])
    highs = pd.Series([d["high"] for d in engine._index_ohlcv])
    lows = pd.Series([d["low"] for d in engine._index_ohlcv])
    signals = []

    # ── MA Alignment ──
    ma20 = closes.rolling(20).mean().iloc[-1] if n >= 20 else closes.mean()
    ma50 = closes.rolling(50).mean().iloc[-1] if n >= 50 else closes.mean()
    ma200 = closes.rolling(200).mean().iloc[-1] if n >= 200 else None
    current_close = closes.iloc[-1]

    if ma200 is not None and not pd.isna(ma200):
        if current_close > ma50 > ma200:
            ma_state = "ALIGNED_BULL"
            signals.append(f"지수 MA 정렬: Close > MA50 > MA200")
        elif current_close < ma50 < ma200:
            ma_state = "ALIGNED_BEAR"
            signals.append(f"지수 MA 정렬: Close < MA50 < MA200")
        else:
            ma_state = "MIXED"
            signals.append(f"지수 MA 혼합")
    elif current_close > ma50:
        ma_state = "ALIGNED_BULL"
        signals.append(f"지수 Close > MA50 (MA200 미계산)")
    else:
        ma_state = "MIXED"
        signals.append(f"지수 MA 혼합 (MA200 미계산)")

    # ── RSI(14) ──
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] > 0 else 100
    rsi = 100.0 - (100.0 / (1.0 + rs))
    signals.append(f"지수 RSI: {rsi:.1f}")

    # ── ADX(14) ──
    try:
        adx_series, _, _ = _compute_adx(highs, lows, closes, period=14)
        adx = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else 20.0
    except Exception:
        adx = 20.0
    signals.append(f"지수 ADX: {adx:.1f}")

    # ── MACD(12, 26, 9) ──
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line.iloc[-1] - signal_line.iloc[-1]
    macd_positive = macd_hist > 0
    signals.append(f"지수 MACD 히스토그램: {macd_hist:.2f} ({'양' if macd_positive else '음'})")

    # ── Momentum Score (0-100) ──
    rsi_norm = min(max((rsi - 30) / 40 * 40, 0), 40)  # 0~40
    adx_norm = min(max(adx / 50 * 35, 0), 35)  # 0~35
    macd_bonus = 25 if macd_positive else 0
    momentum_score = rsi_norm + adx_norm + macd_bonus
    momentum_score = min(max(momentum_score, 0), 100)

    # ── Volatility State (VIX 기반) ──
    vix = engine._vix_ema20
    if vix < 16:
        volatility_state = "LOW"
    elif vix < 22:
        volatility_state = "NORMAL"
    elif vix < 30:
        volatility_state = "HIGH"
    else:
        volatility_state = "EXTREME"
    signals.append(f"VIX EMA20: {vix:.1f} → {volatility_state}")

    # ── Final Trend Classification ──
    if ma_state == "ALIGNED_BULL" and adx > 30 and rsi > 55:
        trend = "STRONG_BULL"
    elif ma_state == "ALIGNED_BULL" or (
        (ma200 is None or current_close > ma200) and momentum_score > 55
    ):
        trend = "BULL"
    elif ma_state == "ALIGNED_BEAR" and volatility_state in ("HIGH", "EXTREME"):
        trend = "CRISIS"
    elif ma_state == "ALIGNED_BEAR":
        trend = "BEAR"
    elif adx < 20 and volatility_state in ("LOW", "NORMAL"):
        trend = "RANGE_BOUND"
    else:
        trend = "NEUTRAL"
    signals.append(f"최종 지수 추세: {trend}")

    return {
        "trend": trend,
        "ma_alignment": ma_state,
        "momentum_score": round(momentum_score, 1),
        "volatility_state": volatility_state,
        "signals": signals,
        "rsi": round(rsi, 1),
        "adx": round(adx, 1),
        "macd_value": round(float(macd_line.iloc[-1]), 2),
        "macd_signal": round(float(signal_line.iloc[-1]), 2),
    }


def update_strategy_weights_from_index(engine: SimulationEngine):
    """지수 추세 분석 → 전략 비중 동적 오버라이드.

    레짐 고정 모드: 고정 레짐의 가중치 강제 적용 (자동 감지 건너뜀).
    multi 모드: 지수 데이터 있으면 INDEX_TREND_STRATEGY_WEIGHTS 적용.
    지수 데이터 부족하면 기존 REGIME_STRATEGY_WEIGHTS 유지 (fallback).
    """
    # 레짐 전략 모드: 고정 레짐 가중치 강제 적용
    if engine._regime_locked:
        weights = INDEX_TREND_STRATEGY_WEIGHTS.get(
            engine._locked_regime,
            INDEX_TREND_STRATEGY_WEIGHTS.get("NEUTRAL", {})
        )
        if engine._strategy_allocator:
            engine._strategy_allocator.override_weights(weights)
        # 지수 추세 분석은 여전히 실행 (표시용)
        if len(engine._index_ohlcv) >= 50:
            engine._index_trend = analyze_index_trend(engine)
        return

    if len(engine._index_ohlcv) < 50:
        return  # 데이터 부족 → 기존 로직 유지

    old_trend = engine._index_trend.get("trend") if engine._index_trend else None
    old_weights = (
        dict(engine._strategy_allocator.weights)
        if engine._strategy_allocator else {}
    )

    engine._index_trend = analyze_index_trend(engine)
    trend = engine._index_trend.get("trend", "NEUTRAL")

    weights = INDEX_TREND_STRATEGY_WEIGHTS.get(
        trend, INDEX_TREND_STRATEGY_WEIGHTS["NEUTRAL"]
    )

    if engine._strategy_allocator:
        engine._strategy_allocator.override_weights(weights)
        engine._phase_stats["index_trend_updates"] += 1

    # 추세 변경 이력 기록
    if old_trend != trend:
        ts = engine._backtest_date or datetime.now().strftime("%Y-%m-%d %H:%M")
        engine._index_trend_history.append({
            "timestamp": ts,
            "from_trend": old_trend,
            "to_trend": trend,
            "from_weights": old_weights,
            "to_weights": dict(weights),
            "trigger_signals": engine._index_trend.get("signals", [])[-3:],
        })
        if len(engine._index_trend_history) > 20:
            engine._index_trend_history = engine._index_trend_history[-20:]


def classify_stock_regime(engine: SimulationEngine, df: pd.DataFrame) -> str:
    """
    종목 개별 레짐 분류 (0-100 복합 스코어).

    구성요소:
      (1) MA 정렬 점수 (0-30): alignment_score 0~5 → 0~30
      (2) ADX 방향 점수 (0-20): UP 추세 + ADX 강도
      (3) RSI 위치 점수 (0-20): 강세/약세 위치
      (4) Price vs MA200 (0-15): 장기 추세 위치
      (5) Trend Stage 보너스 (0-15): EARLY/MID/LATE
    """
    if len(df) < 200:
        return "NEUTRAL"

    trend = engine._confirm_trend(df)
    stage = engine._estimate_trend_stage(df)
    curr = df.iloc[-1]
    score = 0.0

    # (1) MA 정렬 점수 (0-30)
    alignment = trend.get("alignment_score", 0)
    score += alignment * 6  # 0, 6, 12, 18, 24, 30

    # (2) ADX 방향 점수 (0-20)
    adx = trend.get("adx", 0)
    direction = trend.get("direction", "FLAT")
    if direction == "UP":
        score += min(adx / 50 * 20, 20)
    elif direction == "DOWN":
        score += max(0, 5 - adx / 50 * 5)
    else:
        score += 10

    # (3) RSI 위치 점수 (0-20)
    rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
    if rsi >= 55:
        score += min((rsi - 40) / 40 * 20, 20)
    elif rsi <= 35:
        score += max(0, rsi / 35 * 5)
    else:
        score += 10

    # (4) Price vs MA200 (0-15)
    ma200 = float(curr.get("ma200", 0)) if pd.notna(curr.get("ma200")) else 0
    price = float(curr["close"])
    if ma200 > 0:
        ratio = price / ma200
        if ratio > 1.0:
            score += min((ratio - 1.0) * 100, 15)
        else:
            score += max(0, 15 - (1.0 - ratio) * 100)
    else:
        score += 7

    # (5) Trend Stage 보너스 (0-15)
    stage_bonus = {"EARLY": 15, "MID": 8, "LATE": 2}
    score += stage_bonus.get(stage, 8)

    # 스코어 → 레짐 매핑
    score = max(0, min(100, score))
    for threshold, regime in STOCK_REGIME_THRESHOLDS:
        if score >= threshold:
            return regime
    return "CRISIS"
