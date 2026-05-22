"""
Turtle 부적합 메커니즘 추적 — 변동성과 stop hit 패턴 분석.

분석 항목:
1. ATR/가격 비율 (변동성 강도) — 4종목 비교
2. 2N stop vs hard stop 거리 — 어느 게 effective?
3. Breakout 빈도 vs Whipsaw 빈도 (breakout 후 N봉 내 stop 발동)
4. Daily candle range 분포 — hard stop -5% 발동 일 비율
5. Hard stop이 effective일 때의 손실 패턴
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from statistics import mean, median

BASE = "http://localhost:8000/api/v1"

TICKERS = {
    "ES=F": {"mult": 50.0, "name": "S&P 500"},
    "NQ=F": {"mult": 20.0, "name": "NASDAQ 100"},
    "CL=F": {"mult": 1000.0, "name": "WTI Crude"},
    "GC=F": {"mult": 100.0, "name": "Gold"},
}

PERIOD = 20
HARD_STOP_PCT = 0.05
STOP_ATR_MULT = 2.0
WHIPSAW_WINDOW = 5  # breakout 후 5봉 이내 stop 발동 = whipsaw


def get_candles(ticker: str) -> list[dict]:
    url = f"{BASE}/analyze/{ticker}?" + urllib.parse.urlencode({"period": "6mo", "interval": "1d"})
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode()).get("data", [])


def true_range(h: float, l: float, prev_close: float) -> float:
    return max(h - l, abs(h - prev_close), abs(l - prev_close))


def wilder_atr_series(candles: list[dict], period: int = 20) -> list[float]:
    """Wilder EMA ATR 시계열 반환 (각 봉 종료 후 ATR 값)."""
    n = len(candles)
    if n < period + 1:
        return [0.0] * n
    trs = [0.0]  # 첫 봉은 prev 없음 → 0
    for i in range(1, n):
        trs.append(true_range(candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]))
    # Initial SMA
    if n < period:
        return [0.0] * n
    atrs = [0.0] * period
    atrs.append(sum(trs[1:period + 1]) / period)
    # Wilder
    for i in range(period + 1, n):
        atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
    return atrs


def donchian_series(candles: list[dict], period: int = 20) -> tuple[list[float], list[float]]:
    """매 봉마다 직전 N봉의 high/low (shift(1) 적용)."""
    n = len(candles)
    highs = [0.0] * n
    lows = [0.0] * n
    for i in range(period + 1, n):
        window = candles[i - period - 1:i - 1]  # 직전 period (i 자신 제외)
        if window:
            highs[i] = max(c["high"] for c in window)
            lows[i] = min(c["low"] for c in window)
    return highs, lows


def analyze(ticker: str, spec: dict) -> None:
    mult = spec["mult"]
    name = spec["name"]
    candles = get_candles(ticker)
    if len(candles) < 40:
        print(f"\n⚠ {ticker} 데이터 부족 ({len(candles)})")
        return

    atrs = wilder_atr_series(candles, PERIOD)
    donch_highs, donch_lows = donchian_series(candles, PERIOD)
    exit_highs, exit_lows = donchian_series(candles, 10)

    print(f"\n{'═' * 95}")
    print(f"{ticker}  ({name})  Multiplier: ${mult:.0f}/pt  |  봉수: {len(candles)}")
    print('═' * 95)

    # ─ 1. ATR/가격 비율 분포 ─
    atr_pcts = []
    for i in range(PERIOD + 1, len(candles)):
        if atrs[i] > 0:
            atr_pcts.append((atrs[i] / candles[i]["close"]) * 100)

    if not atr_pcts:
        return

    print(f"\n[1] ATR/가격 변동성 분포 (ATR%):")
    print(f"    Min/Median/Max:  {min(atr_pcts):.2f}% / {median(atr_pcts):.2f}% / {max(atr_pcts):.2f}%")
    print(f"    Mean:            {mean(atr_pcts):.2f}%")

    # ─ 2. 2N vs Hard stop 거리 비교 — 어느 게 effective ─
    two_n_smaller = 0  # 2N이 더 가까움 = Turtle 본 룰 적용 (정상)
    hard_smaller = 0   # Hard가 더 가까움 = catastrophic 안전망 동원 (의도 외 stop)
    for i in range(PERIOD + 1, len(candles)):
        if atrs[i] <= 0:
            continue
        two_n_pct = (STOP_ATR_MULT * atrs[i] / candles[i]["close"]) * 100
        hard_pct = HARD_STOP_PCT * 100
        if two_n_pct <= hard_pct:
            two_n_smaller += 1
        else:
            hard_smaller += 1
    total_bars = two_n_smaller + hard_smaller
    pct_hard_eff = (hard_smaller / total_bars * 100) if total_bars else 0
    print(f"\n[2] 2N stop vs Hard stop 거리 (-5%):")
    print(f"    2N이 더 가까운 봉 (정상 Turtle):     {two_n_smaller}/{total_bars} ({100 - pct_hard_eff:.1f}%)")
    print(f"    Hard가 더 가까운 봉 (catastrophic):  {hard_smaller}/{total_bars} ({pct_hard_eff:.1f}%)")
    if pct_hard_eff > 30:
        print(f"    ⚠ Hard stop이 자주 effective → 변동성이 2N stop 거리에 비해 큼")
    elif pct_hard_eff > 5:
        print(f"    △ Hard stop 일부 활성화 — 고변동성 시점에 갱신 가능성")
    else:
        print(f"    ✓ 2N stop이 거의 항상 effective (정통 Turtle 동작)")

    # ─ 3. Donchian Breakout & Whipsaw 분석 ─
    breakouts = []  # (idx, direction, entry_price, atr_at_entry)
    for i in range(PERIOD + 1, len(candles)):
        if donch_highs[i] == 0 or atrs[i] == 0:
            continue
        c = candles[i]
        if c["close"] > donch_highs[i]:
            breakouts.append({"idx": i, "dir": "LONG", "entry": c["close"], "atr": atrs[i]})
        elif c["close"] < donch_lows[i]:
            breakouts.append({"idx": i, "dir": "SHORT", "entry": c["close"], "atr": atrs[i]})

    whipsaws = 0
    avg_holding = []
    exits_by_type = {"2N_STOP": 0, "HARD_STOP": 0, "10D_REVERSE": 0, "STILL_OPEN": 0}
    for bo in breakouts:
        entry_idx = bo["idx"]
        entry = bo["entry"]
        atr_e = bo["atr"]
        is_long = bo["dir"] == "LONG"
        # 2N stop과 hard stop 두 후보 (더 가까운 거리 적용 = max for long, min for short)
        if is_long:
            actual_stop = max(entry - STOP_ATR_MULT * atr_e, entry * (1 - HARD_STOP_PCT))
        else:
            actual_stop = min(entry + STOP_ATR_MULT * atr_e, entry * (1 + HARD_STOP_PCT))
        # 진입 후 청산 추적
        exit_idx = None
        exit_reason = "STILL_OPEN"
        for j in range(entry_idx + 1, len(candles)):
            c = candles[j]
            # 우선순위 1: hard stop -5% (hit 가격 기준 — 봉 내 low/high로 체크)
            hard_stop_price = entry * (1 - HARD_STOP_PCT) if is_long else entry * (1 + HARD_STOP_PCT)
            if is_long and c["low"] <= hard_stop_price:
                exit_idx = j
                # actual_stop이 hard stop과 같은지 (효력 발동)
                if actual_stop >= entry - STOP_ATR_MULT * atr_e:
                    exit_reason = "HARD_STOP"
                else:
                    exit_reason = "2N_STOP"
                break
            if not is_long and c["high"] >= hard_stop_price:
                exit_idx = j
                if actual_stop <= entry + STOP_ATR_MULT * atr_e:
                    exit_reason = "HARD_STOP"
                else:
                    exit_reason = "2N_STOP"
                break
            # 우선순위 2: 2N stop
            two_n_stop = entry - STOP_ATR_MULT * atr_e if is_long else entry + STOP_ATR_MULT * atr_e
            if is_long and c["low"] <= two_n_stop:
                exit_idx = j; exit_reason = "2N_STOP"; break
            if not is_long and c["high"] >= two_n_stop:
                exit_idx = j; exit_reason = "2N_STOP"; break
            # 우선순위 3: 10일 reverse (exit_lows / exit_highs)
            if exit_lows[j] > 0 and is_long and c["close"] < exit_lows[j]:
                exit_idx = j; exit_reason = "10D_REVERSE"; break
            if exit_highs[j] > 0 and not is_long and c["close"] > exit_highs[j]:
                exit_idx = j; exit_reason = "10D_REVERSE"; break
        # holding period
        if exit_idx:
            holding = exit_idx - entry_idx
            avg_holding.append(holding)
            if holding <= WHIPSAW_WINDOW and exit_reason in ("2N_STOP", "HARD_STOP"):
                whipsaws += 1
        exits_by_type[exit_reason] += 1

    n_bo = len(breakouts)
    print(f"\n[3] Donchian Breakout 통계 ({PERIOD}일 high/low):")
    print(f"    총 breakout 수:            {n_bo}")
    if n_bo > 0:
        print(f"    평균 보유 봉수:            {mean(avg_holding):.1f}일" if avg_holding else "    평균 보유 봉수: —")
        print(f"    Whipsaw (≤{WHIPSAW_WINDOW}일 stop hit):  {whipsaws}/{n_bo} ({whipsaws / n_bo * 100:.1f}%)")
        print(f"    청산 사유 분포:")
        for r, cnt in exits_by_type.items():
            pct = cnt / n_bo * 100 if n_bo else 0
            print(f"      {r:<14}  {cnt:>3}  ({pct:>5.1f}%)")

    # ─ 4. 손실 규모 ─
    print(f"\n[4] $ 손실 규모 (1 contract 기준, equity=$100k):")
    current = candles[-1]["close"]
    current_atr = atrs[-1] if atrs[-1] > 0 else mean([a for a in atrs if a > 0])
    hard_dist = current * HARD_STOP_PCT
    twoN_dist = STOP_ATR_MULT * current_atr
    actual_dist = min(hard_dist, twoN_dist)
    actual_label = "HARD" if hard_dist < twoN_dist else "2N"
    print(f"    Current price:  {current:.2f}")
    print(f"    Current ATR:    {current_atr:.4f}")
    print(f"    2N distance:    {twoN_dist:.2f}pt  ({twoN_dist / current * 100:.2f}%)  → $/ct = ${twoN_dist * mult:,.0f}")
    print(f"    Hard distance:  {hard_dist:.2f}pt  ({HARD_STOP_PCT * 100:.1f}%)        → $/ct = ${hard_dist * mult:,.0f}")
    print(f"    Effective ({actual_label}):  {actual_dist:.2f}pt  → $/ct = ${actual_dist * mult:,.0f}  ({actual_dist * mult / 100000 * 100:.2f}% of $100k equity)")


def main():
    print("=" * 95)
    print("Turtle 부적합 메커니즘 추적 — 4종목 변동성 + Whipsaw 분석 (6mo daily)")
    print("=" * 95)

    for tk, sp in TICKERS.items():
        analyze(tk, sp)

    # 비교 요약
    print(f"\n{'═' * 95}")
    print("종합 요약:")
    print("  - ATR% 큰 자산 (CL ~6%) → 2N(12%) > hard(5%) → hard stop이 effective → Turtle 본 의도 깨짐")
    print("  - Whipsaw 비율 높음 (breakout 후 5일 내 stop hit) → 추세 진행 시간 없이 cut")
    print("  - Multiplier 큰 자산 (CL $1000, GC $100) → 절대 $ 손실 크다 → 자본 잠식 빠름")
    print('═' * 95)


if __name__ == "__main__":
    main()
