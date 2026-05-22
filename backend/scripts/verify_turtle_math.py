"""
Turtle 청산 % 검증 — ATR 계산 방식(SMA vs Wilder) + 가격변화% + $손실 + equity% 명시적 분리.

검증 대상:
1. ATR(20) — SMA 방식 vs Wilder EMA 방식 차이
2. 가격 변화 % = 2N / Entry × 100
3. $ 손실 = price change × multiplier
4. Equity Risk % = $ 손실 / equity × 100
5. Effective SL 선택 룰 — LONG: max(2N_price, hard_price)
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "http://localhost:8000/api/v1"

TICKERS = {
    "ES=F": {"mult": 50.0, "decimals": 2},
    "NQ=F": {"mult": 20.0, "decimals": 2},
    "CL=F": {"mult": 1000.0, "decimals": 2},
    "GC=F": {"mult": 100.0, "decimals": 1},
}


def get_candles(ticker: str) -> list[dict]:
    url = f"{BASE}/analyze/{ticker}?" + urllib.parse.urlencode({"period": "3mo", "interval": "1d"})
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode()).get("data", [])


def true_range(h: float, l: float, prev_close: float) -> float:
    return max(h - l, abs(h - prev_close), abs(l - prev_close))


def atr_sma(candles: list[dict], period: int = 20) -> float:
    """ATR SMA (단순 평균) — 우리 Turtle 구현 방식."""
    if len(candles) < period + 1:
        return 0.0
    trs = [true_range(candles[i]["high"], candles[i]["low"], candles[i - 1]["close"])
           for i in range(1, len(candles))]
    return sum(trs[-period:]) / period


def atr_wilder(candles: list[dict], period: int = 20) -> float:
    """ATR Wilder EMA (원조) — α = 1/N."""
    if len(candles) < period + 1:
        return 0.0
    trs = [true_range(candles[i]["high"], candles[i]["low"], candles[i - 1]["close"])
           for i in range(1, len(candles))]
    # Initial: SMA of first `period` TRs
    atr = sum(trs[:period]) / period
    # Wilder smoothing for remaining
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def main():
    print("=" * 105)
    print("Turtle Math Verification — ATR 두 방식 + % 분리 검증")
    print("Equity = $100,000  |  Risk per trade = 1% (= $1,000)")
    print("=" * 105)

    for ticker, spec in TICKERS.items():
        mult = spec["mult"]
        dec = spec["decimals"]
        candles = get_candles(ticker)
        if len(candles) < 25:
            print(f"\n{ticker}: 데이터 부족")
            continue

        entry = candles[-1]["close"]
        atr_s = atr_sma(candles, 20)
        atr_w = atr_wilder(candles, 20)
        # 2N — Turtle 구현은 SMA 사용
        n = atr_s
        two_n = 2 * n
        two_n_wilder = 2 * atr_w

        print(f"\n┌─ {ticker} ─ Entry = {entry:.{dec}f}  ─  Multiplier = ${mult:.0f}/pt ─" + "─" * 30)
        print(f"│")
        print(f"│  ATR(20) SMA    = {atr_s:.{dec + 2}f}   →  2N = {two_n:.{dec}f}   → 2N/Entry = {(two_n / entry) * 100:.3f}%")
        print(f"│  ATR(20) Wilder = {atr_w:.{dec + 2}f}   →  2N = {two_n_wilder:.{dec}f}   → 2N/Entry = {(two_n_wilder / entry) * 100:.3f}%")
        print(f"│  차이 (SMA vs Wilder): {(atr_s - atr_w):.{dec + 2}f}pt ({((atr_s - atr_w) / atr_w * 100):.2f}%)")
        print(f"│")

        # ── LONG 청산 ──
        hard_pct = 0.05
        long_hard_price = entry * (1 - hard_pct)
        long_2n_price = entry - two_n
        # Effective SL: max of two (= 더 가까운 stop = 더 작은 손실)
        long_effective = max(long_2n_price, long_hard_price)

        print(f"│  LONG Position @ Entry = {entry:.{dec}f}")
        print(f"│  ┌─ Tier ─┬── Stop Price ──┬─ Δ Price ──┬─ Δ Price % ─┬─ $/1ct ─┬─ % of $100k ─┐")
        print(f"│  │ Hard   │ {long_hard_price:>12.{dec}f}   │ {long_hard_price - entry:>+9.{dec}f} │ {((long_hard_price - entry) / entry) * 100:>+10.3f}% │ "
              f"-${(entry - long_hard_price) * mult:>8,.0f} │ {((entry - long_hard_price) * mult / 100000) * 100:>10.2f}% │")
        print(f"│  │ 2N     │ {long_2n_price:>12.{dec}f}   │ {long_2n_price - entry:>+9.{dec}f} │ {((long_2n_price - entry) / entry) * 100:>+10.3f}% │ "
              f"-${(entry - long_2n_price) * mult:>8,.0f} │ {((entry - long_2n_price) * mult / 100000) * 100:>10.2f}% │")
        which = "Hard" if long_hard_price > long_2n_price else "2N"
        print(f"│  └─ Effective SL = max(2N, Hard) = {long_effective:.{dec}f} ({which})  ────────────────────────────────┘")

        # ── SHORT 청산 ──
        short_hard_price = entry * (1 + hard_pct)
        short_2n_price = entry + two_n
        short_effective = min(short_2n_price, short_hard_price)

        enable_short = ticker not in ("CL=F", "GC=F")
        if enable_short:
            print(f"│  SHORT Position @ Entry = {entry:.{dec}f}")
            print(f"│  ┌─ Tier ─┬── Stop Price ──┬─ Δ Price ──┬─ Δ Price % ─┬─ $/1ct ─┬─ % of $100k ─┐")
            print(f"│  │ Hard   │ {short_hard_price:>12.{dec}f}   │ {short_hard_price - entry:>+9.{dec}f} │ {((short_hard_price - entry) / entry) * 100:>+10.3f}% │ "
                  f"-${(short_hard_price - entry) * mult:>8,.0f} │ {((short_hard_price - entry) * mult / 100000) * 100:>10.2f}% │")
            print(f"│  │ 2N     │ {short_2n_price:>12.{dec}f}   │ {short_2n_price - entry:>+9.{dec}f} │ {((short_2n_price - entry) / entry) * 100:>+10.3f}% │ "
                  f"-${(short_2n_price - entry) * mult:>8,.0f} │ {((short_2n_price - entry) * mult / 100000) * 100:>10.2f}% │")
            which = "Hard" if short_hard_price < short_2n_price else "2N"
            print(f"│  └─ Effective SL = min(2N, Hard) = {short_effective:.{dec}f} ({which})  ────────────────────────────────┘")
        else:
            print(f"│  SHORT — DISABLED (T override: enable_short=False)")

        print(f"└" + "─" * 100)


if __name__ == "__main__":
    main()
