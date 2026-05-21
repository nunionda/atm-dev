"""
Candlestick pattern detection (Hammer, Engulfing, Doji, Three Soldiers, etc.).

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/candlestick.py
"""
import pandas as pd
import numpy as np

def calculate_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    P2: Vectorized candlestick pattern detector.
    Detects 12 patterns (Tier 1 base ±30, Tier 2 base ±15).
    Output columns: candle_pattern (str|None), candle_score (int, -100 to +100).
    """
    if len(df) < 3:
        df['candle_pattern'] = None
        df['candle_score'] = 0
        return df

    df = df.copy()
    close = df['close'].values.astype(float)
    open_p = df['open'].values.astype(float)
    high = df['high'].values.astype(float)
    low = df['low'].values.astype(float)
    volume = df['volume'].values.astype(float) if 'volume' in df.columns else None
    n = len(df)

    body = close - open_p
    body_abs = np.abs(body)
    upper_shadow = high - np.maximum(close, open_p)
    lower_shadow = np.minimum(close, open_p) - low
    hl_range = high - low
    # Avoid division by zero
    hl_range_safe = np.where(hl_range > 0, hl_range, 1.0)
    body_abs_safe = np.where(body_abs > 0, body_abs, 1e-10)

    # Bullish/Bearish candle flags
    is_bullish = body > 0
    is_bearish = body < 0

    # Previous bar values (shifted by 1)
    prev_close = np.roll(close, 1)
    prev_open = np.roll(open_p, 1)
    prev_high = np.roll(high, 1)
    prev_low = np.roll(low, 1)
    prev_body = np.roll(body, 1)
    prev_body_abs = np.roll(body_abs, 1)
    prev_bullish = np.roll(is_bullish, 1)
    prev_bearish = np.roll(is_bearish, 1)

    # 2-bars-ago values (shifted by 2)
    prev2_close = np.roll(close, 2)
    prev2_open = np.roll(open_p, 2)
    prev2_body = np.roll(body, 2)
    prev2_hl_range = np.roll(hl_range, 2)

    # Initialize score and pattern arrays
    scores = np.zeros(n, dtype=float)
    patterns = np.full(n, None, dtype=object)
    pattern_scores = np.zeros(n, dtype=float)  # track strongest pattern score per bar

    # ═══ Tier 1 Patterns (base ±30) ═══

    # 1. Bullish Engulfing: prev bearish, curr bullish, curr body covers prev body
    bull_engulf = (
        prev_bearish & is_bullish &
        (open_p <= prev_close) & (close >= prev_open)
    )
    bull_engulf[:1] = False
    scores += np.where(bull_engulf, 30, 0)
    _update_pattern(patterns, pattern_scores, bull_engulf, "BULLISH_ENGULFING", 30)

    # 2. Bearish Engulfing: prev bullish, curr bearish, curr body covers prev body
    bear_engulf = (
        prev_bullish & is_bearish &
        (open_p >= prev_close) & (close <= prev_open)
    )
    bear_engulf[:1] = False
    scores += np.where(bear_engulf, -30, 0)
    _update_pattern(patterns, pattern_scores, bear_engulf, "BEARISH_ENGULFING", 30)

    # 3. Hammer: small body at top, lower shadow >= 2x body, upper shadow < body, after 3+ down bars
    hammer_shape = (
        (body_abs > 0) &
        (lower_shadow >= 2 * body_abs) &
        (upper_shadow < body_abs)
    )
    # Context: 3+ consecutive down bars before
    down_count = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] < open_p[i - 1]:
            down_count[i] = down_count[i - 1] + 1
        else:
            down_count[i] = 0
    hammer = hammer_shape & (down_count >= 3)
    scores += np.where(hammer, 30, 0)
    _update_pattern(patterns, pattern_scores, hammer, "HAMMER", 30)

    # 4a. Shooting Star: small body at bottom, upper shadow >= 2x body, after 3+ up bars
    shooting_shape = (
        (body_abs > 0) &
        (upper_shadow >= 2 * body_abs) &
        (lower_shadow < body_abs)
    )
    up_count = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > open_p[i - 1]:
            up_count[i] = up_count[i - 1] + 1
        else:
            up_count[i] = 0
    shooting_star = shooting_shape & (up_count >= 3)
    scores += np.where(shooting_star, -30, 0)
    _update_pattern(patterns, pattern_scores, shooting_star, "SHOOTING_STAR", 30)

    # 4b. Inverted Hammer: upper shadow >= 2x body, after 3+ down bars (bullish reversal)
    inv_hammer = shooting_shape & (down_count >= 3)
    scores += np.where(inv_hammer, 25, 0)
    _update_pattern(patterns, pattern_scores, inv_hammer, "INVERTED_HAMMER", 25)

    # 5. Morning Star: bearish -> small body -> bullish, 3rd close > midpoint of 1st body
    prev2_bearish_ms = prev2_body < 0
    prev1_doji = np.roll(body_abs, 1) < 0.1 * np.roll(hl_range_safe, 1)
    prev2_midpoint = prev2_open + prev2_body / 2
    morning_star = (
        prev2_bearish_ms & prev1_doji & is_bullish &
        (close > prev2_midpoint)
    )
    morning_star[:2] = False
    scores += np.where(morning_star, 30, 0)
    _update_pattern(patterns, pattern_scores, morning_star, "MORNING_STAR", 30)

    # 6. Evening Star: bullish -> small body -> bearish, 3rd close < midpoint of 1st body
    prev2_bullish_es = prev2_body > 0
    evening_star = (
        prev2_bullish_es & prev1_doji & is_bearish &
        (close < prev2_midpoint)
    )
    evening_star[:2] = False
    scores += np.where(evening_star, -30, 0)
    _update_pattern(patterns, pattern_scores, evening_star, "EVENING_STAR", 30)

    # 7. Three White Soldiers: 3 consecutive bullish, higher closes, each opens within prev body
    prev2_bullish_flag = np.roll(is_bullish, 2)
    prev1_bullish_flag = np.roll(is_bullish, 1)
    higher_closes = (close > prev_close) & (prev_close > prev2_close)
    opens_in_prev_body = (
        (open_p >= np.minimum(prev_close, prev_open)) & (open_p <= np.maximum(prev_close, prev_open)) &
        (prev_open >= np.minimum(prev2_close, prev2_open)) & (prev_open <= np.maximum(prev2_close, prev2_open))
    )
    three_white = prev2_bullish_flag & prev1_bullish_flag & is_bullish & higher_closes & opens_in_prev_body
    three_white[:2] = False
    scores += np.where(three_white, 30, 0)
    _update_pattern(patterns, pattern_scores, three_white, "THREE_WHITE_SOLDIERS", 30)

    # 8. Three Black Crows: 3 consecutive bearish, lower closes, each opens within prev body
    prev2_bearish_flag = np.roll(is_bearish, 2)
    prev1_bearish_flag = np.roll(is_bearish, 1)
    lower_closes = (close < prev_close) & (prev_close < prev2_close)
    opens_in_prev_body_bear = (
        (open_p >= np.minimum(prev_close, prev_open)) & (open_p <= np.maximum(prev_close, prev_open)) &
        (prev_open >= np.minimum(prev2_close, prev2_open)) & (prev_open <= np.maximum(prev2_close, prev2_open))
    )
    three_black = prev2_bearish_flag & prev1_bearish_flag & is_bearish & lower_closes & opens_in_prev_body_bear
    three_black[:2] = False
    scores += np.where(three_black, -30, 0)
    _update_pattern(patterns, pattern_scores, three_black, "THREE_BLACK_CROWS", 30)

    # ═══ Tier 2 Patterns (base ±15) ═══

    # 9. Doji: body < 10% of hl_range
    doji = body_abs < 0.1 * hl_range_safe
    dragonfly = doji & (lower_shadow > 2 * upper_shadow) & (lower_shadow > 0)
    gravestone = doji & (upper_shadow > 2 * lower_shadow) & (upper_shadow > 0)
    scores += np.where(dragonfly, 15, 0)
    scores += np.where(gravestone, -15, 0)
    _update_pattern(patterns, pattern_scores, dragonfly, "DRAGONFLY_DOJI", 15)
    _update_pattern(patterns, pattern_scores, gravestone, "GRAVESTONE_DOJI", 15)

    # 10. Piercing Line: prev bearish, open < prev low, close > prev body midpoint
    prev_mid_bear = prev_open + prev_body / 2  # midpoint of prev body (bearish: open > close)
    piercing = (
        prev_bearish & is_bullish &
        (open_p < prev_low) &
        (close > prev_mid_bear)
    )
    piercing[:1] = False
    scores += np.where(piercing, 15, 0)
    _update_pattern(patterns, pattern_scores, piercing, "PIERCING_LINE", 15)

    # 11. Dark Cloud Cover: prev bullish, open > prev high, close < prev body midpoint
    prev_mid_bull = prev_open + prev_body / 2
    dark_cloud = (
        prev_bullish & is_bearish &
        (open_p > prev_high) &
        (close < prev_mid_bull)
    )
    dark_cloud[:1] = False
    scores += np.where(dark_cloud, -15, 0)
    _update_pattern(patterns, pattern_scores, dark_cloud, "DARK_CLOUD_COVER", 15)

    # 12. Harami: current body entirely within prev body
    bull_harami = (
        prev_bearish & is_bullish &
        (open_p >= prev_close) & (close <= prev_open)
    )
    bear_harami = (
        prev_bullish & is_bearish &
        (open_p <= prev_close) & (close >= prev_open)
    )
    bull_harami[:1] = False
    bear_harami[:1] = False
    scores += np.where(bull_harami, 15, 0)
    scores += np.where(bear_harami, -15, 0)
    _update_pattern(patterns, pattern_scores, bull_harami, "BULLISH_HARAMI", 15)
    _update_pattern(patterns, pattern_scores, bear_harami, "BEARISH_HARAMI", 15)

    # ═══ Context Multipliers ═══

    # Volume confirmation: volume > MA20 * 1.5 → multiply by 1.2
    if volume is not None and len(volume) >= 20:
        vol_ma20 = pd.Series(volume).rolling(window=20, min_periods=1).mean().values
        vol_confirm = volume > vol_ma20 * 1.5
        scores = np.where(vol_confirm & (scores != 0), scores * 1.2, scores)

    # Reversal context: 3+ consecutive opposite trend bars → multiply by 1.3
    # For positive scores (bullish), check 3+ down bars before; for negative, 3+ up bars
    reversal_bull = (scores > 0) & (down_count >= 3)
    reversal_bear = (scores < 0) & (up_count >= 3)
    scores = np.where(reversal_bull, scores * 1.3, scores)
    scores = np.where(reversal_bear, scores * 1.3, scores)

    # Clamp to [-100, +100]
    scores = np.clip(scores, -100, 100).astype(int)

    df['candle_pattern'] = patterns
    df['candle_score'] = scores

    return df


def _update_pattern(patterns: np.ndarray, pattern_scores: np.ndarray,
                    mask: np.ndarray, label: str, abs_score: float):
    """Helper: update pattern label where this pattern is stronger than existing."""
    update_mask = mask & (abs_score > pattern_scores)
    patterns[update_mask] = label
    pattern_scores[update_mask] = abs_score


