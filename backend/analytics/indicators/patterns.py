"""
Chart pattern detection — Triangles, Cup & Handle, Head & Shoulders.

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/patterns.py
"""
import pandas as pd
import numpy as np

def _detect_triangle(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     atr: float, i: int, lookback: int = 30) -> tuple:
    """
    B8: Triangle pattern detector (Symmetric/Ascending/Descending).
    Uses linear regression slopes on recent highs/lows.
    Returns (pattern_name, score, None) or (None, 0, None).
    """
    if i < lookback:
        return None, 0, None

    w_high = high[i - lookback: i].astype(float)
    w_low  = low[i - lookback: i].astype(float)
    x = np.arange(lookback, dtype=float)

    if atr <= 0:
        return None, 0, None

    # Linear regression slopes (ATR-normalized)
    upper_slope = float(np.polyfit(x, w_high, 1)[0]) / atr
    lower_slope = float(np.polyfit(x, w_low,  1)[0]) / atr

    threshold = 0.015  # ATR-normalized slope threshold

    if upper_slope < -threshold and lower_slope > threshold:
        return "SYMMETRIC_TRIANGLE", 55, None   # converging — neutral breakout pending
    elif abs(upper_slope) <= threshold and lower_slope > threshold:
        return "ASCENDING_TRIANGLE", 60, None   # bullish (flat top, rising support)
    elif upper_slope < -threshold and abs(lower_slope) <= threshold:
        return "DESCENDING_TRIANGLE", -50, None # bearish (declining top, flat support)

    return None, 0, None


def _detect_cup_and_handle(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                            volume, i: int, lookback: int = 60) -> tuple:
    """
    B7: Cup & Handle pattern detector for a single bar index i.
    Cup depth: 15-35% below left rim. Handle retracement < 50% of cup.
    Returns (pattern_name, score, price_target) or (None, 0, None).
    """
    if i < lookback:
        return None, 0, None

    window_high = high[i - lookback: i]
    window_low  = low[i - lookback: i]

    left_rim_rel = int(np.argmax(window_high))
    left_rim = float(window_high[left_rim_rel])

    cup_bottom_rel = int(np.argmin(window_low[left_rim_rel:]))
    cup_bottom = float(window_low[left_rim_rel + cup_bottom_rel])

    if left_rim <= 0:
        return None, 0, None

    cup_depth_pct = (left_rim - cup_bottom) / left_rim
    if not (0.15 <= cup_depth_pct <= 0.40):
        return None, 0, None

    # Handle: last 5-25 bars should show smaller range than cup
    handle_len = min(25, i)
    handle_high = np.max(high[i - handle_len: i])
    handle_low  = np.min(low[i - handle_len: i])
    cup_range = left_rim - cup_bottom
    handle_range = handle_high - handle_low
    if cup_range <= 0 or handle_range > 0.5 * cup_range:
        return None, 0, None

    # Breakout: current close near or above left rim (within 3%)
    if close[i] < left_rim * 0.97:
        return None, 0, None

    # Volume: handle should have lower volume than cup (optional check)
    vol_ok = True
    if volume is not None:
        cup_vol_mean = np.mean(volume[i - lookback: i - handle_len]) if (i - lookback) < (i - handle_len) else 1.0
        handle_vol_mean = np.mean(volume[i - handle_len: i]) if handle_len > 0 else 1.0
        vol_ok = handle_vol_mean < cup_vol_mean

    score = 70 if vol_ok else 55
    target = close[i] + cup_range  # price target = cup depth above breakout
    return "CUP_AND_HANDLE", score, target


def detect_chart_patterns(df: pd.DataFrame, swing_length: int = 3) -> pd.DataFrame:
    """
    P3: Classic chart pattern detection using swing points.
    Detects: Double Bottom (+70), Double Top (-70), Bull Flag (+60), Bear Flag (-60).

    Output columns: chart_pattern (str|None), chart_pattern_score (int -100..+100),
                    chart_pattern_target (float|None)
    """
    df = df.copy()
    n = len(df)

    df['chart_pattern'] = None
    df['chart_pattern_score'] = 0
    df['chart_pattern_target'] = None

    if n < 15:
        return df

    close = df['close'].values.astype(float)
    high = df['high'].values.astype(float)
    low = df['low'].values.astype(float)
    open_p = df['open'].values.astype(float)
    volume = df['volume'].values.astype(float) if 'volume' in df.columns else None

    # Compute swing points if missing
    if 'is_swing_high' not in df.columns or 'is_swing_low' not in df.columns:
        df['is_swing_high'] = False
        df['is_swing_low'] = False
        for i in range(swing_length, n - swing_length):
            is_sh = True
            is_sl = True
            for j in range(1, swing_length + 1):
                if high[i] <= high[i - j] or high[i] <= high[i + j]:
                    is_sh = False
                if low[i] >= low[i - j] or low[i] >= low[i + j]:
                    is_sl = False
            if is_sh:
                df.iat[i, df.columns.get_loc('is_swing_high')] = True
            if is_sl:
                df.iat[i, df.columns.get_loc('is_swing_low')] = True

    # Collect swing indices
    sh_positions = [i for i in range(n) if df['is_swing_high'].iloc[i]]
    sl_positions = [i for i in range(n) if df['is_swing_low'].iloc[i]]

    # ATR for flag detection
    atr_arr = np.zeros(n)
    if n >= 14:
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        tr = np.concatenate([[high[0] - low[0]], tr])
        atr_series = pd.Series(tr).rolling(window=14, min_periods=1).mean().values
        atr_arr = atr_series

    # Scan each bar for patterns (check most recent occurrences)
    for i in range(20, n):
        best_pattern = None
        best_score = 0
        best_target = None

        # ── Double Bottom ──
        # Find two swing lows before bar i, separated by 10-50 bars, within 3%
        recent_sl = [pos for pos in sl_positions if pos < i and pos >= i - 60]
        if len(recent_sl) >= 2:
            for k in range(len(recent_sl) - 1, 0, -1):
                sl2 = recent_sl[k]
                for m in range(k - 1, -1, -1):
                    sl1 = recent_sl[m]
                    sep = sl2 - sl1
                    if 10 <= sep <= 50:
                        low1 = low[sl1]
                        low2 = low[sl2]
                        if low1 > 0 and abs(low1 - low2) / low1 < 0.03:
                            neckline = np.max(high[sl1:sl2 + 1])
                            bottom = min(low1, low2)
                            if close[i] > neckline:
                                target = neckline + (neckline - bottom)
                                if abs(70) > abs(best_score):
                                    best_pattern = "DOUBLE_BOTTOM"
                                    best_score = 70
                                    best_target = target
                    if best_pattern:
                        break
                if best_pattern:
                    break

        # ── Double Top ──
        recent_sh = [pos for pos in sh_positions if pos < i and pos >= i - 60]
        if len(recent_sh) >= 2 and best_pattern is None:
            for k in range(len(recent_sh) - 1, 0, -1):
                sh2 = recent_sh[k]
                for m in range(k - 1, -1, -1):
                    sh1 = recent_sh[m]
                    sep = sh2 - sh1
                    if 10 <= sep <= 50:
                        high1 = high[sh1]
                        high2 = high[sh2]
                        if high1 > 0 and abs(high1 - high2) / high1 < 0.03:
                            neckline = np.min(low[sh1:sh2 + 1])
                            top = max(high1, high2)
                            if close[i] < neckline:
                                target = neckline - (top - neckline)
                                if abs(-70) > abs(best_score):
                                    best_pattern = "DOUBLE_TOP"
                                    best_score = -70
                                    best_target = target
                    if best_pattern:
                        break
                if best_pattern:
                    break

        # ── Bull Flag ──
        if i >= 20 and best_pattern is None:
            atr = atr_arr[i] if atr_arr[i] > 0 else 1.0
            # Impulse: check bars i-20 to i-15 for strong up move
            impulse_start = max(0, i - 20)
            impulse_end = max(0, i - 15)
            if impulse_end < n and impulse_start < n:
                impulse_move = close[impulse_end] - close[impulse_start]
                if impulse_move > 2 * atr:
                    # Consolidation: last 10 bars (i-10 to i)
                    consol_start = max(0, i - 10)
                    consol_range = np.max(high[consol_start:i + 1]) - np.min(low[consol_start:i + 1])
                    if consol_range < 0.5 * abs(impulse_move):
                        vol_ok = True
                        if volume is not None:
                            vol_start_mean = np.mean(volume[max(0, i - 15):max(1, i - 10)])
                            vol_end_mean = np.mean(volume[max(0, i - 5):i + 1])
                            vol_ok = vol_end_mean < vol_start_mean
                        if vol_ok:
                            target = close[i] + impulse_move
                            best_pattern = "BULL_FLAG"
                            best_score = 60
                            best_target = target

        # ── Bear Flag ──
        if i >= 20 and best_pattern is None:
            atr = atr_arr[i] if atr_arr[i] > 0 else 1.0
            impulse_start = max(0, i - 20)
            impulse_end = max(0, i - 15)
            if impulse_end < n and impulse_start < n:
                impulse_move = close[impulse_start] - close[impulse_end]  # down move
                if impulse_move > 2 * atr:
                    consol_start = max(0, i - 10)
                    consol_range = np.max(high[consol_start:i + 1]) - np.min(low[consol_start:i + 1])
                    if consol_range < 0.5 * abs(impulse_move):
                        vol_ok = True
                        if volume is not None:
                            vol_start_mean = np.mean(volume[max(0, i - 15):max(1, i - 10)])
                            vol_end_mean = np.mean(volume[max(0, i - 5):i + 1])
                            vol_ok = vol_end_mean < vol_start_mean
                        if vol_ok:
                            target = close[i] - impulse_move
                            best_pattern = "BEAR_FLAG"
                            best_score = -60
                            best_target = target

        # B7: Cup & Handle
        ch_name, ch_score, ch_target = _detect_cup_and_handle(close, high, low, volume, i)
        if abs(ch_score) > abs(best_score):
            best_pattern = ch_name
            best_score = ch_score
            best_target = ch_target

        # B8: Triangle
        atr = atr_arr[i] if i < len(atr_arr) else 0.0
        tri_name, tri_score, tri_target = _detect_triangle(high, low, close, atr, i)
        if tri_name and abs(tri_score) > abs(best_score):
            best_pattern = tri_name
            best_score = tri_score
            best_target = tri_target

        if best_pattern:
            df.iat[i, df.columns.get_loc('chart_pattern')] = best_pattern
            df.iat[i, df.columns.get_loc('chart_pattern_score')] = best_score
            df.iat[i, df.columns.get_loc('chart_pattern_target')] = best_target

    return df


# ============================================================
# B1-B5: Additional Technical Indicators
# ============================================================

