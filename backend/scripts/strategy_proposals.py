"""
4종목 진입 전략 제안 — 실시간 데이터 기반.

각 종목의 Mag MA, POC, VAH/VAL, VWATR S/R 위치 분석 → 진입 시나리오 + 구체 가격.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "http://localhost:8000/api/v1"

TICKERS = {
    "ES=F":  {"name": "S&P 500",    "multiplier": 50.0,   "decimals": 2,
              "micro_ticker": "MES=F", "micro_mult": 5.0},
    "NQ=F":  {"name": "NASDAQ 100", "multiplier": 20.0,   "decimals": 2,
              "micro_ticker": "MNQ=F", "micro_mult": 2.0},
    "CL=F":  {"name": "WTI Crude",  "multiplier": 1000.0, "decimals": 2,
              "micro_ticker": "MCL=F", "micro_mult": 100.0},
    "GC=F":  {"name": "Gold",       "multiplier": 100.0,  "decimals": 1,
              "micro_ticker": "MGC=F", "micro_mult": 10.0},
}


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"err": str(e)}


def fetch_full(ticker: str) -> dict:
    """ESF analyze + volume-profile + regime 통합 조회."""
    analyze = _get(f"/esf/analyze/{ticker}", {"interval": "15m", "period": "5d"})
    vp = _get(f"/esf/volume-profile/{ticker}", {"period": "5d", "interval": "15m"})
    regime = _get(f"/esf/regime/{ticker}")
    return {"analyze": analyze, "vp": vp, "regime": regime}


def assess_location(current: float, poc: float, vah: float, val: float, lvn_levels: list) -> tuple[str, str]:
    """가격 위치 → AMT location 라벨 + 매매 시나리오 hint."""
    # LVN 근접 (±0.3%)
    for lvn in lvn_levels[:5]:
        if abs(current - lvn) / current < 0.003:
            return "AT_LVN", "가격이 LVN — 빠른 통과 예상 (저항 약함)"
    # POC 근접 (±0.2%)
    if abs(current - poc) / current < 0.002:
        return "AT_POC", "균형점 — mean-reversion entry 후보"
    # Value Area
    if val <= current <= vah:
        return "IN_VALUE", "Value Area 안 — 횡보 가능성, 양쪽 brake 대기"
    if current > vah:
        return "ABOVE_VAH", "Imbalance Bullish — 추세 추종 LONG 또는 VAH 회귀 SHORT"
    if current < val:
        return "BELOW_VAL", "Imbalance Bearish — 추세 추종 SHORT 또는 VAL 회귀 LONG"
    return "UNKNOWN", "—"


def propose_strategy(ticker: str, data: dict) -> None:
    spec = TICKERS[ticker]
    name = spec["name"]
    mult = spec["multiplier"]
    micro_mult = spec["micro_mult"]
    micro_ticker = spec["micro_ticker"]
    dec = spec["decimals"]

    an = data["analyze"]
    vp = data["vp"]
    regime = data["regime"]

    if "err" in an or "err" in vp:
        print(f"\n⚠ {ticker}: 데이터 로드 실패")
        return

    current = an.get("entry_price", 0) or 0
    direction = an.get("direction", "NEUTRAL")
    score = an.get("total_score", 0)
    grade = an.get("grade", "?")
    mag = an.get("magnetic_ma", {}).get("best", {}).get("current_value", 0) or 0
    ind = an.get("indicators", {})
    atr = ind.get("atr", 0) or 0
    bb_sq = ind.get("bb_squeeze_ratio", 1.0) or 1.0

    poc = vp.get("poc", 0) or 0
    vah = vp.get("vah", 0) or 0
    val = vp.get("val", 0) or 0
    lvn_levels = vp.get("lvn_levels", []) or []

    rg_label = regime.get("regime", "?")
    trend_score = regime.get("trend_score", 0)

    location, location_hint = assess_location(current, poc, vah, val, lvn_levels)

    # 가격 vs Mag MA, POC
    mag_dist = current - mag
    poc_dist = current - poc

    print(f"\n{'═' * 95}")
    print(f"  {ticker}  ({name})  —  Multiplier: ${mult:.0f}/pt (Micro: ${micro_mult:.0f}/pt)")
    print('═' * 95)

    # ── 시장 상태 ──
    print(f"\n  📊 시장 상태:")
    print(f"    현재가:           {current:.{dec}f}")
    print(f"    Backend 방향:     {direction}  (Grade {grade}, Score {score:.1f}/100)")
    print(f"    Regime:           {rg_label}  (trend_score {trend_score:+d})")
    print(f"    AMT Location:     {location} — {location_hint}")
    print(f"    ATR(20):          {atr:.{dec}f}  ({(atr / current * 100):.2f}% volatility)")
    bb_state = "SQUEEZE" if bb_sq < 0.75 else ("EXPANSION" if bb_sq > 1.5 else "NORMAL")
    print(f"    BB Squeeze:       {bb_sq:.2f}  ({bb_state})")

    # ── 자석/균형 가격 ──
    print(f"\n  🧲 자석/균형:")
    if mag > 0:
        print(f"    Mag MA:           {mag:.{dec}f}  (Δ from price = {mag_dist:+.{dec}f}pt)")
    if poc > 0:
        print(f"    POC:              {poc:.{dec}f}  (Δ from price = {poc_dist:+.{dec}f}pt)")
    if vah > 0 and val > 0:
        print(f"    VAH / VAL:        {vah:.{dec}f} / {val:.{dec}f}  (width {vah - val:.{dec}f})")
    print(f"    LVN (top 3):      {[round(l, dec) for l in lvn_levels[:3]]}")

    # ── 진입 전략 제안 ──
    print(f"\n  🎯 진입 시나리오:")

    # 핵심 룰: location + direction + grade 종합
    grade_ok = grade in ("A", "B")  # A/B 만 권장
    scenarios = []

    if location == "AT_LVN":
        # LVN — 가격이 빠르게 통과 — 추세 방향 진입
        if direction == "LONG":
            entry = current
            stop = max(current - 1.0 * atr, mag if mag > 0 and mag < current else current - 1.0 * atr)
            tp = current + 2.0 * atr
            scenarios.append(("🟢 LONG", entry, stop, tp, "LVN 통과 추세 추종 LONG"))
        elif direction == "SHORT":
            entry = current
            stop = min(current + 1.0 * atr, mag if mag > 0 and mag > current else current + 1.0 * atr)
            tp = current - 2.0 * atr
            scenarios.append(("🔴 SHORT", entry, stop, tp, "LVN 통과 추세 추종 SHORT"))

    elif location == "AT_POC":
        # POC — mean-reversion 후보 (이미 균형점) 또는 fade
        # 양방향 시나리오 제시
        if mag > 0 and mag > current:  # Mag MA가 위에 있음 → reversion 위로
            entry = current
            stop = current - 1.0 * atr
            tp = mag
            scenarios.append(("🟢 LONG (Reversion)", entry, stop, tp, "POC → Mag MA 회귀"))
        elif mag > 0 and mag < current:
            entry = current
            stop = current + 1.0 * atr
            tp = mag
            scenarios.append(("🔴 SHORT (Reversion)", entry, stop, tp, "POC → Mag MA 회귀"))

    elif location == "ABOVE_VAH":
        # Imbalance Bullish — 두 방향 가능
        # (A) 추세 추종 LONG
        entry_a = current
        stop_a = vah  # VAH 가 trailing 지지
        tp_a = current + 3.0 * atr
        scenarios.append(("🟢 LONG (Trend)", entry_a, stop_a, tp_a, "VAH 위로 이탈 → 추세 추종"))
        # (B) Fade SHORT — VAH 거부 시
        if mag > 0:
            entry_b = current
            stop_b = current + 1.0 * atr
            tp_b = vah  # VAH로 회귀
            scenarios.append(("🔴 SHORT (Fade)", entry_b, stop_b, tp_b, "VAH 거부 → POC 회귀 (보조)"))

    elif location == "BELOW_VAL":
        # Imbalance Bearish
        entry_a = current
        stop_a = val
        tp_a = current - 3.0 * atr
        scenarios.append(("🔴 SHORT (Trend)", entry_a, stop_a, tp_a, "VAL 아래 이탈 → 추세 추종"))
        if mag > 0:
            entry_b = current
            stop_b = current - 1.0 * atr
            tp_b = val
            scenarios.append(("🟢 LONG (Fade)", entry_b, stop_b, tp_b, "VAL 거부 → POC 회귀 (보조)"))

    elif location == "IN_VALUE":
        # 횡보 — VAH/VAL 양쪽 brake 대기
        scenarios.append(("⏸ WAIT", current, val, vah,
                         f"Value Area 내부 — VAH({vah:.{dec}f}) brake 시 LONG / VAL({val:.{dec}f}) brake 시 SHORT"))

    if not scenarios:
        print(f"    ⏸ WAIT — 명확한 신호 없음 (location={location}, direction={direction})")
    else:
        for label, entry, stop, tp, desc in scenarios:
            risk_pt = abs(entry - stop)
            reward_pt = abs(tp - entry)
            rr = reward_pt / risk_pt if risk_pt > 0 else 0
            risk_d = risk_pt * mult
            reward_d = reward_pt * mult
            risk_d_micro = risk_pt * micro_mult
            print(f"\n    {label}: {desc}")
            print(f"      Entry:  {entry:.{dec}f}")
            print(f"      Stop:   {stop:.{dec}f}  (risk {risk_pt:.{dec}f}pt)")
            print(f"      Target: {tp:.{dec}f}  (reward {reward_pt:.{dec}f}pt)  →  R:R = {rr:.2f}:1")
            print(f"      Full size 1ct risk:  ${risk_d:,.0f}  / reward: ${reward_d:,.0f}")
            print(f"      Micro 1ct ({micro_ticker}): risk ${risk_d_micro:,.0f}  ({risk_d_micro / 100000 * 100:.2f}% of $100k)")

    # ── 신뢰도 / 권장 ──
    print(f"\n  📝 권장:")
    if grade_ok and direction != "NEUTRAL":
        print(f"    ✅ Backend Grade {grade} + direction {direction} 명확 → 진입 신중하게 OK")
    elif score >= 30:
        print(f"    ⚠ Score {score:.0f} (Grade {grade}) — 기준 미달, **관망 권장**")
    else:
        print(f"    ❌ Score 낮음 ({score:.0f}) — 진입 보류, 다음 setup 대기")

    # Equity 기준 ($100k) 권장
    risk_full = 2.0 * atr * mult
    risk_micro = 2.0 * atr * micro_mult
    if risk_full / 100000 > 0.02:
        print(f"    📐 $100k equity 기준: **Micro 사용 권장** (full size 1ct 2N risk = {risk_full / 100000 * 100:.1f}% > 2%)")
    else:
        print(f"    📐 $100k equity 기준: Full size OK (1ct 2N risk = {risk_full / 100000 * 100:.1f}%)")


def main():
    print("=" * 95)
    print("4종목 진입 전략 제안 — 실시간 데이터 기반 (15m intraday)")
    print("=" * 95)
    print("\n  데이터 출처: backend ESF analyze + Volume Profile + Trend Regime")
    print("  Equity 가정: $100,000  |  Risk per trade: 1-2% (Micro 권장)")

    for ticker in TICKERS:
        try:
            data = fetch_full(ticker)
            propose_strategy(ticker, data)
        except Exception as e:
            print(f"\n⚠ {ticker}: {e}")

    print(f"\n{'═' * 95}")
    print("⚠ 주의:")
    print("  - 위 시나리오는 현 시점 데이터의 '만약 진입한다면' 가설")
    print("  - 실제 진입은 backend Grade B+ AND direction 일치 (NEUTRAL 아님) 시점에만")
    print("  - 모든 stop은 ATR×1.0 (스캘프) 또는 ATR×2.0 (Turtle스윙) 기준")
    print(f"{'═' * 95}")


if __name__ == "__main__":
    main()
