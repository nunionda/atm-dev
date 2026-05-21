"""
추세 레짐 감지기 — 중앙 집중식 시장 레짐 판단.

일봉/인트라데이 전략 모두에서 사용하는 통합 레짐 감지.
추세 점수(-10 ~ +10)를 기반으로 BULL/NEUTRAL/BEAR/CRISIS 판단.

구성 요소 (총 -10 ~ +10):
  MA200 위치: +2/-2
  MA200 기울기(20d): +1/-1
  EMA 20/50/100 정렬: +2/-2
  MACD 일봉: +1/-1
  RSI(14) breadth proxy: +1/-1
  VIX 레벨: +1/-1/-2 (CRISIS)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from infra.logger import get_logger

logger = get_logger("trend_regime_detector")


@dataclass
class RegimeResult:
    """레짐 감지 결과."""
    regime: str                    # BULL / NEUTRAL / BEAR / CRISIS
    trend_score: int               # -10 ~ +10
    recommended_strategy: str      # long / mean_reversion / short_mr_hybrid / short
    confidence: float              # 0.0 ~ 1.0
    components: dict               # 개별 구성 요소 점수


# 레짐 → 전략 매핑
REGIME_STRATEGY_MAP = {
    "BULL": "long",
    "NEUTRAL": "mean_reversion",
    "BEAR": "short_mr_hybrid",
    "CRISIS": "short",
}

# 레짐별 counter-bias 페널티
REGIME_COUNTER_BIAS = {
    "BULL": 5.0,
    "NEUTRAL": 2.0,
    "BEAR": 0.0,
    "CRISIS": 0.0,
}

# 레짐별 SHORT 보너스 (보수적: CRISIS에서만 소폭)
REGIME_SHORT_BONUS = {
    "BULL": 0,
    "NEUTRAL": 0,
    "BEAR": 0,
    "CRISIS": 0,  # 보너스 제거 — 낮은 WR 방지
}


def detect_regime(
    df: pd.DataFrame,
    vix_level: Optional[float] = None,
    slope_lookback: int = 20,
) -> RegimeResult:
    """
    DataFrame에서 시장 레짐을 감지한다.

    Args:
        df: OHLCV DataFrame (최소 200+봉 필요, 지표 사전 계산 필요 없음)
        vix_level: VIX 현재값 (None이면 VIX 구성 요소 스킵)
        slope_lookback: MA200 기울기 계산 lookback

    Returns:
        RegimeResult with regime, score, strategy recommendation
    """
    if df.empty or len(df) < 210:
        return RegimeResult(
            regime="NEUTRAL", trend_score=0,
            recommended_strategy="mean_reversion",
            confidence=0.0, components={},
        )

    c = df["close"].astype(float)

    # 지표 계산 (이미 있으면 재사용)
    if "ma_trend" not in df.columns and "ma200" not in df.columns:
        ma200 = c.rolling(window=200).mean()
    else:
        ma200 = df.get("ma_trend", df.get("ma200"))

    if "ema_mid" not in df.columns:
        ema20 = c.ewm(span=20, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        ema100 = c.ewm(span=100, adjust=False).mean()
    else:
        ema20 = df.get("ema_fast", c.ewm(span=20, adjust=False).mean())
        ema50 = df.get("ema_mid", c.ewm(span=50, adjust=False).mean())
        ema100 = df.get("ema_slow", c.ewm(span=100, adjust=False).mean())

    if "macd_hist" not in df.columns:
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal
    else:
        macd_hist = df["macd_hist"]

    if "rsi" not in df.columns:
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(span=14, adjust=False).mean()
        avg_loss = loss.ewm(span=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
    else:
        rsi = df["rsi"]

    # 현재 값 추출
    curr_close = float(c.iloc[-1])
    curr_ma200 = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else curr_close
    curr_ema20 = float(ema20.iloc[-1]) if pd.notna(ema20.iloc[-1]) else curr_close
    curr_ema50 = float(ema50.iloc[-1]) if pd.notna(ema50.iloc[-1]) else curr_close
    curr_ema100 = float(ema100.iloc[-1]) if pd.notna(ema100.iloc[-1]) else curr_close
    curr_macd = float(macd_hist.iloc[-1]) if pd.notna(macd_hist.iloc[-1]) else 0
    curr_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50

    score = 0
    components = {}

    # ── 1. MA200 위치 (+1/-1) ──
    # K (Walk-Forward D 진단): ±2 → ±1로 감소. MA200 lag로 약세 초입에도
    # close>MA200이 자주 유지되어 +2 우위로 BULL/NEUTRAL 분류 → BEAR 미감지.
    # 가중치 절반으로 줄여 lag 영향 완화.
    if curr_ma200 > 0:
        if curr_close > curr_ma200:
            score += 1
            components["ma200_position"] = +1
        else:
            score -= 1
            components["ma200_position"] = -1
    else:
        components["ma200_position"] = 0

    # ── 2. MA200 기울기 (+1/-1) ──
    lb = min(slope_lookback, len(ma200) - 1)
    if lb > 0:
        prev_ma200 = float(ma200.iloc[-lb]) if pd.notna(ma200.iloc[-lb]) else curr_ma200
        if curr_ma200 > prev_ma200 * 1.001:  # 0.1% threshold
            score += 1
            components["ma200_slope"] = +1
        elif curr_ma200 < prev_ma200 * 0.999:
            score -= 1
            components["ma200_slope"] = -1
        else:
            components["ma200_slope"] = 0
    else:
        components["ma200_slope"] = 0

    # ── 3. EMA 정렬 (+2/-2) ──
    if curr_ema20 > curr_ema50 > curr_ema100:
        score += 2
        components["ema_alignment"] = +2
    elif curr_ema20 < curr_ema50 < curr_ema100:
        score -= 2
        components["ema_alignment"] = -2
    else:
        components["ema_alignment"] = 0

    # ── 3b. 단기 EMA cross (+1/-1) — K (D 진단): 약세 초입 단기 신호 감지 ──
    # EMA20 vs EMA50 비교만으로 단기 추세 전환을 빠르게 잡음.
    # 전체 정렬(3개 EMA)가 깨지기 전에 단기 신호로 score 떨어뜨려 BEAR 진입 촉진.
    if curr_ema20 > curr_ema50:
        score += 1
        components["ema_short_cross"] = +1
    elif curr_ema20 < curr_ema50:
        score -= 1
        components["ema_short_cross"] = -1
    else:
        components["ema_short_cross"] = 0

    # ── 4. MACD 방향 (+1/-1) ──
    if curr_macd > 0:
        score += 1
        components["macd"] = +1
    elif curr_macd < 0:
        score -= 1
        components["macd"] = -1
    else:
        components["macd"] = 0

    # ── 5. RSI breadth proxy (+1/-1) ──
    if curr_rsi > 60:
        score += 1
        components["rsi_breadth"] = +1
    elif curr_rsi < 40:
        score -= 1
        components["rsi_breadth"] = -1
    else:
        components["rsi_breadth"] = 0

    # ── 6. VIX 레벨 (+1/-1/-2) ──
    if vix_level is not None:
        if vix_level < 15:
            score += 1
            components["vix"] = +1
        elif vix_level > 35:
            score -= 2
            components["vix"] = -2
        elif vix_level > 25:
            score -= 1
            components["vix"] = -1
        else:
            components["vix"] = 0
    else:
        components["vix"] = 0  # VIX 없으면 중립

    # ── 레짐 매핑 ──
    # D 시도: NEUTRAL 임계 1→2로 좁혀 약세 초입 BEAR 감지 시도했으나, baseline의
    # NEUTRAL 봉들이 이미 score 2~4였음 → 어떤 봉도 분류 변경되지 않음. revert.
    # MA200 lag 본질을 풀려면 score 컴포넌트 가중치 재설계 필요 (다음 세션 후보).
    if score >= 5:
        regime = "BULL"
    elif score >= 1:
        regime = "NEUTRAL"
    elif score >= -4:
        regime = "BEAR"
    else:
        regime = "CRISIS"

    # Confidence: |score| / max_possible (10)
    max_possible = 10
    confidence = min(abs(score) / max_possible, 1.0)

    recommended = REGIME_STRATEGY_MAP.get(regime, "mean_reversion")

    logger.info(
        "Regime: %s (score=%d, confidence=%.1f%%) → %s | "
        "MA200pos=%d slope=%d EMA=%d EMA_short=%d MACD=%d RSI=%d VIX=%d",
        regime, score, confidence * 100, recommended,
        components.get("ma200_position", 0),
        components.get("ma200_slope", 0),
        components.get("ema_alignment", 0),
        components.get("ema_short_cross", 0),
        components.get("macd", 0),
        components.get("rsi_breadth", 0),
        components.get("vix", 0),
    )

    return RegimeResult(
        regime=regime,
        trend_score=score,
        recommended_strategy=recommended,
        confidence=confidence,
        components=components,
    )


def get_counter_bias_penalty(regime: str) -> float:
    """레짐별 counter-bias 페널티 반환."""
    return REGIME_COUNTER_BIAS.get(regime, 2.0)


def get_short_bonus(regime: str) -> int:
    """레짐별 SHORT 보너스 반환."""
    return REGIME_SHORT_BONUS.get(regime, 0)
