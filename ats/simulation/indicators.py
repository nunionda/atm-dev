"""
Core technical indicator calculations: MA, RSI, MACD, BB, ATR, ADX.
Extracted from engine.py for modularity (C2 decomposition).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from simulation.allocator import _compute_adx

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


def calculate_indicators(engine: SimulationEngine, df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicator columns to OHLCV DataFrame."""
    if df.empty or len(df) < engine.ma_long:
        return df

    # 거래량 0인 행 제거 (휴장일/비정상 데이터 — 지표 왜곡 방지)
    if "volume" in df.columns:
        df = df[df["volume"] > 0]
    if len(df) < engine.ma_long:
        return df

    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    h = df["high"].astype(float)
    lo = df["low"].astype(float)
    df = df.copy()

    # ── 기존 이평선 ──
    df["ma_short"] = c.rolling(window=engine.ma_short).mean()
    df["ma_long"] = c.rolling(window=engine.ma_long).mean()

    # ── Phase 1: 정배열용 이평선 ──
    df["ma60"] = c.rolling(window=60).mean()
    df["ma120"] = c.rolling(window=120).mean()
    df["ma200"] = c.rolling(window=200).mean()

    # ── Phase 1: ADX / DMI (14일) ──
    adx_vals, plus_di_vals, minus_di_vals = _compute_adx(h, lo, c, period=14)
    df["adx"] = adx_vals
    df["plus_di"] = plus_di_vals
    df["minus_di"] = minus_di_vals

    # ── Phase 2: 볼린저 밴드 (20, 2σ) ──
    bb_ma = c.rolling(window=20).mean()
    bb_std = c.rolling(window=20).std()
    df["bb_upper"] = bb_ma + bb_std * 2
    df["bb_lower"] = bb_ma - bb_std * 2
    df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / bb_ma.replace(0, np.nan))
    df["bb_middle"] = bb_ma

    # ── Phase 3: MACD (12/26/9) ──
    ema_fast = c.ewm(span=12, adjust=False).mean()
    ema_slow = c.ewm(span=26, adjust=False).mean()
    df["macd_line"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]

    # ── RSI ──
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=engine.rsi_period).mean()
    avg_loss = loss.rolling(window=engine.rsi_period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── 슬로우 RSI (28일) — 멀티 타임프레임 확인용 ──
    delta_slow = c.diff()
    gain_slow = delta_slow.clip(lower=0)
    loss_slow = (-delta_slow).clip(lower=0)
    avg_gain_slow = gain_slow.rolling(window=28).mean()
    avg_loss_slow = loss_slow.rolling(window=28).mean()
    rs_slow = avg_gain_slow / avg_loss_slow.replace(0, np.nan)
    df["rsi_slow"] = 100 - (100 / (1 + rs_slow))

    # ── 거래량 이동평균 ──
    df["volume_ma"] = v.rolling(window=20).mean()

    # ── ATR (14-period) — 동적 트레일링 + 포지션 사이징용 ──
    tr1 = h - lo
    tr2 = (h - c.shift()).abs()
    tr3 = (lo - c.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()
    df["atr_pct"] = df["atr"] / c  # 가격 대비 ATR 비율

    # ── Donchian Channel (20d) — STRONG_BULL Donchian 돌파용 ──
    df["donchian_high"] = h.rolling(20, min_periods=20).max()
    df["donchian_low"] = lo.rolling(20, min_periods=20).min()

    # ── 이격도 (Disparity) — BULL 부분 청산용 ──
    ma20 = c.rolling(window=20).mean()
    df["ma20"] = ma20
    df["disparity_20"] = c / ma20.replace(0, np.nan)

    return df


def confirm_trend(df: pd.DataFrame) -> dict:
    """
    Phase 1: 종목 수준 추세 방향 + 강도 판정.
    Returns: {"direction": "UP"/"DOWN"/"FLAT",
              "strength": "STRONG"/"MODERATE"/"WEAK",
              "aligned": bool, "adx": float, "alignment_score": int}
    """
    default = {"direction": "FLAT", "strength": "WEAK", "aligned": False, "adx": 0}
    if len(df) < 200:
        return default

    curr = df.iloc[-1]
    price = float(curr["close"])

    # 정배열: 3/5 이상이면 정배열 인정
    mas = [curr.get("ma_short"), curr.get("ma_long"), curr.get("ma60"),
           curr.get("ma120"), curr.get("ma200")]
    alignment_score = 0
    if all(pd.notna(m) for m in mas):
        ma_vals = [float(m) for m in mas]
        if price > ma_vals[0]:
            alignment_score += 1
        for i in range(len(ma_vals) - 1):
            if ma_vals[i] > ma_vals[i + 1]:
                alignment_score += 1
        aligned = alignment_score >= 3
    else:
        aligned = False

    # ADX/DMI
    adx = float(curr.get("adx", 0)) if pd.notna(curr.get("adx")) else 0
    plus_di = float(curr.get("plus_di", 0)) if pd.notna(curr.get("plus_di")) else 0
    minus_di = float(curr.get("minus_di", 0)) if pd.notna(curr.get("minus_di")) else 0
    trend_exists = adx > 20
    bullish_di = plus_di > minus_di

    # 종합
    bull_count = sum([aligned, trend_exists and bullish_di])
    if bull_count >= 2:
        direction = "UP"
    elif aligned or (trend_exists and bullish_di):
        direction = "UP"
    elif not aligned and minus_di > plus_di:
        direction = "DOWN"
    else:
        direction = "FLAT"

    strength = "STRONG" if adx > 40 else "MODERATE" if adx > 25 else "WEAK"

    return {"direction": direction, "strength": strength, "aligned": aligned,
            "adx": adx, "alignment_score": alignment_score}


def estimate_trend_stage(df: pd.DataFrame) -> str:
    """
    Phase 2: EARLY / MID / LATE 판정.
    볼린저 밴드 스퀴즈 비율 + RSI + 52주 고점 근접도 종합.
    """
    if len(df) < 50:
        return "MID"

    curr = df.iloc[-1]
    bb_width = float(curr.get("bb_width", 0)) if pd.notna(curr.get("bb_width")) else 0

    # BB 폭 평균 (50일)
    if "bb_width" in df.columns:
        bb_avg_series = df["bb_width"].rolling(window=50).mean()
        bb_width_avg = float(bb_avg_series.iloc[-1]) if pd.notna(bb_avg_series.iloc[-1]) else bb_width
    else:
        bb_width_avg = bb_width
    if bb_width_avg == 0:
        bb_width_avg = bb_width or 1.0

    rsi = float(curr.get("rsi", 50)) if pd.notna(curr.get("rsi")) else 50
    squeeze_ratio = bb_width / bb_width_avg if bb_width_avg > 0 else 1.0

    # 52주 고점 대비
    close_series = df["close"].astype(float)
    window_52w = min(252, len(close_series))
    high_52w = float(close_series.rolling(window=window_52w).max().iloc[-1])
    price = float(curr["close"])
    pct_of_high = (price / high_52w * 100) if high_52w > 0 else 50

    # 판정
    if squeeze_ratio < 0.8 or (squeeze_ratio < 1.2 and rsi < 65):
        return "EARLY"
    # LATE 판정: 점수 기반
    late_score = 0
    if squeeze_ratio > 2.0:
        late_score += 2
    if rsi > 80:
        late_score += 2
    if pct_of_high > 95:
        late_score += 1
    if pct_of_high > 98:
        late_score += 1

    if late_score >= 3:
        return "LATE"
    return "MID"
