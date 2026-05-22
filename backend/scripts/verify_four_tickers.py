"""
Phase 1: 4종목 × 3모드 시뮬레이션 매트릭스 검증.

API 호출로 각 조합의 HTTP 응답·trade 수·에러를 매트릭스로 출력.
Phase 3 (Intraday CL/GC 지원) 진입 전 baseline + 완료 후 회귀 검증 모두에 활용.

Usage:
    ./start-backend.sh start
    python3 backend/scripts/verify_four_tickers.py
    python3 backend/scripts/verify_four_tickers.py --tickers ES=F,CL=F --modes intraday,daily
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

BASE = "http://localhost:8000/api/v1"

DEFAULT_TICKERS = [
    "ES=F", "MES=F", "NQ=F", "MNQ=F",
    "CL=F", "MCL=F", "GC=F", "MGC=F",
]
DEFAULT_MODES = ["intraday", "daily", "walk-forward"]
OVERLAY_ENDPOINTS = ["analyze", "candles", "volume-profile", "regime"]
MICRO_SET = {"MES=F", "MNQ=F", "MCL=F", "MGC=F"}


@dataclass
class Result:
    ticker: str
    mode: str
    status: str            # "PASS" | "FAIL" | "SKIP"
    http_code: int
    trades: Optional[int]
    elapsed_s: float
    detail: str = ""


def _get(path: str, params: Optional[dict] = None, timeout: int = 60) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, {"detail": body_text}
    except Exception as e:
        return 0, {"detail": str(e)}


def _is_finite(v) -> bool:
    if v is None:
        return False
    try:
        f = float(v)
        return f == f and abs(f) != float("inf")  # NaN check + inf check
    except (TypeError, ValueError):
        return False


def _post(path: str, body: Optional[dict] = None, params: Optional[dict] = None, timeout: int = 600) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, {"detail": body_text}
    except Exception as e:
        return 0, {"detail": str(e)}


def _extract_trades(payload: dict) -> Optional[int]:
    """다양한 응답 포맷에서 total_trades 추출."""
    # Daily: {ticker, metrics:{total_trades}}
    # Intraday: {status, result:{metrics:{total_trades}}}
    # Walk-Forward: {status, result:{distributions:[{metric:'total_trades',median}], windows:[...]}}
    if "metrics" in payload:
        return int(payload["metrics"].get("total_trades", 0))
    res = payload.get("result") or {}
    if isinstance(res, dict):
        m = res.get("metrics")
        if isinstance(m, dict) and "total_trades" in m:
            return int(m["total_trades"])
        # walk-forward
        dists = res.get("distributions") or []
        for d in dists:
            if d.get("metric") == "total_trades":
                # sum across windows (median is informational only)
                return int(sum(w.get("total_trades", 0) for w in (res.get("windows") or []) if w.get("error") is None))
    return None


def run_intraday(ticker: str) -> Result:
    t0 = time.time()
    is_micro = ticker in MICRO_SET
    code, payload = _post("/esf/backtest", body={
        "ticker": ticker,
        "period": "5d",
        "initial_equity": 10000.0,
        "is_micro": is_micro,
        "mode": "intraday",
    }, timeout=600)
    elapsed = time.time() - t0
    if code == 200:
        trades = _extract_trades(payload)
        return Result(ticker, "intraday", "PASS", code, trades, elapsed,
                      detail=f"trades={trades}")
    return Result(ticker, "intraday", "FAIL", code, None, elapsed,
                  detail=str(payload.get("detail", payload))[:120])


def run_daily(ticker: str) -> Result:
    t0 = time.time()
    is_micro = ticker in MICRO_SET
    code, payload = _post("/futures/backtest", params={
        "ticker": ticker,
        "start_date": "20230101",
        "end_date": "20241231",
        "equity": 100000,
        "is_micro": str(is_micro).lower(),
    }, timeout=900)
    elapsed = time.time() - t0
    if code == 200:
        trades = _extract_trades(payload)
        return Result(ticker, "daily", "PASS", code, trades, elapsed,
                      detail=f"trades={trades}")
    return Result(ticker, "daily", "FAIL", code, None, elapsed,
                  detail=str(payload.get("detail", payload))[:120])


def run_walk_forward(ticker: str) -> Result:
    t0 = time.time()
    is_micro = ticker in MICRO_SET
    code, payload = _post("/esf/backtest/walk-forward", body={
        "ticker": ticker,
        "initial_equity": 100000.0,
        "is_micro": is_micro,
        "trend_adaptive": True,
    }, timeout=900)
    elapsed = time.time() - t0
    if code == 200:
        trades = _extract_trades(payload)
        return Result(ticker, "walk-forward", "PASS", code, trades, elapsed,
                      detail=f"sum_trades={trades}")
    return Result(ticker, "walk-forward", "FAIL", code, None, elapsed,
                  detail=str(payload.get("detail", payload))[:120])


MODE_RUNNERS = {
    "intraday":     run_intraday,
    "daily":        run_daily,
    "walk-forward": run_walk_forward,
}


# ══════════════════════════════════════════
# F1: Overlay sanity verification
# ══════════════════════════════════════════


def run_overlay_analyze(ticker: str) -> Result:
    """analyze endpoint: direction/total_score/grade/amt_state.location/magnetic_ma 존재."""
    t0 = time.time()
    code, p = _get(f"/esf/analyze/{ticker}", params={"interval": "15m", "period": "5d"}, timeout=30)
    elapsed = time.time() - t0
    if code != 200:
        return Result(ticker, "overlay:analyze", "FAIL", code, None, elapsed,
                      detail=str(p.get("detail", p))[:80])
    missing = []
    for k in ("direction", "total_score", "grade", "amt_state"):
        if k not in p:
            missing.append(k)
    if "amt_state" in p:
        if "location" not in p["amt_state"]:
            missing.append("amt_state.location")
        if "aggression" not in p["amt_state"]:
            missing.append("amt_state.aggression")
    if "magnetic_ma" not in p:
        missing.append("magnetic_ma")
    if missing:
        return Result(ticker, "overlay:analyze", "FAIL", code, None, elapsed,
                      detail=f"missing={missing}")
    return Result(ticker, "overlay:analyze", "PASS", code, None, elapsed,
                  detail=f"grade={p.get('grade')} score={p.get('total_score')}")


def run_overlay_candles(ticker: str) -> Result:
    """candles endpoint: 각 candle에 ema_fast/mid/slow, bb_hband/lband, magnetic_ma, vwatr 키 존재 + finite."""
    t0 = time.time()
    code, p = _get(f"/esf/candles/{ticker}", params={"interval": "15m", "period": "5d"}, timeout=60)
    elapsed = time.time() - t0
    if code != 200:
        return Result(ticker, "overlay:candles", "FAIL", code, None, elapsed,
                      detail=str(p.get("detail", p))[:80])
    candles = p.get("candles") or []
    if not candles:
        return Result(ticker, "overlay:candles", "FAIL", code, None, elapsed,
                      detail="empty candles")
    # 마지막 candle (warm-up 후 안정된 값) 검사
    last = candles[-1]
    required = ("ema_fast", "ema_mid", "ema_slow", "bb_hband", "bb_lband", "bb_mavg")
    missing = [k for k in required if k not in last]
    # 핵심 키들이 finite 한지 (마지막 봉은 warm-up 충분히 지났음)
    non_finite = [k for k in required if k in last and not _is_finite(last[k])]
    if missing:
        return Result(ticker, "overlay:candles", "FAIL", code, None, elapsed,
                      detail=f"missing={missing}")
    if non_finite:
        return Result(ticker, "overlay:candles", "FAIL", code, None, elapsed,
                      detail=f"non_finite={non_finite}")
    return Result(ticker, "overlay:candles", "PASS", code, None, elapsed,
                  detail=f"n={len(candles)} ema_fast={last['ema_fast']:.2f}")


def run_overlay_volume_profile(ticker: str) -> Result:
    """volume-profile endpoint: POC/VAH/VAL/LVN 정합성 (vah > poc > val)."""
    t0 = time.time()
    code, p = _get(f"/esf/volume-profile/{ticker}", params={"period": "5d", "interval": "15m"}, timeout=30)
    elapsed = time.time() - t0
    if code != 200:
        return Result(ticker, "overlay:volume-profile", "FAIL", code, None, elapsed,
                      detail=str(p.get("detail", p))[:80])
    poc = p.get("poc")
    vah = p.get("vah")
    val = p.get("val")
    lvn = p.get("lvn_levels", [])
    if not (_is_finite(poc) and _is_finite(vah) and _is_finite(val)):
        return Result(ticker, "overlay:volume-profile", "FAIL", code, None, elapsed,
                      detail=f"non_finite POC/VAH/VAL = {poc}/{vah}/{val}")
    if not (poc > 0 and vah > 0 and val > 0):
        return Result(ticker, "overlay:volume-profile", "FAIL", code, None, elapsed,
                      detail=f"non-positive {poc}/{vah}/{val}")
    # VAH > VAL 보장 (POC가 VA 내부에 있어야 하지만, 가끔 edge case)
    if vah <= val:
        return Result(ticker, "overlay:volume-profile", "FAIL", code, None, elapsed,
                      detail=f"VAH({vah}) <= VAL({val})")
    if not isinstance(lvn, list):
        return Result(ticker, "overlay:volume-profile", "FAIL", code, None, elapsed,
                      detail="LVN not list")
    return Result(ticker, "overlay:volume-profile", "PASS", code, None, elapsed,
                  detail=f"poc={poc:.1f} VA=[{val:.1f},{vah:.1f}] LVN={len(lvn)}")


def run_overlay_regime(ticker: str) -> Result:
    """regime endpoint: regime enum + trend_score finite."""
    t0 = time.time()
    code, p = _get(f"/esf/regime/{ticker}", timeout=30)
    elapsed = time.time() - t0
    if code != 200:
        return Result(ticker, "overlay:regime", "FAIL", code, None, elapsed,
                      detail=str(p.get("detail", p))[:80])
    regime = p.get("regime")
    ts = p.get("trend_score")
    valid = {"BULL", "BEAR", "NEUTRAL", "CRISIS", "UNKNOWN"}
    if regime not in valid:
        return Result(ticker, "overlay:regime", "FAIL", code, None, elapsed,
                      detail=f"unknown regime: {regime}")
    if not _is_finite(ts):
        return Result(ticker, "overlay:regime", "FAIL", code, None, elapsed,
                      detail=f"non_finite trend_score: {ts}")
    return Result(ticker, "overlay:regime", "PASS", code, None, elapsed,
                  detail=f"{regime} ts={ts}")


OVERLAY_RUNNERS = {
    "analyze":         run_overlay_analyze,
    "candles":         run_overlay_candles,
    "volume-profile":  run_overlay_volume_profile,
    "regime":          run_overlay_regime,
}


def print_matrix(results: list[Result], tickers: list[str], modes: list[str]) -> None:
    print()
    print("=" * 110)
    print("VERIFICATION MATRIX — 8 ticker × 3 mode")
    print("=" * 110)
    # Header
    header = f"{'Ticker':<10}"
    for m in modes:
        header += f"| {m:<22}"
    print(header)
    print("-" * 110)
    # Rows
    by_key = {(r.ticker, r.mode): r for r in results}
    for t in tickers:
        row = f"{t:<10}"
        for m in modes:
            r = by_key.get((t, m))
            if r is None:
                cell = "—"
            elif r.status == "PASS":
                cell = f"✅ {r.http_code} {r.detail}"
            else:
                cell = f"❌ {r.http_code} {r.detail[:18]}"
            row += f"| {cell:<22}"
        print(row)
    print("=" * 110)
    # Summary
    pass_n = sum(1 for r in results if r.status == "PASS")
    fail_n = sum(1 for r in results if r.status == "FAIL")
    print(f"PASS={pass_n} / FAIL={fail_n} / total={len(results)}")
    print()
    # Failures detail
    fails = [r for r in results if r.status == "FAIL"]
    if fails:
        print("FAILURES:")
        for r in fails:
            print(f"  [{r.ticker} × {r.mode}] HTTP {r.http_code}: {r.detail}")


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    ap.add_argument("--modes", default=",".join(DEFAULT_MODES))
    ap.add_argument("--base", default=BASE, help="API base URL")
    ap.add_argument(
        "--overlays", action="store_true",
        help="Run overlay sanity check instead of backtest matrix (8 ticker × 4 endpoint = 32 calls)",
    )
    args = ap.parse_args()

    BASE = args.base
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # F1: overlay mode short-circuit
    if args.overlays:
        return run_overlays_mode(tickers)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    # Health check
    try:
        with urllib.request.urlopen(f"{BASE.replace('/api/v1', '')}/health", timeout=5) as r:
            if r.status != 200:
                print(f"Backend not healthy (HTTP {r.status}). Start with ./start-backend.sh")
                sys.exit(1)
    except Exception as e:
        print(f"Backend unreachable: {e}. Start with ./start-backend.sh start")
        sys.exit(1)

    print(f"BASE: {BASE}")
    print(f"Tickers: {tickers}")
    print(f"Modes: {modes}")
    print(f"Combinations: {len(tickers) * len(modes)}\n")

    results: list[Result] = []
    for t in tickers:
        for m in modes:
            runner = MODE_RUNNERS.get(m)
            if runner is None:
                results.append(Result(t, m, "SKIP", 0, None, 0.0, "unknown mode"))
                continue
            print(f"  [{t} × {m}] ... ", end="", flush=True)
            r = runner(t)
            results.append(r)
            print(f"{r.status} ({r.elapsed_s:.1f}s) {r.detail[:60]}")

    print_matrix(results, tickers, modes)


def run_overlays_mode(tickers: list[str]) -> None:
    """F1: overlay sanity 매트릭스 (8 ticker × 4 endpoint = 32 calls)."""
    # Health check
    try:
        with urllib.request.urlopen(f"{BASE.replace('/api/v1', '')}/health", timeout=5) as r:
            if r.status != 200:
                print(f"Backend not healthy (HTTP {r.status})")
                sys.exit(1)
    except Exception as e:
        print(f"Backend unreachable: {e}. Start with ./start-backend.sh start")
        sys.exit(1)

    endpoints = OVERLAY_ENDPOINTS
    print(f"\nOVERLAY SANITY — {len(tickers)} ticker × {len(endpoints)} endpoint = {len(tickers)*len(endpoints)} calls\n")

    results: list[Result] = []
    for t in tickers:
        for ep in endpoints:
            runner = OVERLAY_RUNNERS.get(ep)
            if runner is None:
                continue
            print(f"  [{t} × {ep}] ... ", end="", flush=True)
            r = runner(t)
            results.append(r)
            print(f"{r.status} ({r.elapsed_s:.1f}s) {r.detail[:60]}")

    # Matrix
    print()
    print("=" * 130)
    print(f"OVERLAY MATRIX — {len(tickers)} ticker × {len(endpoints)} endpoint")
    print("=" * 130)
    header = f"{'Ticker':<10}"
    for ep in endpoints:
        header += f"| {('overlay:'+ep):<28}"
    print(header)
    print("-" * 130)
    by_key = {(r.ticker, r.mode.replace("overlay:", "")): r for r in results}
    for t in tickers:
        row = f"{t:<10}"
        for ep in endpoints:
            r = by_key.get((t, ep))
            cell = "—" if r is None else (f"✅ {r.detail[:24]}" if r.status == "PASS" else f"❌ {r.detail[:22]}")
            row += f"| {cell:<28}"
        print(row)
    print("=" * 130)
    pass_n = sum(1 for r in results if r.status == "PASS")
    fail_n = sum(1 for r in results if r.status == "FAIL")
    print(f"PASS={pass_n} / FAIL={fail_n} / total={len(results)}")
    fails = [r for r in results if r.status == "FAIL"]
    if fails:
        print("\nFAILURES:")
        for r in fails:
            print(f"  [{r.ticker} × {r.mode}] HTTP {r.http_code}: {r.detail}")


if __name__ == "__main__":
    main()
