"""
T verification — 4-ticker walk-forward 비교.

per_ticker_overrides 적용 후 ES/NQ/CL/GC 각각 평가.
S 진단 결과 vs T 결과를 비교해 SHORT 차단(GC/CL) + baseline 유지(ES/NQ) 검증.

Usage:
    python3 backend/scripts/verify_t_per_ticker.py
    python3 backend/scripts/verify_t_per_ticker.py --tickers ES=F,GC=F
"""
from __future__ import annotations

import argparse
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from data.config_manager import ConfigManager
from backtest.walk_forward_engine import WalkForwardEngine


def _fmt(v: float, suffix: str = "") -> str:
    return f"{v:+.2f}{suffix}"


def run_ticker(ticker: str, cfg) -> dict:
    engine = WalkForwardEngine(
        config=cfg,
        ticker=ticker,
        is_micro=ticker.startswith("M"),
        initial_equity=100_000.0,
        trend_adaptive=True,
    )
    result = engine.run()
    # 분포 통계 dict
    dists = {d.metric: d for d in result.distributions}
    # 방향별 PnL/거래수 합계
    long_pnl = short_pnl = 0.0
    long_n = short_n = 0
    long_w = short_w = 0
    for w in result.windows:
        if w.direction_stats:
            long_pnl += float(w.direction_stats.get("long_pnl_total", 0) or 0)
            short_pnl += float(w.direction_stats.get("short_pnl_total", 0) or 0)
            long_n += int(w.direction_stats.get("long_trade_count", 0) or 0)
            short_n += int(w.direction_stats.get("short_trade_count", 0) or 0)
            long_w += int(w.direction_stats.get("long_win_count", 0) or 0)
            short_w += int(w.direction_stats.get("short_win_count", 0) or 0)
    return {
        "ticker": ticker,
        "n_windows": result.n_windows,
        "median_return": dists.get("total_return_pct").median if "total_return_pct" in dists else 0.0,
        "median_sharpe": dists.get("sharpe_ratio").median if "sharpe_ratio" in dists else 0.0,
        "median_mdd": dists.get("max_drawdown_pct").median if "max_drawdown_pct" in dists else 0.0,
        "median_wr": dists.get("win_rate").median if "win_rate" in dists else 0.0,
        "total_trades": sum(w.total_trades for w in result.windows if w.error is None),
        "long_n": long_n,
        "short_n": short_n,
        "long_pnl": long_pnl,
        "short_pnl": short_pnl,
        "long_wr": (long_w / long_n) if long_n > 0 else 0.0,
        "short_wr": (short_w / short_n) if short_n > 0 else 0.0,
        "errors": result.errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tickers", default="ES=F,NQ=F,CL=F,GC=F",
        help="comma-separated tickers"
    )
    args = ap.parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    cfg = ConfigManager().load()
    overrides = getattr(cfg.sp500_futures, "per_ticker_overrides", {}) or {}
    print("=" * 80)
    print("T VERIFICATION — Per-ticker Strategy Differentiation")
    print("=" * 80)
    print(f"per_ticker_overrides loaded: {overrides}")
    print()

    results = []
    for t in tickers:
        print(f"\n>>> Running walk-forward: {t}")
        try:
            r = run_ticker(t, cfg)
            results.append(r)
            print(f"   windows={r['n_windows']} trades={r['total_trades']} "
                  f"L={r['long_n']} S={r['short_n']}")
        except Exception as e:
            print(f"   ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Summary table
    print()
    print("=" * 100)
    print(f"{'Ticker':<8} {'Wins':<7} {'Trd':<5} {'L(n)':<6} {'S(n)':<6} "
          f"{'Median ret':<12} {'Sharpe':<8} {'MDD':<8} {'WR':<7} "
          f"{'L$':<10} {'S$':<10}")
    print("-" * 100)
    for r in results:
        print(
            f"{r['ticker']:<8} {r['n_windows']:<7} {r['total_trades']:<5} "
            f"{r['long_n']:<6} {r['short_n']:<6} "
            f"{_fmt(r['median_return'], '%'):<12} {_fmt(r['median_sharpe']):<8} "
            f"{_fmt(r['median_mdd'], '%'):<8} {_fmt(r['median_wr'] * 100, '%'):<7} "
            f"{_fmt(r['long_pnl']):<10} {_fmt(r['short_pnl']):<10}"
        )
    print("=" * 100)

    # T verification gates
    print("\nT VERIFICATION:")
    for r in results:
        ticker = r["ticker"]
        allow_short = overrides.get(ticker, {}).get("enable_short", True)
        gates = []
        if not allow_short:
            if r["short_n"] == 0:
                gates.append("✅ SHORT 차단 OK (short_n=0)")
            else:
                gates.append(f"❌ SHORT 차단 실패 (short_n={r['short_n']})")
        else:
            gates.append(f"baseline (SHORT 허용, short_n={r['short_n']})")
        print(f"  {ticker}: {' | '.join(gates)}")


if __name__ == "__main__":
    main()
