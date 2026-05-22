"""
V verification — LONG-only mode 효과 측정.

baseline ES (long_only_mode=False) vs LONG-only ES (long_only_mode=True) 4종 walk-forward 비교.
19 사이클 진단 결론(baseline SHORT net negative)을 직접 검증.

Usage:
    python3 backend/scripts/verify_v_long_only.py
"""
from __future__ import annotations

import copy
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
    dists = {d.metric: d for d in result.distributions}
    long_pnl = short_pnl = 0.0
    long_n = short_n = 0
    for w in result.windows:
        if w.direction_stats:
            long_pnl += float(w.direction_stats.get("long_pnl_total", 0) or 0)
            short_pnl += float(w.direction_stats.get("short_pnl_total", 0) or 0)
            long_n += int(w.direction_stats.get("long_trade_count", 0) or 0)
            short_n += int(w.direction_stats.get("short_trade_count", 0) or 0)
    return {
        "ticker": ticker,
        "median_return": dists.get("total_return_pct").median if "total_return_pct" in dists else 0.0,
        "median_sharpe": dists.get("sharpe_ratio").median if "sharpe_ratio" in dists else 0.0,
        "median_mdd": dists.get("max_drawdown_pct").median if "max_drawdown_pct" in dists else 0.0,
        "long_n": long_n,
        "short_n": short_n,
        "long_pnl": long_pnl,
        "short_pnl": short_pnl,
        "net_pnl": long_pnl + short_pnl,
    }


def main():
    cfg_base = ConfigManager().load()

    # mode A: baseline (T+U 적용 상태)
    cfg_a = copy.deepcopy(cfg_base)
    cfg_a.sp500_futures.long_only_mode = False

    # mode B: LONG-only
    cfg_b = copy.deepcopy(cfg_base)
    cfg_b.sp500_futures.long_only_mode = True

    print("=" * 90)
    print("V VERIFICATION — LONG-only Mode")
    print("=" * 90)

    tickers = ["ES=F", "NQ=F", "CL=F", "GC=F"]
    res_a = []
    res_b = []

    for t in tickers:
        print(f"\n>>> [Baseline T+U] {t}")
        res_a.append(run_ticker(t, cfg_a))
        print(f"   L={res_a[-1]['long_n']} S={res_a[-1]['short_n']} "
              f"Net={_fmt(res_a[-1]['net_pnl'])}")
        print(f">>> [LONG-only V]  {t}")
        res_b.append(run_ticker(t, cfg_b))
        print(f"   L={res_b[-1]['long_n']} S={res_b[-1]['short_n']} "
              f"Net={_fmt(res_b[-1]['net_pnl'])}")

    print()
    print("=" * 110)
    print(f"{'Ticker':<8} {'Mode':<14} {'L(n)':<6} {'S(n)':<6} {'Median ret':<12} "
          f"{'Sharpe':<8} {'MDD':<8} {'L$':<11} {'S$':<11} {'Net$':<11}")
    print("-" * 110)
    for a, b in zip(res_a, res_b):
        print(
            f"{a['ticker']:<8} {'Baseline T+U':<14} {a['long_n']:<6} {a['short_n']:<6} "
            f"{_fmt(a['median_return'], '%'):<12} {_fmt(a['median_sharpe']):<8} "
            f"{_fmt(a['median_mdd'], '%'):<8} {_fmt(a['long_pnl']):<11} "
            f"{_fmt(a['short_pnl']):<11} {_fmt(a['net_pnl']):<11}"
        )
        print(
            f"{'':<8} {'LONG-only V':<14} {b['long_n']:<6} {b['short_n']:<6} "
            f"{_fmt(b['median_return'], '%'):<12} {_fmt(b['median_sharpe']):<8} "
            f"{_fmt(b['median_mdd'], '%'):<8} {_fmt(b['long_pnl']):<11} "
            f"{_fmt(b['short_pnl']):<11} {_fmt(b['net_pnl']):<11}"
        )
        delta = b["net_pnl"] - a["net_pnl"]
        print(f"{'':<8} {'Δ Net':<14} {'':<6} {'':<6} {'':<12} {'':<8} {'':<8} "
              f"{'':<11} {'':<11} {_fmt(delta):<11}")
        print("-" * 110)

    # V verification gates
    print("\nV VERIFICATION:")
    for a, b in zip(res_a, res_b):
        t = a["ticker"]
        ok_short = b["short_n"] == 0
        delta = b["net_pnl"] - a["net_pnl"]
        ok_pnl = delta >= 0  # 손실 자산은 V로 회복
        mark = "✅" if ok_short else "❌"
        print(f"  {t}: {mark} SHORT 차단(short_n={b['short_n']}) | Δ Net = {_fmt(delta)}")


if __name__ == "__main__":
    main()
