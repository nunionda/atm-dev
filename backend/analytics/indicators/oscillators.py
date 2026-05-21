"""
Additional oscillators — Connors RSI, Williams %R, MFI, Z-Score, CMF.

Phase 4.A 분할: ats/analytics/indicators.py → ats/analytics/indicators/oscillators.py
"""
import pandas as pd
import numpy as np

def calculate_connors_rsi(df: pd.DataFrame, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> pd.DataFrame:
    """
    B1: Connors RSI — composite momentum/reversion indicator.
    Components:
      1. RSI(3) — fast price RSI
      2. Streak RSI(2) — RSI of consecutive up/down day count
      3. PercentRank(100) — percentile rank of today's 1-day return in last 100 bars
    Output columns: crsi (float 0-100), crsi_oversold (bool: crsi < 15), crsi_overbought (bool: crsi > 80)
    """
    df = df.copy()
    close = df['close'].astype(float)

    # Component 1: Fast RSI(3)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    rs1 = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
    rsi3 = 100 - (100 / (1 + rs1))

    # Component 2: Streak RSI
    # Count consecutive up (+) or down (-) days
    direction = np.sign(close.diff()).fillna(0)
    streak = pd.Series(0.0, index=df.index)
    current_streak = 0.0
    for idx in range(len(direction)):
        d = direction.iloc[idx]
        if d > 0:
            current_streak = max(0, current_streak) + 1
        elif d < 0:
            current_streak = min(0, current_streak) - 1
        else:
            current_streak = 0.0
        streak.iloc[idx] = current_streak

    # Apply RSI(2) to streak values
    s_delta = streak.diff()
    s_gain = s_delta.clip(lower=0)
    s_loss = (-s_delta).clip(lower=0)
    s_avg_gain = s_gain.ewm(com=streak_period - 1, min_periods=streak_period).mean()
    s_avg_loss = s_loss.ewm(com=streak_period - 1, min_periods=streak_period).mean()
    rs2 = s_avg_gain / s_avg_loss.replace(0, np.finfo(float).eps)
    streak_rsi = 100 - (100 / (1 + rs2))

    # Component 3: PercentRank(100) — where today's return ranks vs last 100
    daily_ret = close.pct_change()
    percent_rank = daily_ret.rolling(rank_period).apply(
        lambda x: float((x[:-1] < x[-1]).sum()) / max(len(x) - 1, 1) * 100,
        raw=True
    )

    # Composite: average of 3 components
    crsi = (rsi3 + streak_rsi + percent_rank) / 3.0
    crsi = crsi.clip(0, 100)

    df['crsi'] = crsi
    df['crsi_oversold'] = crsi < 15
    df['crsi_overbought'] = crsi > 80
    return df


def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    B2: Williams %R — momentum/mean-reversion oscillator.
    Range: -100 to 0. Oversold < -80, Overbought > -20.
    Output columns: williams_r (float), williams_r_oversold (bool: wr < -80)
    """
    df = df.copy()
    highest_high = df['high'].rolling(period).max()
    lowest_low = df['low'].rolling(period).min()
    denom = (highest_high - lowest_low).replace(0, np.finfo(float).eps)
    df['williams_r'] = (highest_high - df['close']) / denom * -100
    df['williams_r_oversold'] = df['williams_r'] < -80
    return df


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    B3: Money Flow Index (MFI) — volume-weighted RSI.
    Oversold < 20, Overbought > 80.
    Also detects bearish divergence: price at 20-bar high but MFI declining.
    Output columns: mfi (float 0-100), mfi_bear_div (int 0/1)
    """
    df = df.copy()
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    raw_mf = tp * df['volume']

    # Positive / Negative money flow
    pos_mf = raw_mf.where(tp > tp.shift(1), 0.0)
    neg_mf = raw_mf.where(tp < tp.shift(1), 0.0)

    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum().replace(0, np.finfo(float).eps)

    mfr = pos_sum / neg_sum
    df['mfi'] = 100 - (100 / (1 + mfr))
    df['mfi'] = df['mfi'].clip(0, 100)

    # Bearish divergence: price at new 20-bar high but MFI trending down
    price_new_high = df['close'] > df['close'].rolling(20).max().shift(1)
    mfi_declining = df['mfi'] < df['mfi'].shift(5)
    df['mfi_bear_div'] = (price_new_high & mfi_declining).astype(int)

    return df


def calculate_zscore(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    B4: Rolling Z-score normalization of price.
    Z < -2.0 = statistically oversold (MR entry signal)
    Z > +2.0 = statistically overbought (MR exit / short signal)
    Output columns: zscore (float)
    """
    df = df.copy()
    roll_mean = df['close'].rolling(period).mean()
    roll_std = df['close'].rolling(period).std().replace(0, np.finfo(float).eps)
    df['zscore'] = (df['close'] - roll_mean) / roll_std
    return df


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    B5: Chaikin Money Flow — institutional accumulation/distribution.
    CMF > 0.05 = bullish (buying pressure), < -0.05 = bearish.
    Output columns: cmf (float -1 to +1)
    """
    df = df.copy()
    hl_range = (df['high'] - df['low']).replace(0, np.finfo(float).eps)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_range
    mfm = mfm.fillna(0.0)
    vol_sum = df['volume'].rolling(period).sum().replace(0, np.finfo(float).eps)
    df['cmf'] = (mfm * df['volume']).rolling(period).sum() / vol_sum
    df['cmf'] = df['cmf'].clip(-1, 1)
    return df
