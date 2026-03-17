"""
ES Futures Signal Bot — exit_engine.py
7-priority exit signal evaluation for open positions.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np
import config as C
from signal_engine import _atr, _adx, _macd


EXIT_PRIORITY = {
    "ES1":           1,   # Hard SL -3%
    "ES_ATR_SL":     2,   # Dynamic ATR stop
    "ES_ATR_TP":     3,   # ATR×3 take-profit
    "ES_CHANDELIER": 4,   # Chandelier exit
    "ES3":           5,   # Progressive trailing
    "ES_CHOCH":      6,   # MACD reversal
    "ES5":           7,   # Max hold 20 days
}


@dataclass
class ExitSignal:
    triggered:    bool
    exit_id:      str
    priority:     int
    reason:       str
    exit_price:   float
    pnl_pct:      float


def evaluate_exit(df: pd.DataFrame,
                  entry_price: float,
                  direction: str,       # "LONG" | "SHORT"
                  entry_time: pd.Timestamp,
                  highest_price: float,   # running max (long) / min (short)
                  equity: float = C.EQUITY) -> Optional[ExitSignal]:
    """
    Returns the highest-priority exit that has triggered, or None.
    Call once per bar on an open position.
    """
    close   = float(df["close"].iloc[-1])
    atr_val = float(_atr(df).iloc[-1])
    adx_val = float(_adx(df)["adx"].iloc[-1])
    now     = df.index[-1]

    if direction == "LONG":
        sign   = 1
        pnl_pct = (close - entry_price) / entry_price
    else:
        sign   = -1
        pnl_pct = (entry_price - close) / entry_price

    candidates: list[ExitSignal] = []

    # ── ES1: Hard stop -3 % ─────────────────────────────────────────────
    if pnl_pct <= -C.HARD_SL_PCT:
        candidates.append(ExitSignal(
            triggered=True, exit_id="ES1", priority=1,
            reason=f"Hard SL triggered ({pnl_pct*100:.2f}%)",
            exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
        ))

    # ── ES_ATR_SL: Dynamic ATR stop ─────────────────────────────────────
    mult = C.ATR_SL_MULT_TRENDING if adx_val >= 25 else C.ATR_SL_MULT_RANGING
    if direction == "LONG":
        atr_sl = entry_price - mult * atr_val
        if close <= atr_sl:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_ATR_SL", priority=2,
                reason=f"ATR SL hit (ADX={adx_val:.1f}, mult={mult}x)",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))
    else:
        atr_sl = entry_price + mult * atr_val
        if close >= atr_sl:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_ATR_SL", priority=2,
                reason=f"ATR SL hit (ADX={adx_val:.1f}, mult={mult}x)",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))

    # ── ES_ATR_TP: ATR×3 take-profit ────────────────────────────────────
    if direction == "LONG":
        atr_tp = entry_price + C.ATR_TP_MULT * atr_val
        if close >= atr_tp:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_ATR_TP", priority=3,
                reason=f"ATR TP hit ({C.ATR_TP_MULT}×ATR, R:R≥{C.RR_MIN})",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))
    else:
        atr_tp = entry_price - C.ATR_TP_MULT * atr_val
        if close <= atr_tp:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_ATR_TP", priority=3,
                reason=f"ATR TP hit ({C.ATR_TP_MULT}×ATR, R:R≥{C.RR_MIN})",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))

    # ── ES_CHANDELIER ────────────────────────────────────────────────────
    if direction == "LONG":
        chandelier = df["high"].rolling(22).max().iloc[-1] - C.CHANDELIER_MULT * atr_val
        if close <= chandelier:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_CHANDELIER", priority=4,
                reason=f"Chandelier exit (highest-{C.CHANDELIER_MULT}×ATR)",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))
    else:
        chandelier = df["low"].rolling(22).min().iloc[-1] + C.CHANDELIER_MULT * atr_val
        if close >= chandelier:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES_CHANDELIER", priority=4,
                reason=f"Chandelier exit (lowest+{C.CHANDELIER_MULT}×ATR)",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))

    # ── ES3: Progressive trailing (activates at +2 %) ───────────────────
    if pnl_pct >= C.TRAIL_ACTIVATE:
        # tighten trail as profit grows
        if pnl_pct >= 0.05:
            trail_pct = 0.005      # 0.5 %
        elif pnl_pct >= 0.03:
            trail_pct = 0.010      # 1.0 %
        else:
            trail_pct = 0.015      # 1.5 %

        if direction == "LONG":
            trail_stop = highest_price * (1 - trail_pct)
            if close <= trail_stop:
                candidates.append(ExitSignal(
                    triggered=True, exit_id="ES3", priority=5,
                    reason=f"Progressive trail ({trail_pct*100:.1f}% below {highest_price:.2f})",
                    exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
                ))
        else:
            trail_stop = highest_price * (1 + trail_pct)
            if close >= trail_stop:
                candidates.append(ExitSignal(
                    triggered=True, exit_id="ES3", priority=5,
                    reason=f"Progressive trail ({trail_pct*100:.1f}% above {highest_price:.2f})",
                    exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
                ))

    # ── ES_CHOCH: MACD reversal ──────────────────────────────────────────
    _, _, hist = _macd(df["close"])
    macd_reversed = (
        (direction == "LONG"  and hist.iloc[-1] < 0 and hist.iloc[-2] >= 0) or
        (direction == "SHORT" and hist.iloc[-1] > 0 and hist.iloc[-2] <= 0)
    )
    if macd_reversed:
        candidates.append(ExitSignal(
            triggered=True, exit_id="ES_CHOCH", priority=6,
            reason="MACD histogram reversal (change of character)",
            exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
        ))

    # ── ES5: Max hold 20 days ────────────────────────────────────────────
    if isinstance(entry_time, pd.Timestamp) and isinstance(now, pd.Timestamp):
        hold_days = (now - entry_time).days
        if hold_days >= C.MAX_HOLD_DAYS:
            candidates.append(ExitSignal(
                triggered=True, exit_id="ES5", priority=7,
                reason=f"Max hold period reached ({hold_days} days)",
                exit_price=close, pnl_pct=round(pnl_pct * 100, 2)
            ))

    if not candidates:
        return None

    # Return highest-priority (lowest number) exit
    return sorted(candidates, key=lambda e: e.priority)[0]
