"""
4종목 Turtle 청산 조건의 실제 가격 + $ 손익 추정.

각 ticker:
- 현재가 (=가정 Entry)
- ATR(20) → N
- 20일 high/low (Donchian entry levels)
- 10일 high/low (Donchian exit levels)
- 3-tier 청산 가격 + 1 contract 기준 $ 손익

LONG 청산:
  1. Hard stop: Entry × 0.95
  2. 2N stop: Entry - 2 × ATR
  3. 10-day reverse: 10일 Donchian Low

SHORT 청산 (대칭):
  1. Hard stop: Entry × 1.05
  2. 2N stop: Entry + 2 × ATR
  3. 10-day reverse: 10일 Donchian High
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

BASE = "http://localhost:8000/api/v1"

# Contract specs (mini, $/pt)
TICKERS = {
    "ES=F": {"name": "S&P 500", "multiplier": 50.0, "decimals": 2},
    "NQ=F": {"name": "NASDAQ 100", "multiplier": 20.0, "decimals": 2},
    "CL=F": {"name": "WTI Crude", "multiplier": 1000.0, "decimals": 2},
    "GC=F": {"name": "Gold", "multiplier": 100.0, "decimals": 1},
}


def _get(path: str, params: dict | None = None, timeout: int = 30) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"err": str(e)}


def get_daily_data(ticker: str, period_days: int = 30) -> dict | None:
    """Daily candle 데이터 조회 — period_days 일치."""
    # ESF candles endpoint는 intraday만 지원 — futures/analyze + analyze data 사용
    # /api/v1/analyze/{ticker} (NOT esf/) — daily candles
    period = "3mo" if period_days <= 90 else "6mo"
    d = _get(f"/analyze/{ticker}", {"period": period, "interval": "1d"})
    if "err" in d:
        return None
    return d


def compute_donchian(candles: list[dict], period: int) -> tuple[float, float]:
    """N일 high/low 계산 (현재 봉 제외 = shift(1) 시뮬레이션)."""
    if len(candles) < period + 1:
        return 0.0, 0.0
    # 마지막 candle 제외, 그 이전 period개 봉으로 계산 (shift(1))
    recent = candles[-(period + 1):-1]
    if not recent:
        return 0.0, 0.0
    high = max(c["high"] for c in recent)
    low = min(c["low"] for c in recent)
    return high, low


def compute_atr(candles: list[dict], period: int = 20) -> float:
    """ATR(20) 계산 — True Range 단순 평균."""
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    # 최근 period TR 평균
    recent_trs = trs[-period:]
    return sum(recent_trs) / len(recent_trs)


def fmt_usd(v: float) -> str:
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.0f}"


def estimate_ticker(ticker: str) -> None:
    spec = TICKERS[ticker]
    mult = spec["multiplier"]
    decimals = spec["decimals"]

    print(f"\n{'═' * 90}")
    print(f"{ticker}  ({spec['name']})  — Multiplier: ${mult:.0f}/pt")
    print('═' * 90)

    # Get daily data
    data = get_daily_data(ticker)
    if data is None or "data" not in data:
        print(f"  ⚠ 데이터 로드 실패")
        return

    candles = data.get("data", [])
    if len(candles) < 25:
        print(f"  ⚠ 캔들 부족 ({len(candles)})")
        return

    # Compute indicators
    current_price = candles[-1]["close"]
    atr_20 = compute_atr(candles, period=20)
    donch_20_high, donch_20_low = compute_donchian(candles, period=20)
    donch_10_high, donch_10_low = compute_donchian(candles, period=10)
    n = atr_20  # Turtle "N"

    print(f"  📊 Current Price (entry 가정):  {current_price:.{decimals}f}")
    print(f"  📊 ATR(20) = N:                 {n:.{decimals}f}")
    print(f"  📊 20일 Donchian High/Low:      {donch_20_high:.{decimals}f} / {donch_20_low:.{decimals}f}")
    print(f"  📊 10일 Donchian High/Low:      {donch_10_high:.{decimals}f} / {donch_10_low:.{decimals}f}")
    print(f"  📊 2N:                          {2 * n:.{decimals}f}")
    print(f"  📊 -5% level:                   -{current_price * 0.05:.{decimals}f}")

    entry = current_price

    # ─── LONG Exit Levels ───
    print(f"\n  ┌─────────────────────────────────────────────────────────┐")
    print(f"  │ LONG Position @ Entry = {entry:.{decimals}f}  (1 contract)         │")
    print(f"  └─────────────────────────────────────────────────────────┘")

    # 1. Hard stop -5%
    long_hard_stop = entry * 0.95
    long_hard_loss = (long_hard_stop - entry) * mult
    print(f"  1️⃣  HARD_STOP_LOSS  | Price ≤ {long_hard_stop:.{decimals}f}  "
          f"({((long_hard_stop - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(long_hard_loss)}")

    # 2. 2N ATR stop
    long_2n_stop = entry - 2 * n
    long_2n_loss = (long_2n_stop - entry) * mult
    print(f"  2️⃣  TURTLE_2N_STOP  | Price ≤ {long_2n_stop:.{decimals}f}  "
          f"({((long_2n_stop - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(long_2n_loss)}")

    # 3. 10-day reverse
    long_10d_pnl = (donch_10_low - entry) * mult
    print(f"  3️⃣  10D_REVERSE     | Price < {donch_10_low:.{decimals}f}  "
          f"({((donch_10_low - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(long_10d_pnl)}")

    # Actual SL (used at entry) — max(2N, hard) = 더 가까운 = 더 작은 손실
    actual_sl_long = max(long_2n_stop, long_hard_stop)
    actual_sl_loss = (actual_sl_long - entry) * mult
    print(f"  ▶ Effective SL at Entry: {actual_sl_long:.{decimals}f}  "
          f"=>  Initial Risk = {fmt_usd(actual_sl_loss)}")

    # ─── SHORT Exit Levels ───
    enable_short = ticker not in ("CL=F", "MCL=F", "GC=F", "MGC=F")
    print(f"\n  ┌─────────────────────────────────────────────────────────┐")
    if not enable_short:
        print(f"  │ SHORT Position @ Entry = {entry:.{decimals}f}  ⚠ DISABLED (T override) │")
    else:
        print(f"  │ SHORT Position @ Entry = {entry:.{decimals}f}  (1 contract)        │")
    print(f"  └─────────────────────────────────────────────────────────┘")

    # 1. Hard stop +5%
    short_hard_stop = entry * 1.05
    short_hard_loss = (entry - short_hard_stop) * mult
    print(f"  1️⃣  HARD_STOP_LOSS  | Price ≥ {short_hard_stop:.{decimals}f}  "
          f"({((short_hard_stop - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(short_hard_loss)}")

    # 2. 2N ATR stop
    short_2n_stop = entry + 2 * n
    short_2n_loss = (entry - short_2n_stop) * mult
    print(f"  2️⃣  TURTLE_2N_STOP  | Price ≥ {short_2n_stop:.{decimals}f}  "
          f"({((short_2n_stop - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(short_2n_loss)}")

    # 3. 10-day reverse
    short_10d_pnl = (entry - donch_10_high) * mult
    print(f"  3️⃣  10D_REVERSE     | Price > {donch_10_high:.{decimals}f}  "
          f"({((donch_10_high - entry) / entry) * 100:+.1f}%) "
          f"=>  PnL = {fmt_usd(short_10d_pnl)}")

    actual_sl_short = min(short_2n_stop, short_hard_stop)
    actual_sl_loss = (entry - actual_sl_short) * mult
    print(f"  ▶ Effective SL at Entry: {actual_sl_short:.{decimals}f}  "
          f"=>  Initial Risk = {fmt_usd(actual_sl_loss)}")

    # ─── Position Sizing ───
    print(f"\n  💰 Position Sizing (equity = $100,000, 1% risk):")
    stop_dist_2n = 2 * n
    risk_per_contract = stop_dist_2n * mult
    contracts = max(1, int(100000 * 0.01 / risk_per_contract))
    print(f"     Risk amount: $1,000 / contract cost: {fmt_usd(risk_per_contract)}")
    print(f"     Recommended contracts: {contracts}")
    print(f"     Total risk if 2N stop hit: {fmt_usd(risk_per_contract * contracts)}")


def main():
    print("=" * 90)
    print("Turtle 청산 조건 — 4종목 실제 가격/손익 추정 (1 contract 기준)")
    print("Equity 가정: $100,000, Risk per trade: 1%")
    print("=" * 90)

    for ticker in TICKERS:
        estimate_ticker(ticker)

    print(f"\n{'═' * 90}")
    print("핵심 관찰:")
    print("  - 2N stop이 hard stop(-5%)보다 가까우면 보수적 → 더 적은 risk")
    print("  - 2N stop이 hard stop보다 멀면 → -5% catastrophic backup 적용")
    print("  - 10-day reverse는 dynamic — let winners run으로 시간이 지나면 변화")
    print('═' * 90)


if __name__ == "__main__":
    main()
