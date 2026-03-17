"""
ES Futures Signal Bot — signal_engine.py
4-Layer entry scoring: Z-Score / Trend / Momentum / Volume
Each layer = 25 pts  →  total 100 pts  →  threshold 60 pts
"""
import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from typing import Optional, Literal
import config as C


# ─── Types ──────────────────────────────────────────────────────────────────
Direction = Literal["LONG", "SHORT", "FLAT"]

@dataclass
class LayerScore:
    l1_zscore:    float = 0.0
    l2_trend:     float = 0.0
    l3_momentum:  float = 0.0
    l4_volume:    float = 0.0
    total:        float = 0.0
    direction:    Direction = "FLAT"
    filtered:     bool  = False          # True = blocked by fake-out filter
    filter_reason: str  = ""

@dataclass
class SignalResult:
    ticker:        str
    timestamp:     pd.Timestamp
    close:         float
    direction:     Direction
    score:         LayerScore
    atr:           float
    adx:           float
    entry_price:   float
    stop_loss:     float
    take_profit:   float
    rr_ratio:      float
    fired:         bool             # True = threshold crossed & not filtered
    note:          str = ""


# ─── Data fetch ─────────────────────────────────────────────────────────────
def fetch_bars(ticker: str = C.ES_TICKER,
               interval: str = C.INTERVAL,
               days: int = C.LOOKBACK_DAYS) -> pd.DataFrame:
    df = yf.download(ticker,
                     period=f"{days}d",
                     interval=interval,
                     auto_adjust=True,
                     progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # yfinance ≥0.2 returns MultiIndex columns — flatten to lowercase
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df.dropna(inplace=True)
    return df


# ─── Indicator helpers ───────────────────────────────────────────────────────
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def _atr(df: pd.DataFrame, n: int = C.ATR_PERIOD) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _adx(df: pd.DataFrame, n: int = C.ADX_PERIOD) -> pd.DataFrame:
    """Returns DataFrame with columns: adx, plus_di, minus_di"""
    h, l, c = df["high"], df["low"], df["close"]
    up   = h - h.shift()
    down = l.shift() - l
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr_s = _atr(df, n)
    plus_di  = 100 * pd.Series(plus_dm,  index=df.index).ewm(span=n, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(span=n, adjust=False).mean() / atr_s
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx = dx.ewm(span=n, adjust=False).mean()
    return pd.DataFrame({"adx": adx, "+di": plus_di, "-di": minus_di})

def _macd(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast   = _ema(s, C.MACD_FAST)
    slow   = _ema(s, C.MACD_SLOW)
    macd   = fast - slow
    signal = _ema(macd, C.MACD_SIGNAL)
    hist   = macd - signal
    return macd, signal, hist

def _rsi(s: pd.Series, n: int = C.RSI_PERIOD) -> pd.Series:
    delta = s.diff()
    gain  = delta.clip(lower=0).ewm(span=n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=n, adjust=False).mean()
    rs    = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)

def _obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()

def _bb(s: pd.Series, n: int = C.BB_PERIOD) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid   = _sma(s, n)
    std   = s.rolling(n).std()
    upper = mid + C.BB_STD * std
    lower = mid - C.BB_STD * std
    return upper, mid, lower

def _bb_bandwidth(s: pd.Series) -> pd.Series:
    upper, mid, lower = _bb(s)
    return (upper - lower) / (mid + 1e-9)


# ─── Layer 1 — Z-Score (25 pts) ─────────────────────────────────────────────
def _score_l1(df: pd.DataFrame) -> tuple[float, float, Direction]:
    """Returns (score, z_value, direction_hint)"""
    c = df["close"]
    roll_mean = c.rolling(C.ZSCORE_PERIOD).mean()
    roll_std  = c.rolling(C.ZSCORE_PERIOD).std()
    z = ((c - roll_mean) / (roll_std + 1e-9)).iloc[-1]

    if z <= C.ZSCORE_LONG:
        score = 25.0
        d: Direction = "LONG"
    elif z >= C.ZSCORE_SHORT:
        score = 25.0
        d = "SHORT"
    elif abs(z) >= 1.5:
        score = 15.0
        d = "LONG" if z < 0 else "SHORT"
    elif abs(z) >= 1.0:
        score = 8.0
        d = "LONG" if z < 0 else "SHORT"
    else:
        score = 0.0
        d = "FLAT"

    return score, round(float(z), 3), d


# ─── Layer 2 — Trend (25 pts) ────────────────────────────────────────────────
def _score_l2(df: pd.DataFrame) -> tuple[float, Direction]:
    c    = df["close"]
    e10  = _ema(c, C.EMA_SHORT).iloc[-1]
    e20  = _ema(c, C.EMA_MED).iloc[-1]
    e50  = _ema(c, C.EMA_LONG).iloc[-1]
    ma200_s = _sma(c, C.MA200)
    ma200     = ma200_s.iloc[-1]
    ma200_prev= ma200_s.iloc[-5]
    slope_up  = ma200 > ma200_prev
    slope_dn  = ma200 < ma200_prev
    close     = c.iloc[-1]

    score = 0.0
    d: Direction = "FLAT"

    # Bullish stack
    if e10 > e20 > e50 and close > ma200:
        score = 25.0
        d = "LONG"
    elif e10 > e20 > e50 and slope_up:
        score = 18.0
        d = "LONG"
    elif e10 > e20 and close > ma200:
        score = 12.0
        d = "LONG"
    # Bearish stack
    elif e10 < e20 < e50 and close < ma200:
        score = 25.0
        d = "SHORT"
    elif e10 < e20 < e50 and slope_dn:
        score = 18.0
        d = "SHORT"
    elif e10 < e20 and close < ma200:
        score = 12.0
        d = "SHORT"

    return score, d


# ─── Layer 3 — Momentum (25 pts) ────────────────────────────────────────────
def _score_l3(df: pd.DataFrame) -> tuple[float, Direction]:
    c = df["close"]
    macd, signal, hist = _macd(c)
    adx_df = _adx(df)
    adx  = adx_df["adx"].iloc[-1]
    pdi  = adx_df["+di"].iloc[-1]
    mdi  = adx_df["-di"].iloc[-1]
    rsi  = _rsi(c).iloc[-1]

    # MACD cross (1-bar lookback)
    macd_cross_up   = hist.iloc[-1] > 0 and hist.iloc[-2] <= 0
    macd_cross_dn   = hist.iloc[-1] < 0 and hist.iloc[-2] >= 0
    macd_above_zero = hist.iloc[-1] > 0
    macd_below_zero = hist.iloc[-1] < 0

    # ADX strength
    adx_strong   = adx >= 25
    di_long      = pdi > mdi
    di_short     = mdi > pdi

    # RSI range filter
    rsi_long_ok  = 30 <= rsi <= 60
    rsi_short_ok = 40 <= rsi <= 70

    score = 0.0
    d: Direction = "FLAT"

    if (macd_cross_up or macd_above_zero) and adx_strong and di_long and rsi_long_ok:
        score = 25.0
        d = "LONG"
    elif (macd_cross_up or macd_above_zero) and di_long and rsi_long_ok:
        score = 15.0
        d = "LONG"
    elif macd_above_zero and di_long:
        score = 8.0
        d = "LONG"
    elif (macd_cross_dn or macd_below_zero) and adx_strong and di_short and rsi_short_ok:
        score = 25.0
        d = "SHORT"
    elif (macd_cross_dn or macd_below_zero) and di_short and rsi_short_ok:
        score = 15.0
        d = "SHORT"
    elif macd_below_zero and di_short:
        score = 8.0
        d = "SHORT"

    return score, d


# ─── Layer 4 — Volume (25 pts) ──────────────────────────────────────────────
def _score_l4(df: pd.DataFrame) -> tuple[float, Direction]:
    vol   = df["volume"]
    close = df["close"]

    avg_vol     = vol.rolling(20).mean().iloc[-1]
    cur_vol     = vol.iloc[-1]
    vol_spike   = cur_vol > avg_vol * C.VOL_SPIKE_MULT

    obv_s       = _obv(df)
    obv_up      = obv_s.iloc[-1] > obv_s.iloc[-3]   # 3-bar OBV slope

    bw          = _bb_bandwidth(close)
    bw_mean     = bw.rolling(50).mean().iloc[-1]
    bb_squeeze  = bw.iloc[-1] < bw_mean * 0.8        # bandwidth contraction

    score = 0.0
    d: Direction = "FLAT"

    long_dir  = close.diff().iloc[-1] > 0
    short_dir = close.diff().iloc[-1] < 0

    if vol_spike and obv_up and long_dir:
        score = 25.0 if bb_squeeze else 20.0
        d = "LONG"
    elif vol_spike and not obv_up and short_dir:
        score = 25.0 if bb_squeeze else 20.0
        d = "SHORT"
    elif vol_spike and long_dir:
        score = 15.0
        d = "LONG"
    elif vol_spike and short_dir:
        score = 15.0
        d = "SHORT"
    elif obv_up and long_dir:
        score = 8.0
        d = "LONG"
    elif not obv_up and short_dir:
        score = 8.0
        d = "SHORT"

    return score, d


# ─── Fake-out filter ────────────────────────────────────────────────────────
def _fakeout_filter(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Returns (blocked, reason).
    Blocks if:
      - Low-volume candle  (vol < 70 % of 20-bar avg)
      - Long wick candle   (wick/body ratio > 3.0)
    """
    row = df.iloc[-1]
    avg_vol = df["volume"].rolling(20).mean().iloc[-1]
    if row["volume"] < avg_vol * 0.70:
        return True, "low volume candle"

    body  = abs(row["close"] - row["open"])
    wick  = row["high"] - row["low"] - body
    if body > 0 and wick / body > 3.0:
        return True, f"long wick (ratio={wick/body:.1f})"

    return False, ""


# ─── ATR breakout filter ────────────────────────────────────────────────────
def _atr_breakout(df: pd.DataFrame) -> bool:
    atr = _atr(df).iloc[-1]
    bar_range = df["high"].iloc[-1] - df["low"].iloc[-1]
    return bar_range > atr * 1.2


# ─── Master entry evaluator ─────────────────────────────────────────────────
def evaluate_entry(df: pd.DataFrame) -> SignalResult:
    close_px  = float(df["close"].iloc[-1])
    atr_val   = float(_atr(df).iloc[-1])
    adx_val   = float(_adx(df)["adx"].iloc[-1])
    ts        = df.index[-1]

    l1_score, z_val, l1_dir = _score_l1(df)
    l2_score, l2_dir         = _score_l2(df)
    l3_score, l3_dir         = _score_l3(df)
    l4_score, l4_dir         = _score_l4(df)

    total = l1_score + l2_score + l3_score + l4_score

    # Determine direction by majority vote
    votes = [d for d in [l1_dir, l2_dir, l3_dir, l4_dir] if d != "FLAT"]
    if not votes:
        direction: Direction = "FLAT"
    else:
        direction = max(set(votes), key=votes.count)

    layer = LayerScore(
        l1_zscore=l1_score, l2_trend=l2_score,
        l3_momentum=l3_score, l4_volume=l4_score,
        total=total, direction=direction
    )

    # Fake-out filter
    blocked, reason = _fakeout_filter(df)
    if blocked:
        layer.filtered = True
        layer.filter_reason = reason

    # ATR filter
    if not _atr_breakout(df):
        layer.filtered = True
        layer.filter_reason = layer.filter_reason or "no ATR breakout"

    # Stop-loss & take-profit
    mult = C.ATR_SL_MULT_TRENDING if adx_val >= 25 else C.ATR_SL_MULT_RANGING
    if direction == "LONG":
        stop_loss   = close_px - mult * atr_val
        take_profit = close_px + C.ATR_TP_MULT * atr_val
    elif direction == "SHORT":
        stop_loss   = close_px + mult * atr_val
        take_profit = close_px - C.ATR_TP_MULT * atr_val
    else:
        stop_loss = take_profit = close_px

    risk   = abs(close_px - stop_loss)
    reward = abs(close_px - take_profit)
    rr     = reward / (risk + 1e-9)

    fired = (
        total >= C.ENTRY_THRESHOLD
        and direction != "FLAT"
        and not layer.filtered
        and rr >= C.RR_MIN
    )

    return SignalResult(
        ticker=C.ES_TICKER,
        timestamp=ts,
        close=close_px,
        direction=direction,
        score=layer,
        atr=round(atr_val, 2),
        adx=round(adx_val, 2),
        entry_price=round(close_px, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        rr_ratio=round(rr, 2),
        fired=fired,
        note=f"z={z_val}"
    )
