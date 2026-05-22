"""
스캘핑(ESF Intraday) + 스윙(SP500 Futures Daily) 신호 발생 점검.

각 4종목 × 두 전략의 현 시점 신호 상태를 매트릭스로 출력.
- 스캘핑: GET /api/v1/esf/analyze/{ticker} → direction / total_score / grade / signal_active
- 스윙:   GET /api/v1/futures/signal/{ticker} → direction / signal_strength / position size
또는 최근 60일 daily backtest에서 trade 발생 개수.

Usage:
    python3 backend/scripts/check_signal_emission.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000/api/v1"
TICKERS = ["ES=F", "NQ=F", "CL=F", "GC=F"]
MICRO_SET = {"MES=F", "MNQ=F", "MCL=F", "MGC=F"}


def _get(path: str, params: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"detail": body[:200]}
    except Exception as e:
        return 0, {"detail": str(e)}


def _post(path: str, params: dict | None = None, timeout: int = 900) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"detail": body[:200]}
    except Exception as e:
        return 0, {"detail": str(e)}


def check_scalping(ticker: str) -> dict:
    """ESF 스캘핑 — 현 시점 analyze + signal."""
    code, an = _get(f"/esf/analyze/{ticker}", {"interval": "15m", "period": "5d"})
    if code != 200:
        return {"ticker": ticker, "error": f"analyze {code}: {an.get('detail', '')[:50]}"}
    return {
        "ticker": ticker,
        "direction": an.get("direction", "?"),
        "score": an.get("total_score", 0),
        "grade": an.get("grade", "?"),
        "signal_active": an.get("signal_active", False),
        "regime": (an.get("regime") or {}).get("regime", "?"),
    }


def check_swing_realtime(ticker: str) -> dict:
    """SP500 Futures Daily — 현 시점 signal."""
    code, sig = _get(f"/futures/signal/{ticker}", {"equity": 100000})
    if code != 200:
        return {"ticker": ticker, "error": f"signal {code}: {sig.get('detail', '')[:50]}"}
    s = sig.get("signal")
    if s is None:
        return {"ticker": ticker, "direction": "—", "msg": sig.get("message", "no signal")}
    return {
        "ticker": ticker,
        "direction": s.get("direction", "?"),
        "strength": s.get("signal_strength", 0),
        "entry": s.get("entry_price", 0),
        "rr": s.get("risk_reward_ratio", 0),
        "contracts": s.get("position_size_contracts", 0),
    }


def check_swing_backtest(ticker: str) -> dict:
    """SP500 Futures Daily — 최근 6개월 backtest trade 수."""
    code, res = _post("/futures/backtest", {
        "ticker": ticker, "start_date": "20251101", "end_date": "20260520",
        "equity": 100000, "is_micro": "false",
    })
    if code != 200:
        return {"ticker": ticker, "error": f"backtest {code}: {res.get('detail', '')[:50]}"}
    m = res.get("metrics", {})
    ds = m.get("direction_stats", {})
    return {
        "ticker": ticker,
        "trades": m.get("total_trades", 0),
        "long_n": int(ds.get("long_trade_count", 0)),
        "short_n": int(ds.get("short_trade_count", 0)),
        "long_called": int(ds.get("long_called", 0)),
        "short_called": int(ds.get("short_called", 0)),
        "return_pct": m.get("total_return_pct", 0),
    }


def main():
    print("=" * 100)
    print("신호 발생 점검 — 4종목 × 스캘핑(ESF Intraday) + 스윙(SP500 Daily)")
    print("=" * 100)

    # ── 1. 스캘핑 (ESF Intraday) — 현 시점 ──
    print("\n[1] 스캘핑 (ESF Intraday 15m) — 현 시점 analyze:\n")
    print(f"{'Ticker':<8} {'Dir':<8} {'Score':<8} {'Grade':<8} {'Active':<8} {'Regime':<10}")
    print("-" * 60)
    scalp_results = []
    for t in TICKERS:
        r = check_scalping(t)
        scalp_results.append(r)
        if "error" in r:
            print(f"{r['ticker']:<8} ERROR: {r['error']}")
        else:
            print(f"{r['ticker']:<8} {r['direction']:<8} {r['score']:<8.1f} {r['grade']:<8} "
                  f"{str(r['signal_active']):<8} {r['regime']:<10}")

    # 통계
    active_n = sum(1 for r in scalp_results if r.get("signal_active") is True)
    direction_dist = {d: sum(1 for r in scalp_results if r.get("direction") == d)
                     for d in ("LONG", "SHORT", "NEUTRAL")}
    grade_dist = {g: sum(1 for r in scalp_results if r.get("grade") == g)
                 for g in ("A", "B", "C", "D", "NO_TRADE")}
    print(f"\nScalping 통계: signal_active={active_n}/4")
    print(f"  방향: LONG={direction_dist['LONG']} SHORT={direction_dist['SHORT']} NEUTRAL={direction_dist['NEUTRAL']}")
    print(f"  Grade: A={grade_dist['A']} B={grade_dist['B']} C={grade_dist['C']} D={grade_dist['D']} NO_TRADE={grade_dist['NO_TRADE']}")

    # ── 2. 스윙 (SP500 Daily) — 현 시점 signal ──
    print("\n[2] 스윙 (SP500 Futures Daily) — 현 시점 signal:\n")
    print(f"{'Ticker':<8} {'Dir':<8} {'Strength':<10} {'Entry':<10} {'R:R':<6} {'Ct':<4} {'Msg':<20}")
    print("-" * 80)
    swing_now = []
    for t in TICKERS:
        r = check_swing_realtime(t)
        swing_now.append(r)
        if "error" in r:
            print(f"{r['ticker']:<8} ERROR: {r['error']}")
        elif r.get("direction") == "—":
            print(f"{r['ticker']:<8} {'—':<8} {'—':<10} {'—':<10} {'—':<6} {'—':<4} {r.get('msg', ''):<20}")
        else:
            print(f"{r['ticker']:<8} {r['direction']:<8} {r['strength']:<10.1f} {r['entry']:<10.2f} "
                  f"{r['rr']:<6.2f} {r['contracts']:<4}")

    swing_active = sum(1 for r in swing_now if r.get("direction") not in ("—", "?", None) and "error" not in r)
    print(f"\nSwing 실시간 활성 신호: {swing_active}/4")

    # ── 3. 스윙 (SP500 Daily) — 최근 6개월 backtest ──
    print("\n[3] 스윙 (SP500 Futures Daily) — 최근 6개월 backtest trade 통계:\n")
    print(f"{'Ticker':<8} {'Trades':<8} {'LONG':<6} {'SHORT':<7} {'L_called':<10} {'S_called':<10} {'Return%':<10}")
    print("-" * 75)
    swing_bt = []
    for t in TICKERS:
        r = check_swing_backtest(t)
        swing_bt.append(r)
        if "error" in r:
            print(f"{r['ticker']:<8} ERROR: {r['error']}")
        else:
            print(f"{r['ticker']:<8} {r['trades']:<8} {r['long_n']:<6} {r['short_n']:<7} "
                  f"{r['long_called']:<10} {r['short_called']:<10} {r['return_pct']:<10.2f}")

    total_trades = sum(r.get("trades", 0) for r in swing_bt if "error" not in r)
    total_long_called = sum(r.get("long_called", 0) for r in swing_bt if "error" not in r)
    total_short_called = sum(r.get("short_called", 0) for r in swing_bt if "error" not in r)
    print(f"\nSwing 6mo backtest 총 trade: {total_trades}, LONG called={total_long_called}, SHORT called={total_short_called}")

    # ── 결론 ──
    print("\n" + "=" * 100)
    print("결론:")
    print(f"  - 스캘핑 활성 신호: {active_n}/4 ticker")
    print(f"  - 스윙 실시간 활성 신호: {swing_active}/4 ticker")
    print(f"  - 스윙 6개월 backtest trade 평균: {total_trades / max(len(TICKERS), 1):.1f} trades/ticker")
    if active_n == 0 and swing_active == 0:
        print("  ⚠ 양쪽 모두 실시간 신호 없음 — 정상 (낮은 빈도 시그널, 백테스트 통계로 검증 필요)")
    elif total_trades < 10:
        print("  ⚠ 백테스트 trade 수 부족 — 임계값 너무 보수적 가능")


if __name__ == "__main__":
    main()
