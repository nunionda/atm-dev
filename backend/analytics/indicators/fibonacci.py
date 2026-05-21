"""
Fibonacci retracement levels from swing high/low detection.

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/fibonacci.py
"""
import pandas as pd
import numpy as np

# Phase 4.A: fibonacci uses calculate_smc for swing point reuse.
from .smc import calculate_smc


def calculate_fibonacci_levels(df: pd.DataFrame, swing_length: int = 3) -> pd.DataFrame:
    """
    P3: Fibonacci retracement/extension levels based on recent swing high/low.
    Reuses is_swing_high/is_swing_low from calculate_smc() if available.

    Output columns: fib_236, fib_382, fib_500, fib_618, fib_786,
                    fib_ext_1272, fib_ext_1618, fib_trend ("UP"/"DOWN")
    """
    df = df.copy()

    # Compute swing points if not already present
    if 'is_swing_high' not in df.columns or 'is_swing_low' not in df.columns:
        highs = df['high'].values
        lows = df['low'].values
        length = len(df)
        df['is_swing_high'] = False
        df['is_swing_low'] = False
        for i in range(swing_length, length - swing_length):
            is_sh = True
            is_sl = True
            for j in range(1, swing_length + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_sh = False
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_sl = False
            if is_sh:
                df.at[df.index[i], 'is_swing_high'] = True
            if is_sl:
                df.at[df.index[i], 'is_swing_low'] = True

    # Initialize output columns
    fib_cols = ['fib_236', 'fib_382', 'fib_500', 'fib_618', 'fib_786',
                'fib_ext_1272', 'fib_ext_1618']
    for col in fib_cols:
        df[col] = None
    df['fib_trend'] = None

    # Find most recent confirmed swing high and swing low
    sh_mask = df['is_swing_high'] == True  # noqa: E712
    sl_mask = df['is_swing_low'] == True   # noqa: E712

    sh_indices = df.index[sh_mask]
    sl_indices = df.index[sl_mask]

    if len(sh_indices) == 0 or len(sl_indices) == 0:
        return df

    last_sh_idx = sh_indices[-1]
    last_sl_idx = sl_indices[-1]
    last_sh_pos = df.index.get_loc(last_sh_idx)
    last_sl_pos = df.index.get_loc(last_sl_idx)

    swing_high = float(df.loc[last_sh_idx, 'high'])
    swing_low = float(df.loc[last_sl_idx, 'low'])
    swing_range = swing_high - swing_low

    if swing_range <= 0:
        return df

    # Determine trend: if swing low is more recent → uptrend (retracing from high)
    # if swing high is more recent → downtrend (bouncing from low)
    ratios_ret = [0.236, 0.382, 0.5, 0.618, 0.786]
    ratios_ext = [1.272, 1.618]

    if last_sl_pos > last_sh_pos:
        # Downtrend: swing high then swing low, price bouncing from low
        trend = "DOWN"
        fib_ret = [swing_low + swing_range * r for r in ratios_ret]
        fib_ext = [swing_low - swing_range * (r - 1.0) for r in ratios_ext]
    else:
        # Uptrend: swing low then swing high, price retracing from high
        trend = "UP"
        fib_ret = [swing_high - swing_range * r for r in ratios_ret]
        fib_ext = [swing_high + swing_range * (r - 1.0) for r in ratios_ext]

    # Set fib levels as constant across all rows (current levels)
    df['fib_236'] = fib_ret[0]
    df['fib_382'] = fib_ret[1]
    df['fib_500'] = fib_ret[2]
    df['fib_618'] = fib_ret[3]
    df['fib_786'] = fib_ret[4]
    df['fib_ext_1272'] = fib_ext[0]
    df['fib_ext_1618'] = fib_ext[1]
    df['fib_trend'] = trend

    return df


